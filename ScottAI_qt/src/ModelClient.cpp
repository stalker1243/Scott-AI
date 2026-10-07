#include "BackendClient.h"
#include <QJsonArray>
#include <QRegularExpression>
#include <QSet>

namespace {
bool modelId(const QString &value) {
    return !value.isEmpty() && value.size() <= 200 &&
           !value.contains(QRegularExpression(QStringLiteral("[\\s\\x00-\\x1f]")));
}
bool readCatalog(const QJsonObject &data, QVariantList &providers, QVariantMap &state) {
    if (!data.value("providers").isArray() || !data.value("enabled").isBool() ||
        !data.value("active_model").isString() ||
        !(data.value("active_provider").isNull() || data.value("active_provider").isString())) return false;
    QSet<QString> ids;
    for (const auto &entry : data.value("providers").toArray()) {
        const auto row = entry.toObject(); const auto id = row.value("id").toString();
        if (id.isEmpty() || ids.contains(id) || !row.value("configured").isBool() || !row.value("models").isArray()) return false;
        ids.insert(id); QVariantList models; QSet<QString> modelIds;
        for (const auto &value : row.value("models").toArray()) {
            const auto model = value.toObject(); const auto name = model.value("id").toString();
            if (!modelId(name) || modelIds.contains(name)) return false;
            modelIds.insert(name);
            models.append(QVariantMap{{"id", name}, {"note", model.value("note").toString()}, {"free", model.value("free").toBool()}, {"capabilities", model.value("capabilities").toObject().toVariantMap()}});
        }
        // Keep metadata only; credentials never become a QML property.
        providers.append(QVariantMap{{"id", id}, {"note", row.value("note").toString()}, {"configured", row.value("configured").toBool()}, {"models", models}});
    }
    const auto active = data.value("active_provider").toString();
    if (ids.isEmpty() || (!active.isEmpty() && !ids.contains(active)) ||
        (data.value("enabled").toBool() && (active.isEmpty() || !modelId(data.value("active_model").toString())))) return false;
    state = {{"provider", active}, {"model", data.value("active_model").toString()}, {"enabled", data.value("enabled").toBool()}, {"capabilities", data.value("capabilities").toObject().toVariantMap()}};
    return true;
}
}

void BackendClient::refreshModels() {
    if (!m_online || m_modelsBusy) return;
    m_modelsBusy = true; m_modelsError.clear(); m_modelsNotice.clear(); emit modelsStateChanged();
    const auto generation = m_modelsGeneration;
    request("/ai/providers", nullptr, 60000, [this, generation](const QJsonObject &data, const QString &error) {
        m_modelsBusy = false;
        if (generation != m_modelsGeneration) {
            emit modelsStateChanged(); if (m_online) refreshModels(); return;
        }
        QVariantList providers; QVariantMap state;
        if (m_online && error.isEmpty() && readCatalog(data, providers, state)) {
            m_aiProviders = providers; m_aiState = state; m_modelsReady = true; emit modelsChanged();
        } else {
            m_modelsReady = false;
            m_modelsError = error.isEmpty() ? QStringLiteral("Не удалось загрузить настройки моделей. Обновите данные.") : error;
        }
        emit modelsStateChanged();
    });
}

void BackendClient::configureModel(const QString &provider, const QString &model, const QString &apiKey) {
    if (m_modelsBusy) return;
    m_modelsError.clear(); m_modelsNotice.clear();
    if (!m_online || !m_modelsReady) {
        m_modelsError = QStringLiteral("Подключите Scott и загрузите настройки моделей."); emit modelsStateChanged(); return;
    }
    const auto name = model.trimmed(); const auto key = apiKey.trimmed(); bool known = false, configured = false;
    for (const auto &entry : m_aiProviders) {
        const auto row = entry.toMap();
        if (row.value("id").toString() == provider) { known = true; configured = row.value("configured").toBool(); }
    }
    if (!known || !modelId(name) || key.size() > 4096 || key.contains(QRegularExpression(QStringLiteral("[\\x00-\\x1f]"))))
        m_modelsError = QStringLiteral("Проверьте провайдера, ID модели и API Token.");
    else if (!configured && key.isEmpty()) m_modelsError = QStringLiteral("Введите API Token для выбранного провайдера.");
    if (!m_modelsError.isEmpty()) { emit modelsStateChanged(); return; }
    QJsonObject body{{"provider", provider}, {"model", name}};
    if (!key.isEmpty()) body.insert("api_key", key);
    m_modelsBusy = true; emit modelsStateChanged();
    request("/ai/configure", &body, 90000, [this, provider, key](const QJsonObject &data, const QString &error) {
        m_modelsBusy = false;
        const auto actual = data.value("model").toString();
        if (error.isEmpty() && data.value("success").toBool() && data.value("provider").toString() == provider && modelId(actual)) {
            m_aiState = {{"provider", provider}, {"model", actual}, {"enabled", true}};
            for (auto &entry : m_aiProviders) {
                auto row = entry.toMap(); if (row.value("id").toString() == provider) { row["configured"] = true; entry = row; }
            }
            m_modelsNotice = data.value("note").toString(QStringLiteral("Настройки сохранены. Для новых ответов: %1 · %2.").arg(provider, actual));
            if (!key.isEmpty()) m_modelsNotice.replace(key, QStringLiteral("[скрыто]"));
            emit modelConfigured(); emit modelsChanged(); refreshChatCapabilities();
        } else {
            m_modelsError = !error.isEmpty() ? error : data.value("error").toString(data.value("message").toString(QStringLiteral("Scott не подтвердил смену модели. Обновите данные перед повтором.")));
            if (!key.isEmpty()) m_modelsError.replace(key, QStringLiteral("[скрыто]"));
        }
        emit modelsStateChanged();
    });
}
