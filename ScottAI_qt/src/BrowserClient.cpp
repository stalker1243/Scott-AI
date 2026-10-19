#include "BackendClient.h"

void BackendClient::acceptBrowser(const QJsonObject &data) {
    if (!data.value("state").isString()) return;
    const auto state = data.toVariantMap();
    const bool changed = !m_browserReady || state != m_browserState;
    m_browserState = state;
    m_browserReady = true;
    const auto status = state.value("state").toString();
    if (status == "running" || status == "cancelling") m_browserPoll.start();
    else m_browserPoll.stop();
    if (changed) emit browserChanged();
}
void BackendClient::refreshBrowser() {
    if (!m_online || m_browserFetching || m_browserPending) return;
    m_browserFetching = true;
    const auto revision = m_browserRevision;
    request("/browser", nullptr, 6000, [this, revision](const QJsonObject &data, const QString &error) {
        m_browserFetching = false;
        if (revision != m_browserRevision) return;
        if (error.isEmpty() && data.value("state").isString()) acceptBrowser(data);
        else {
            m_browserReady = false;
            m_browserState.insert("message", QStringLiteral("Состояние браузера недоступно. Обновите подключение."));
            m_browserPoll.stop(); emit browserChanged();
        }
    });
}
void BackendClient::browserMutation(const QString &path, const QJsonObject &body) {
    if (!m_online || !m_browserReady || m_browserPending) return;
    m_browserPending = true;
    m_browserReady = false;
    const auto revision = ++m_browserRevision;
    m_browserState.insert("state", path.endsWith("cancel") ? "cancelling" : "running");
    m_browserState.insert("message", path.endsWith("cancel") ? QStringLiteral("Останавливаем действие") : QStringLiteral("Передаём команду браузеру"));
    emit browserChanged();
    request(path, &body, 15000, [this, revision](const QJsonObject &data, const QString &error) {
        m_browserPending = false;
        if (revision != m_browserRevision || !m_online) return;
        if (error.isEmpty() && data.value("state").isString()) acceptBrowser(data);
        else {
            m_browserState.insert("state", "failed");
            m_browserState.insert("message", error.isEmpty() ? QStringLiteral("Некорректный ответ браузера") : error);
            emit browserChanged(); refreshBrowser();
        }
    });
}
void BackendClient::startBrowser(const QString &action, const QString &query, int index) {
    const auto state = m_browserState.value("state").toString();
    if (state == "running" || state == "cancelling") return;
    QJsonObject body{{"action", action}, {"query", query}};
    if (index >= 0) {
        body.insert("index", index);
        body.insert("results_id", m_browserState.value("results_id").toString());
    }
    browserMutation("/browser", body);
}
void BackendClient::cancelBrowser() {
    if (m_browserState.value("state").toString() != "running") return;
    browserMutation("/browser/cancel", {{"id", m_browserState.value("id").toString()}});
}
void BackendClient::setBrowserEnabled(bool enabled) {
    const auto state = m_browserState.value("state").toString();
    if (state == "running" || state == "cancelling") return;
    browserMutation("/browser/settings", {{"enabled", enabled}});
}
