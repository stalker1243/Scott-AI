#include "BackendClient.h"
#include "ProtocolValidation.h"
#include <QJsonDocument>

static QString component(const QString &id) { return QString::fromUtf8(QUrl::toPercentEncoding(id)); }
bool BackendClient::beginProtocolOperation() {
    if (!m_online || m_protocolsBusy || !m_protocolsReady) return false;
    m_protocolsBusy = true; m_protocolsError.clear(); m_protocolsNotice.clear(); emit protocolsStateChanged();
    return true;
}
void BackendClient::refreshProtocols() {
    if (!m_online || m_protocolsBusy) return;
    m_protocolsBusy = true; m_protocolsError.clear(); emit protocolsStateChanged();
    request("/protocols", nullptr, 10000, [this](const QJsonObject &data, const QString &error) {
        bool valid = m_online && error.isEmpty() && data.value("success").toBool() && data.value("protocols").isArray();
        QSet<QString> ids;
        for (const auto &value : data.value("protocols").toArray()) {
            const auto record = value.toObject(); const auto id = record.value("id").toString();
            valid &= protocolRecordValid(record) && !ids.contains(id); ids.insert(id);
        }
        m_protocolsBusy = false; m_protocolsReady = valid;
        if (valid) { m_protocols = data.value("protocols").toArray().toVariantList(); emit protocolsChanged(); }
        else m_protocolsError = !error.isEmpty() ? error : data.value("error").toString(QStringLiteral("Не удалось загрузить протоколы."));
        emit protocolsStateChanged();
        if (valid) pollProtocolJob();
    });
}
void BackendClient::saveProtocol(const QString &id, const QString &json) {
    const auto draft = QJsonDocument::fromJson(json.toUtf8()).object();
    if (!protocolDraftValid(draft)) {
        m_protocolsError = QStringLiteral("Проверьте имя, шаги, повторы и длину полей."); emit protocolsStateChanged(); return;
    }
    if (!id.isEmpty()) {
        bool known = false; for (const auto &value : m_protocols) known |= value.toMap().value("id").toString() == id;
        if (!known) return;
    }
    if (!beginProtocolOperation()) return;
    request(id.isEmpty() ? "/protocols" : "/protocols/id/" + component(id), &draft, 15000,
        [this, id](const QJsonObject &data, const QString &error) {
            m_protocolsBusy = false; const auto record = data.value("protocol").toObject();
            if (error.isEmpty() && data.value("success").toBool() && protocolRecordValid(record) && (id.isEmpty() || record.value("id").toString() == id)) {
                const auto saved = record.toVariantMap(); bool replaced = false;
                for (int i = 0; i < m_protocols.size(); ++i) if (m_protocols[i].toMap().value("id") == saved.value("id")) { m_protocols[i] = saved; replaced = true; break; }
                if (!replaced) m_protocols.prepend(saved);
                m_protocolsNotice = QStringLiteral("Протокол сохранён.");
                emit protocolsChanged(); emit protocolSaved(saved);
            } else m_protocolsError = !error.isEmpty() ? error : data.value("error").toString(QStringLiteral("Scott не подтвердил сохранение протокола."));
            emit protocolsStateChanged();
        }, false, false, !id.isEmpty());
}
void BackendClient::deleteProtocol(const QString &id) {
    bool known = false; for (const auto &value : m_protocols) known |= value.toMap().value("id").toString() == id;
    if (!known || (protocolRunning() && m_protocolJob.value("protocol_id").toString() == id) || !beginProtocolOperation()) return;
    request("/protocols/id/" + component(id), nullptr, 10000, [this, id](const QJsonObject &data, const QString &error) {
        m_protocolsBusy = false;
        if (error.isEmpty() && data.value("success").toBool()) {
            for (int i = m_protocols.size() - 1; i >= 0; --i) if (m_protocols[i].toMap().value("id").toString() == id) m_protocols.removeAt(i);
            m_protocolsNotice = QStringLiteral("Протокол удалён."); emit protocolsChanged(); emit protocolDeleted(id);
        } else m_protocolsError = !error.isEmpty() ? error : data.value("error").toString(QStringLiteral("Не удалось удалить протокол."));
        emit protocolsStateChanged();
    }, true);
}
void BackendClient::acceptProtocolJob(const QJsonObject &job) {
    const bool wasRunning = protocolRunning();
    m_protocolJob = job.toVariantMap(); m_protocolJobReady = true; m_protocolJobError.clear(); emit protocolJobChanged();
    if (protocolRunning()) m_protocolPoll.start(); else m_protocolPoll.stop();
    if (wasRunning && !protocolRunning()) refreshProtocols();
}
void BackendClient::pollProtocolJob() {
    if (!m_online || m_protocolJobBusy || m_protocolPolling) return;
    m_protocolPolling = true;
    const auto revision = m_protocolJobRevision;
    const auto id = m_protocolJob.value("id").toString();
    request(protocolRunning() && m_protocolJobReady && !id.isEmpty() ? "/protocols/jobs/" + component(id) : "/protocols/jobs/current", nullptr, 6000,
        [this, revision](const QJsonObject &data, const QString &error) {
            m_protocolPolling = false;
            if (revision != m_protocolJobRevision) return;
            if (m_online && error.isEmpty() && data.value("success").toBool() && data.value("job").isObject() && protocolJobValid(data.value("job").toObject()))
                acceptProtocolJob(data.value("job").toObject());
            else {
                m_protocolJobReady = false;
                m_protocolJobError = !error.isEmpty() ? error : data.value("error").toString(QStringLiteral("Не удалось проверить выполнение. Обновите список."));
                emit protocolJobChanged();
            }
        });
}
void BackendClient::runProtocol(const QString &id) {
    if (!m_online || !m_protocolsReady || m_protocolsBusy || !m_protocolJobReady || protocolRunning() || m_protocolJobBusy) return;
    bool enabled = false; for (const auto &value : m_protocols) { const auto record = value.toMap(); if (record.value("id").toString() == id) enabled = record.value("enabled").toBool(); }
    if (!enabled) return;
    ++m_protocolJobRevision;
    m_protocolJobBusy = true; m_protocolJobError.clear(); emit protocolJobChanged(); const QJsonObject body{};
    request("/protocols/id/" + component(id) + "/start", &body, 10000, [this](const QJsonObject &data, const QString &error) {
        m_protocolJobBusy = false;
        if (error.isEmpty() && data.value("success").toBool() && !data.value("job").toObject().isEmpty() && protocolJobValid(data.value("job").toObject())) acceptProtocolJob(data.value("job").toObject());
        else {
            m_protocolJobReady = false;
            m_protocolJobError = !error.isEmpty() ? error : data.value("error").toString(QStringLiteral("Не удалось начать выполнение."));
            emit protocolJobChanged();
            // A timed-out POST may have started: confirm actual state before allowing another run.
            m_protocolPoll.start();
        }
    });
}
void BackendClient::cancelProtocol() {
    if (!m_online || !protocolRunning() || m_protocolJobBusy) return;
    ++m_protocolJobRevision;
    m_protocolJobBusy = true; emit protocolJobChanged(); const QJsonObject body{};
    request("/protocols/jobs/" + component(m_protocolJob.value("id").toString()) + "/cancel", &body, 10000,
        [this](const QJsonObject &data, const QString &error) {
            m_protocolJobBusy = false;
            if (error.isEmpty() && data.value("success").toBool() && !data.value("job").toObject().isEmpty() && protocolJobValid(data.value("job").toObject())) acceptProtocolJob(data.value("job").toObject());
            else { m_protocolJobError = !error.isEmpty() ? error : QStringLiteral("Не удалось остановить запуск. Проверяю состояние…"); emit protocolJobChanged(); }
        });
}
