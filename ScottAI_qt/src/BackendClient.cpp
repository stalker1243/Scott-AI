#include "BackendClient.h"
#include "ProtocolValidation.h"
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QRegularExpression>
#include <QNetworkReply>
#include <QNetworkProxy>
#include <QFileInfo>
#include <QCoreApplication>
#include <QUrlQuery>
#include <QSet>
#include <memory>

BackendClient::BackendClient(QUrl base, QObject *parent) : QObject(parent), m_base(base) {
    m_network.setProxy(QNetworkProxy::NoProxy);
    m_poll.setInterval(5000);
    connect(&m_poll, &QTimer::timeout, this, &BackendClient::refresh);
    m_protocolPoll.setInterval(800);
    m_voiceInstallPoll.setInterval(900);
    m_voicePreparationPoll.setInterval(5000);
    connect(&m_voicePreparationPoll, &QTimer::timeout, this, &BackendClient::refreshVoicePreparation);
    connect(&m_voiceInstallPoll, &QTimer::timeout, this, &BackendClient::refreshVoiceInstall);
    connect(&m_protocolPoll, &QTimer::timeout, this, &BackendClient::pollProtocolJob);
    // Drain both channels immediately; never let Python block on a full pipe.
    connect(&m_process, &QProcess::readyReadStandardOutput, this, [this] { m_process.readAllStandardOutput(); });
    connect(&m_process, &QProcess::readyReadStandardError, this, [this] { m_process.readAllStandardError(); });
    connect(&m_process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError) {
        m_starting = false;
        m_error = QStringLiteral("Не удалось запустить Python: ") + m_process.errorString();
        emit stateChanged();
    });
    connect(&m_process, &QProcess::finished, this, [this](int code, QProcess::ExitStatus) {
        m_starting = false;
        m_online = false;
        m_abilitiesReady = false;
        m_modelsReady = false; ++m_modelsGeneration; emit modelsStateChanged();
        m_protocolsReady = false; m_protocolJobReady = false;
        emit protocolsStateChanged(); emit protocolJobChanged();
        emit abilitiesStateChanged();
        m_metrics.clear();
        if (code != 0) m_error = QStringLiteral("Backend завершился. Код: %1").arg(code);
        emit metricsChanged();
        emit stateChanged();
    });
}
BackendClient::~BackendClient() { stopBackend(); }
QString BackendClient::status() const {
    if (m_online) return QStringLiteral("На связи");
    if (m_starting) return QStringLiteral("Загрузка моделей…");
    return QStringLiteral("Нет подключения");
}
void BackendClient::configureProcess(const QString &directory, const QString &python) {
    m_directory = directory;
    m_python = python;
}
void BackendClient::beginPolling() { refresh(); m_poll.start(); }
void BackendClient::request(const QString &path, const QJsonObject *body, int timeout, Callback callback, bool remove, bool form, bool patch) {
    QUrl url = m_base;
    const QUrl relative(path);
    url.setPath(relative.path(QUrl::FullyEncoded), QUrl::StrictMode); url.setQuery(relative.query());
    QNetworkRequest req(url);
    req.setTransferTimeout(timeout);
    req.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    req.setHeader(QNetworkRequest::ContentTypeHeader, form ? "application/x-www-form-urlencoded" : "application/json");
    QByteArray payload;
    if (body) {
        if (form) {
            QUrlQuery query;
            for (auto it = body->begin(); it != body->end(); ++it) query.addQueryItem(it.key(), it.value().toString());
            payload = query.query(QUrl::FullyEncoded).toUtf8();
        } else payload = QJsonDocument(*body).toJson(QJsonDocument::Compact);
    }
    auto *reply = patch ? m_network.sendCustomRequest(req, "PATCH", payload) : remove ? m_network.deleteResource(req) : body ? m_network.post(req, payload) : m_network.get(req);
    connect(reply, &QNetworkReply::finished, this, [reply, callback] {
        QString error;
        QJsonObject object;
        const auto bytes = reply->readAll();
        if (reply->error() != QNetworkReply::NoError) {
            const auto details = QJsonDocument::fromJson(bytes).object();
            error = details.value("message").toString(details.value("error").toString(details.value("detail").toString()));
            if (error.isEmpty()) error = QStringLiteral("Нет ответа от backend: ") + reply->errorString();
        } else {
            QJsonParseError parse;
            const auto json = QJsonDocument::fromJson(bytes, &parse);
            if (parse.error != QJsonParseError::NoError || !json.isObject())
                error = QStringLiteral("Backend вернул некорректный JSON.");
            else object = json.object();
        }
        reply->deleteLater();
        callback(object, error);
    });
}
void BackendClient::refresh() {
    if (m_refreshing) return;
    m_refreshing = true;
    request("/health", nullptr, 4000, [this](const QJsonObject &data, const QString &error) {
        m_online = error.isEmpty() && data.value("status").toString() == "online";
        if (m_online) m_starting = false;
        emit stateChanged();
        if (!m_online) {
            m_voiceInstallReady = false; ++m_voiceInstallRevision;
            emit voiceInstallChanged();
            m_modelsReady = false; ++m_modelsGeneration; emit modelsStateChanged();
            m_listeningReady = false;
            m_profileReady = false;
            m_abilitiesReady = false;
            m_protocolsReady = false; m_protocolJobReady = false;
            emit protocolsStateChanged(); emit protocolJobChanged();
            emit abilitiesStateChanged();
            emit profileStateChanged();
            emit listeningChanged();
            m_refreshing = false;
            m_metrics.clear();
            emit metricsChanged();
            return;
        }
        request("/metrics", nullptr, 4000, [this](const QJsonObject &data, const QString &error) {
            m_refreshing = false;
            m_metrics = error.isEmpty() ? data.value("metrics").toObject().toVariantMap() : QVariantMap{};
            emit metricsChanged();
        });
        refreshListening();
        if (!m_voiceInstall.isEmpty() && (!m_voiceInstallReady || m_voiceInstall.value("state").toString() == "running" || m_voiceInstall.value("state").toString() == "cancelling")) refreshVoiceInstall();
        if (protocolRunning()) pollProtocolJob();
    });
}
void BackendClient::refreshListening() {
    if (!m_online || m_listeningBusy) return;
    m_listeningBusy = true; emit listeningChanged();
    request("/listen/status", nullptr, 6000, [this](const QJsonObject &data, const QString &error) {
        m_listeningBusy = false;
        m_listeningReady = m_online && error.isEmpty() && data.value("listening").isBool() && data.value("available").isBool();
        if (m_listeningReady) {
            m_listening = data.value("listening").toBool();
            m_listeningAvailable = data.value("available").toBool();
        }
        emit listeningChanged();
    });
}
static bool validAbilities(const QJsonObject &data) {
    if (!data.value("success").toBool() || !data.value("groups").isArray()) return false;
    QSet<QString> ids;
    int total = 0, ready = 0;
    for (const auto &groupValue : data.value("groups").toArray()) {
        const auto group = groupValue.toObject();
        if (!group.value("group").isString() || group.value("group").toString().trimmed().isEmpty() || !group.value("items").isArray()) return false;
        for (const auto &itemValue : group.value("items").toArray()) {
            const auto item = itemValue.toObject();
            const auto id = item.value("id").toString();
            const auto state = item.value("state").toString();
            if (id.trimmed().isEmpty() || ids.contains(id) || !item.value("title").isString() || item.value("title").toString().trimmed().isEmpty() ||
                !item.value("detail").isString() || !item.value("reason").isString() || !item.value("examples").isArray() ||
                (state != "ready" && state != "off")) return false;
            for (const auto &example : item.value("examples").toArray())
                if (!example.isString() || example.toString().trimmed().isEmpty()) return false;
            ids.insert(id); ++total; if (state == "ready") ++ready;
        }
    }
    return data.value("total").isDouble() && data.value("total").toDouble() == total &&
           data.value("ready").isDouble() && data.value("ready").toDouble() == ready;
}
void BackendClient::refreshAbilities() {
    if (!m_online || m_abilitiesBusy) return;
    m_abilitiesBusy = true; m_abilitiesError.clear(); emit abilitiesStateChanged();
    request("/abilities", nullptr, 15000, [this](const QJsonObject &data, const QString &error) {
        m_abilitiesBusy = false;
        if (m_online && error.isEmpty() && validAbilities(data)) {
            m_abilities = data.value("groups").toArray().toVariantList();
            m_abilitiesReadyCount = data.value("ready").toInt(); m_abilitiesTotal = data.value("total").toInt();
            m_abilitiesReady = true; emit abilitiesChanged();
        } else {
            m_abilitiesReady = false;
            m_abilitiesError = !error.isEmpty() ? error : QStringLiteral("Не удалось загрузить список действий Scott.");
        }
        emit abilitiesStateChanged();
    });
}
static bool validProfile(const QJsonObject &data, bool withStyles) {
    if (!data.value("success").toBool() || !data.value("name").isString() || !data.value("about").isString() ||
        !data.value("style").isString() || !data.value("interests").isArray()) return false;
    for (const auto &interest : data.value("interests").toArray()) if (!interest.isString()) return false;
    if (withStyles) {
        const auto styles = data.value("styles").toArray();
        if (styles.isEmpty()) return false;
        bool known = false;
        for (const auto &style : styles) {
            const auto entry = style.toObject();
            if (!entry.value("id").isString() || !entry.value("title").isString()) return false;
            known |= entry.value("id") == data.value("style");
        }
        if (!known) return false;
    }
    return true;
}
void BackendClient::refreshProfile() {
    if (!m_online || m_profileBusy) return;
    m_profileBusy = true; m_profileError.clear(); m_profileNotice.clear(); emit profileStateChanged();
    request("/personality", nullptr, 6000, [this](const QJsonObject &data, const QString &error) {
        m_profileBusy = false;
        if (error.isEmpty() && validProfile(data, true)) {
            m_profile = data.toVariantMap(); m_profileReady = true; emit profileChanged();
        } else {
            m_profileReady = false;
            m_profileError = !error.isEmpty() ? error : QStringLiteral("Не удалось прочитать профиль Scott.");
        }
        emit profileStateChanged();
    });
}
void BackendClient::saveProfile(const QString &name, const QString &about, const QString &style, const QStringList &interests) {
    if (m_profileBusy || !m_online || !m_profileReady) return;
    bool known = false;
    for (const auto &entry : m_profile.value("styles").toList()) known |= entry.toMap().value("id").toString() == style;
    bool valid = known && name.trimmed().size() <= 60 && about.trimmed().size() <= 300 && interests.size() <= 12;
    QStringList cleaned;
    for (const auto &entry : interests) {
        const auto trimmed = entry.trimmed();
        valid &= !trimmed.isEmpty() && trimmed.size() <= 40 && !cleaned.contains(trimmed);
        cleaned.append(trimmed);
    }
    if (!valid) {
        m_profileError = QStringLiteral("Проверьте длину полей и выбранный характер."); emit profileStateChanged(); return;
    }
    m_profileBusy = true; m_profileError.clear(); m_profileNotice.clear(); emit profileStateChanged();
    const QJsonObject body{{"name", name.trimmed()}, {"about", about.trimmed()}, {"style", style}, {"interests", QJsonArray::fromStringList(cleaned)}};
    request("/personality", &body, 15000, [this](const QJsonObject &data, const QString &error) {
        m_profileBusy = false;
        if (error.isEmpty() && validProfile(data, false)) {
            const auto styles = m_profile.value("styles");
            m_profile = data.toVariantMap(); m_profile.insert("styles", styles);
            m_profileNotice = QStringLiteral("Профиль сохранён.");
            emit profileSaved(); emit profileChanged();
        } else m_profileError = !error.isEmpty() ? error : QStringLiteral("Scott не подтвердил сохранение профиля.");
        emit profileStateChanged();
    });
}
void BackendClient::setListening(bool enabled) {
    if (!m_online || !m_listeningReady || !m_listeningAvailable || m_listeningBusy || enabled == m_listening) return;
    m_listeningBusy = true; m_listeningError.clear(); emit listeningChanged();
    const QJsonObject body{};
    request(enabled ? "/listen/start" : "/listen/stop", &body, 15000, [this](const QJsonObject &data, const QString &error) {
        m_listeningBusy = false;
        const bool valid = error.isEmpty() && data.value("success").toBool() && data.value("listening").isBool() && data.value("available").isBool();
        m_listeningReady = m_online && valid;
        if (valid) {
            m_listening = data.value("listening").toBool();
            m_listeningAvailable = data.value("available").toBool();
        } else {
            m_listeningError = !error.isEmpty() ? error : data.value("message").toString(QStringLiteral("Не удалось переключить микрофон."));
            emit listeningFailed(m_listeningError);
        }
        emit listeningChanged();
        if (!valid) refreshListening();
    });
}
void BackendClient::append(const QString &role, const QString &text) {
    m_messages.append(QVariantMap{{"role", role}, {"text", text}});
    emit messagesChanged();
}
void BackendClient::sendMessage(const QString &text) {
    const auto trimmed = text.trimmed();
    if (trimmed.isEmpty() || m_busy) return;
    if (!m_online) {
        m_error = QStringLiteral("Подключите backend перед отправкой сообщения.");
        emit stateChanged();
        return;
    }
    m_error.clear();
    m_busy = true;
    append("user", trimmed);
    emit stateChanged();
    const QJsonObject body{{"question", trimmed}, {"quiet_mode", true}};
    request("/ask", &body, 90000, [this](const QJsonObject &data, const QString &error) {
        m_busy = false;
        const auto answer = data.value("data").toObject().value("answer").toString();
        if (!error.isEmpty() || !data.value("success").toBool() || answer.isEmpty()) {
            m_error = !error.isEmpty() ? error : QStringLiteral("Backend не вернул ответ. Попробуйте ещё раз.");
            append("error", m_error);
        } else append("assistant", answer);
        emit stateChanged();
    });
}
void BackendClient::clearChat() {
    if (m_busy) return;
    m_messages.clear(); m_error.clear();
    emit messagesChanged(); emit stateChanged();
}

bool BackendClient::beginSettingsOperation() {
    if (m_settingsBusy) return false;
    m_settingsError.clear(); m_settingsNotice.clear();
    if (!m_online) {
        m_settingsError = QStringLiteral("Подключите Scott, чтобы изменить настройки.");
        emit settingsStateChanged(); return false;
    }
    m_settingsBusy = true; emit settingsStateChanged(); return true;
}
void BackendClient::refreshSettings() {
    if (beginSettingsOperation()) loadSettings();
}
void BackendClient::loadSettings() {
    refreshVoiceInstall();
    refreshVoicePreparation();
    const QList<QPair<QString, QString>> sections{
        {"audio", "/audio/settings"}, {"device", "/settings/device"},
        {"voices", "/voice/available"}, {"characters", "/audio/characters"},
        {"versions", "/versions/items"}};
    auto remaining = std::make_shared<int>(sections.size());
    m_settingsReady.clear();
    for (const auto &section : sections) {
        const auto key = section.first;
        request(section.second, nullptr, key == "voices" ? 20000 : 6000, [this, remaining, key](const QJsonObject &data, const QString &error) {
            const bool successful = !data.contains("success") || data.value("success").toBool();
            const bool valid = successful &&
                (key == "audio" ? data.value("settings").isObject() && data.value("devices").isObject() :
                 key == "device" ? data.value("engines").isObject() :
                 key == "voices" ? data.value("voices").isArray() :
                 key == "characters" ? data.value("characters").isArray() : data.value("data").isArray());
            if (error.isEmpty() && valid) {
                m_settings.insert(key, data.toVariantMap());
                m_settingsReady.append(key);
            } else {
                if (!m_settingsError.isEmpty()) m_settingsError += "\n";
                const QMap<QString, QString> labels{{"audio", QStringLiteral("Звук")}, {"device", QStringLiteral("Обработка речи")},
                    {"voices", QStringLiteral("Голос")}, {"characters", QStringLiteral("Характер звучания")}, {"versions", QStringLiteral("Версии действий")}};
                m_settingsError += labels.value(key) + ": " + (!error.isEmpty() ? error : data.value("message").toString(QStringLiteral("Некорректный ответ backend.")));
            }
            if (--*remaining == 0) {
                m_settingsBusy = false;
                emit settingsChanged(); emit settingsStateChanged();
            }
        });
    }
}
void BackendClient::acceptVoiceInstall(const QJsonObject &job) {
    const auto state = job.value("state").toString();
    const bool newlyComplete = state == "complete" &&
        (m_voiceInstall.value("id").toString() != job.value("id").toString() || m_voiceInstall.value("state").toString() != state);
    m_voiceInstall = job.toVariantMap();
    m_voiceInstallReady = true;
    if (state == "running" || state == "cancelling") m_voiceInstallPoll.start();
    else m_voiceInstallPoll.stop();
    emit voiceInstallChanged();
    if (newlyComplete) {
        request("/voice/available", nullptr, 20000, [this](const QJsonObject &data, const QString &error) {
            if (error.isEmpty() && data.value("voices").isArray()) {
                m_settings.insert("voices", data.toVariantMap());
                if (!m_settingsReady.contains("voices")) m_settingsReady.append("voices");
                emit settingsChanged(); emit settingsStateChanged();
            }
        });
    }
}
bool BackendClient::acceptVoicePreparation(const QJsonObject &data) {
    const auto state = data.value("state").toString();
    const auto id = data.value("id").toString();
    const QStringList states{"idle", "running", "cancelling", "complete", "cancelled", "failed"};
    if (!states.contains(state) || !data.value("model_loaded").isBool() || !data.value("message").isString() ||
        !data.value("id").isString() || (!id.isEmpty() && !QRegularExpression("^[0-9a-f]{32}$").match(id).hasMatch()) ||
        ((state == "running" || state == "cancelling" || state == "complete") && id.isEmpty())) return false;
    m_voicePreparation = data.toVariantMap();
    m_voicePreparationReady = true;
    m_voicePreparationPoll.setInterval(state == "running" || state == "cancelling" ? 900 : 5000);
    m_voicePreparationPoll.start();
    emit voicePreparationChanged();
    return true;
}
void BackendClient::refreshVoicePreparation() {
    if (!m_online || m_voicePreparationFetching || m_voicePreparationPending) return;
    m_voicePreparationFetching = true;
    const auto revision = m_voicePreparationRevision;
    request("/voice/prepare", nullptr, 6000, [this, revision](const QJsonObject &data, const QString &error) {
        m_voicePreparationFetching = false;
        if (revision != m_voicePreparationRevision || !m_online) return;
        if (error.isEmpty() && acceptVoicePreparation(data)) return;
        m_voicePreparationReady = false;
        m_voicePreparation.insert("model_loaded", false);
        m_voicePreparation.insert("message", QStringLiteral("Состояние модели недоступно. Обновите данные после подключения."));
        emit voicePreparationChanged();
    });
}
void BackendClient::warmScottVoice() {
    const auto state = m_voicePreparation.value("state").toString();
    if (!m_online || !m_voicePreparationReady || m_voicePreparationPending || m_settingsBusy ||
        state == "running" || state == "cancelling" || m_voicePreparation.value("model_loaded").toBool()) return;
    m_voicePreparationPending = true;
    const auto revision = ++m_voicePreparationRevision;
    m_voicePreparation.insert("state", "running");
    m_voicePreparation.insert("id", "");
    m_voicePreparation.insert("message", QStringLiteral("Загружаем модель и готовим голос…"));
    emit voicePreparationChanged();
    const QJsonObject body;
    request("/voice/prepare", &body, 20000, [this, revision](const QJsonObject &data, const QString &error) {
        m_voicePreparationPending = false;
        if (revision != m_voicePreparationRevision || !m_online) { refreshVoicePreparation(); return; }
        if (error.isEmpty() && acceptVoicePreparation(data)) return;
        m_voicePreparationReady = false;
        refreshVoicePreparation();
    });
}
void BackendClient::releaseScottVoice() {
    const auto id = m_voicePreparation.value("id").toString();
    if (!m_online || !m_voicePreparationReady || m_voicePreparationPending || id.isEmpty() ||
        m_voicePreparation.value("state").toString() == "cancelling") return;
    m_voicePreparationPending = true;
    const auto revision = ++m_voicePreparationRevision;
    m_voicePreparation.insert("state", "cancelling");
    m_voicePreparation.insert("message", QStringLiteral("Освобождаем модель…"));
    emit voicePreparationChanged();
    const QJsonObject body{{"id", id}};
    request("/voice/prepare/cancel", &body, 6000, [this, revision](const QJsonObject &data, const QString &error) {
        m_voicePreparationPending = false;
        if (revision != m_voicePreparationRevision || !m_online) { refreshVoicePreparation(); return; }
        if (error.isEmpty() && acceptVoicePreparation(data)) return;
        m_voicePreparationReady = false;
        refreshVoicePreparation();
    });
}
void BackendClient::refreshVoiceInstall() {
    if (!m_online || m_voiceInstallFetching || m_voiceInstallPending) return;
    m_voiceInstallFetching = true;
    const auto revision = m_voiceInstallRevision;
    request("/voice/install", nullptr, 6000, [this, revision](const QJsonObject &data, const QString &error) {
        m_voiceInstallFetching = false;
        if (revision != m_voiceInstallRevision) return;
        if (error.isEmpty() && data.value("state").isString()) acceptVoiceInstall(data);
        else {
            m_voiceInstallReady = false;
            m_voiceInstall.insert("message", QStringLiteral("Состояние подготовки недоступно. Обновите данные после подключения."));
            emit voiceInstallChanged();
        }
    });
}
void BackendClient::prepareScottVoice(bool checkOnly) {
    const auto state = m_voiceInstall.value("state").toString();
    if (!m_online || !m_voiceInstallReady || m_voiceInstallPending || state == "running" || state == "cancelling") return;
    if (!checkOnly && !m_voiceInstall.value("supported").toBool()) return;
    m_voiceInstallPending = true;
    const auto revision = ++m_voiceInstallRevision;
    const auto previous = m_voiceInstall;
    m_voiceInstall.insert("state", "running");
    m_voiceInstall.insert("message", checkOnly ? QStringLiteral("Проверяем Scott Voice") : QStringLiteral("Подготавливаем Scott Voice"));
    emit voiceInstallChanged();
    const QJsonObject body{{"action", checkOnly ? "check" : "install"}};
    request("/voice/install", &body, 10000, [this, previous, revision](const QJsonObject &data, const QString &error) {
        m_voiceInstallPending = false;
        if (revision != m_voiceInstallRevision || !m_online) { refreshVoiceInstall(); return; }
        if (error.isEmpty() && data.value("state").isString()) acceptVoiceInstall(data);
        else {
            m_voiceInstall = previous;
            m_voiceInstall.insert("message", error.isEmpty() ? QStringLiteral("Не удалось запустить подготовку.") : error);
            emit voiceInstallChanged();
            // A timed out POST may still have started a job. Reconcile before another click.
            m_voiceInstallReady = false;
            refreshVoiceInstall();
        }
    });
}
void BackendClient::cancelScottVoice() {
    if (!m_online || m_voiceInstallPending || m_voiceInstall.value("state").toString() != "running") return;
    const auto id = m_voiceInstall.value("id").toString();
    if (id.isEmpty()) return;
    m_voiceInstallPending = true;
    const auto revision = ++m_voiceInstallRevision;
    const QJsonObject body{{"id", id}};
    m_voiceInstall.insert("state", "cancelling");
    emit voiceInstallChanged();
    request("/voice/install/cancel", &body, 6000, [this, revision](const QJsonObject &data, const QString &error) {
        m_voiceInstallPending = false;
        if (revision != m_voiceInstallRevision || !m_online) { refreshVoiceInstall(); return; }
        if (error.isEmpty() && data.value("state").isString()) acceptVoiceInstall(data);
        else { m_voiceInstallReady = false; refreshVoiceInstall(); }
    });
}
void BackendClient::applySetting(const QString &group, const QVariantMap &changes) {
    if (m_settingsBusy) return;
    QString path, required, validationError;
    bool valid = changes.size() == 1;
    if (group == "audio") {
        path = "/audio/settings"; required = "audio";
        const auto key = changes.isEmpty() ? QString() : changes.firstKey();
        const auto value = changes.value(key);
        bool number = false;
        const int volume = value.toInt(&number);
        valid = valid && (key == "volume" ? number && volume >= 0 && volume <= 100 :
                         key == "character" ? !value.toString().isEmpty() : key == "input_device" || key == "output_device");
        if (key == "character") required = "characters";
    } else if (group == "quiet") {
        path = "/audio/quiet"; required = "audio"; valid = valid && changes.contains("quiet");
    } else if (group == "voice") {
        path = "/voice/select"; required = "voices"; valid = valid && !changes.value("voice").toString().isEmpty();
    } else if (group == "voiceStreaming" || group == "voiceAcceleration") {
        path = "/voice/select"; required = "voices";
        const auto catalog = m_settings.value("voices").toMap();
        const QString key = group == "voiceStreaming" ? "streaming" : "acceleration";
        const QString capability = group == "voiceStreaming" ? "streaming_available" : "acceleration_available";
        valid = changes.size() == 2 && catalog.value("current").toString() == "scott-voice" &&
                changes.value("voice").toString() == "scott-voice" && changes.value(key).typeId() == QMetaType::Bool;
        bool available = false;
        for (const auto &option : catalog.value("voices").toList()) {
            const auto entry = option.toMap();
            if (entry.value("id").toString() == "scott-voice") available = entry.value(capability).toBool();
        }
        valid = valid && (available || !changes.value(key).toBool());
    } else if (group == "voiceBuffer") {
        path = "/voice/select"; required = "voices";
        const auto catalog = m_settings.value("voices").toMap();
        bool known = false, available = false;
        for (const auto &option : catalog.value("scott_buffers").toList())
            if (option.toMap().value("id") == changes.value("buffer")) known = true;
        for (const auto &option : catalog.value("voices").toList()) {
            const auto entry = option.toMap();
            if (entry.value("id").toString() == "scott-voice") available = entry.value("available").toBool();
        }
        valid = changes.size() == 2 && catalog.value("current").toString() == "scott-voice" &&
                changes.value("voice").toString() == "scott-voice" &&
                changes.value("buffer").typeId() == QMetaType::QString && known && available;
    } else if (group == "voiceProfile") {
        path = "/voice/select"; required = "voices";
        const auto catalog = m_settings.value("voices").toMap();
        bool known = false;
        for (const auto &option : catalog.value("scott_profiles").toList())
            if (option.toMap().value("id") == changes.value("profile")) known = true;
        valid = changes.size() == 2 && catalog.value("current").toString() == "scott-voice" &&
                changes.value("voice").toString() == "scott-voice" && known;
        for (const auto &option : catalog.value("voices").toList()) {
            const auto entry = option.toMap();
            if (entry.value("id").toString() == "scott-voice" && !entry.value("available", true).toBool()) {
                valid = false; validationError = entry.value("reason").toString();
            }
        }
    } else if (group == "device") {
        path = "/settings/device"; required = "device";
        const auto engine = changes.value("engine").toString();
        const auto choice = changes.value("choice").toString();
        const auto state = m_settings.value("device").toMap();
        const auto engines = state.value("engines").toMap();
        const auto info = engines.value(engine).toMap();
        bool available = choice == "auto" || choice == "cpu" ||
                (choice == "cuda" && state.value("cuda_available").toBool()) ||
                (choice == "rocm" && state.value("rocm_available").toBool()) ||
                (choice == "mps" && engine == "silero" && state.value("mps_available").toBool());
        if (info.contains("options")) {
            available = false;
            for (const auto &option : info.value("options").toList()) {
                const auto entry = option.toMap();
                if (entry.value("id").toString() == choice) available = entry.value("available").toBool();
            }
        }
        valid = changes.size() == 2 && engines.contains(engine) && !info.value("locked_by_env").toBool() && available;
    } else valid = false;
    if (group == "voice" || (group == "audio" && changes.contains("character"))) {
        const auto section = group == "voice" ? "voices" : "characters";
        const auto field = group == "voice" ? "voice" : "character";
        const auto options = m_settings.value(section).toMap().value(section).toList();
        bool known = false;
        for (const auto &option : options) {
            const auto entry = option.toMap();
            if (entry.value("id") == changes.value(field)) {
                known = entry.value("available", true).toBool();
                if (!known) validationError = entry.value("reason").toString();
            }
        }
        valid = valid && known;
    }
    if (!valid || !m_settingsReady.contains(required)) {
        m_settingsError = validationError.isEmpty() ? QStringLiteral("Настройка недоступна. Обновите данные и проверьте выбранное значение.") : validationError;
        emit settingsStateChanged(); return;
    }
    if (!beginSettingsOperation()) return;
    const auto body = QJsonObject::fromVariantMap(changes);
    request(path, &body, 15000, [this](const QJsonObject &data, const QString &error) {
        if (!error.isEmpty() || !data.value("success").toBool()) {
            m_settingsBusy = false;
            m_settingsError = !error.isEmpty() ? error : data.value("message").toString(data.value("error").toString(QStringLiteral("Не удалось сохранить настройку.")));
            emit settingsChanged(); emit settingsStateChanged(); return;
        }
        m_settingsNotice = data.value("message").toString(QStringLiteral("Настройка сохранена."));
        loadSettings(); // Show the values that the backend actually accepted.
    });
}
void BackendClient::previewVoice() {
    if (!m_settingsReady.contains("voices") || !beginSettingsOperation()) return;
    const bool scott = m_settings.value("voices").toMap().value("current").toString() == "scott-voice";
    m_settingsNotice = scott ? QStringLiteral("Готовим Scott Voice. Первая новая фраза может занять до минуты…") : QStringLiteral("Готовим пробную фразу…");
    emit settingsStateChanged();
    const QJsonObject body{{"text", scott ? QStringLiteral("Скотт на связи. Всё в порядке.") : QStringLiteral("Скотт на связи. Всё в порядке. Я проверю детали и помогу с задачей. Яркость — сорок процентов. Программное обеспечение обновлено.")}, {"force", "true"}};
    request("/speak", &body, 90000, [this](const QJsonObject &data, const QString &error) {
        m_settingsBusy = false;
        if (!error.isEmpty() || !data.value("success").toBool()) m_settingsError = !error.isEmpty() ? error : data.value("message").toString(QStringLiteral("Не удалось воспроизвести голос."));
        else m_settingsNotice = data.value("fallback").toBool() ? data.value("message").toString() : QStringLiteral("Пробная фраза воспроизведена.");
        emit settingsStateChanged();
    }, false, true);
}
void BackendClient::startBackend() {
    if (m_starting || m_online || ownsBackend()) return;
    m_starting = true; m_error.clear(); emit stateChanged();
    // Recheck ownership immediately before starting a process.
    request("/health", nullptr, 2500, [this](const QJsonObject &data, const QString &error) {
        if (error.isEmpty() && data.value("status").toString() == "online") {
            m_starting = false; m_online = true; emit stateChanged(); refresh(); return;
        }
        if (!QFileInfo::exists(m_directory + "/main.py") || !QFileInfo::exists(m_python)) {
            m_starting = false;
            m_error = QStringLiteral("Не найден Python или backend/main.py. Запустите через run.ps1.");
            emit stateChanged(); return;
        }
        auto env = QProcessEnvironment::systemEnvironment();
        env.insert("SCOTT_PARENT_PID", QString::number(QCoreApplication::applicationPid()));
        env.insert("PYTHONIOENCODING", "utf-8");
        m_process.setProcessEnvironment(env);
        m_process.setWorkingDirectory(m_directory);
        m_process.start(m_python, {"-u", "main.py"});
        emit stateChanged();
    });
}
void BackendClient::stopBackend() {
    // Never stop a backend started by Avalonia or by the user.
    if (!ownsBackend()) return;
    m_process.terminate();
    if (!m_process.waitForFinished(1500)) {
        m_process.kill();
        m_process.waitForFinished(1500);
    }
}

bool BackendClient::beginMemoryOperation() {
    if (m_memoryBusy) return false;
    m_memoryNotice.clear();
    m_memoryError.clear();
    if (!m_online) {
        m_memoryError = QStringLiteral("Память недоступна: нет подключения к Scott.");
        emit memoryStateChanged();
        return false;
    }
    m_memoryBusy = true;
    emit memoryStateChanged();
    return true;
}
void BackendClient::loadMemories() {
    request("/memories", nullptr, 5000, [this](const QJsonObject &data, const QString &error) {
        m_memoryBusy = false;
        if (!error.isEmpty() || !data.value("success").toBool() || !data.value("memories").isArray() || !data.value("kinds").isArray()) {
            m_memoryError = error.isEmpty() ? QStringLiteral("Не удалось получить память Scott.") : error;
        } else {
            m_memories = data.value("memories").toArray().toVariantList();
            m_memoryKinds = data.value("kinds").toArray().toVariantList();
            m_memorySettingsAvailable = data.value("auto_capture").isBool();
            m_autoMemoryEnabled = data.value("auto_capture").toBool(true);
            m_archivedTurns = data.value("archived_turns").toInt(-1);
            m_memoryError = data.value("warning").toString();
            emit memoriesChanged();
        }
        emit memoryStateChanged();
    });
}
void BackendClient::refreshMemories() {
    if (beginMemoryOperation()) loadMemories();
}
void BackendClient::setAutoMemoryEnabled(bool enabled) {
    if (!m_memorySettingsAvailable || !beginMemoryOperation()) return;
    const QJsonObject body{{"auto_capture", enabled}};
    request("/memories/settings", &body, 5000, [this](const QJsonObject &data, const QString &error) {
        if (!error.isEmpty() || !data.value("success").toBool()) {
            m_memoryBusy = false;
            m_memoryError = !error.isEmpty() ? error : data.value("error").toString(QStringLiteral("Не удалось сохранить настройку памяти."));
            emit memoriesChanged(); emit memoryStateChanged(); return;
        }
        m_memoryNotice = QStringLiteral("Настройка памяти сохранена.");
        loadMemories();
    });
}
void BackendClient::clearConversationMemory() {
    if (m_archivedTurns < 0 || !beginMemoryOperation()) return;
    const QJsonObject body;
    request("/ai/clear-memory", &body, 5000, [this](const QJsonObject &data, const QString &error) {
        if (!error.isEmpty() || data.value("status").toString() != "success") {
            m_memoryBusy = false;
            m_memoryError = !error.isEmpty() ? error : data.value("error").toString(QStringLiteral("Не удалось очистить историю."));
            emit memoryStateChanged(); return;
        }
        m_memoryNotice = QStringLiteral("История разговоров очищена. Сохранённые факты остались.");
        loadMemories();
    });
}
void BackendClient::addMemory(const QString &text, const QString &kind) {
    const auto trimmed = text.trimmed();
    if (trimmed.isEmpty() || m_memoryBusy) return;
    if (trimmed.toUcs4().size() > 200) {
        m_memoryError = QStringLiteral("Запись должна быть не длиннее 200 символов.");
        emit memoryStateChanged(); return;
    }
    bool known = false;
    for (const auto &item : m_memoryKinds) if (item.toMap().value("id").toString() == kind) known = true;
    if (!known) {
        m_memoryError = QStringLiteral("Выберите категорию записи.");
        emit memoryStateChanged(); return;
    }
    if (!beginMemoryOperation()) return;
    const QJsonObject body{{"text", trimmed}, {"kind", kind}};
    request("/memories", &body, 5000, [this](const QJsonObject &data, const QString &error) {
        if (!error.isEmpty() || !data.value("success").toBool()) {
            m_memoryBusy = false;
            m_memoryError = !error.isEmpty() ? error : data.value("error").toString(QStringLiteral("Не удалось запомнить запись."));
            emit memoryStateChanged(); return;
        }
        m_memoryNotice = data.value("note").toString(QStringLiteral("Запомнил. Запись доступна и в основном лаунчере."));
        emit memoryAdded();
        loadMemories();
    });
}
void BackendClient::forgetMemory(const QString &id) {
    // Only single records currently present in this view; never a bulk endpoint.
    if (m_memoryBusy || !QRegularExpression("^[a-zA-Z0-9_-]+$").match(id).hasMatch()) return;
    bool known = false;
    for (const auto &item : m_memories) if (item.toMap().value("id").toString() == id) known = true;
    if (!known || !beginMemoryOperation()) return;
    request("/memories/" + id, nullptr, 5000, [this](const QJsonObject &data, const QString &error) {
        if (!error.isEmpty() || !data.value("success").toBool()) {
            m_memoryBusy = false;
            m_memoryError = !error.isEmpty() ? error : data.value("error").toString(QStringLiteral("Не удалось удалить запись."));
            emit memoryStateChanged(); return;
        }
        m_memoryNotice = QStringLiteral("Запись удалена.");
        loadMemories();
    }, true);
}
