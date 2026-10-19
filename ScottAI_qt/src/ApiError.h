#pragma once
#include <QJsonObject>
#include <QNetworkReply>
#include <QRegularExpression>

// Keep source text until display so a language switch also updates open notices.
inline QString apiErrorMessage(const QJsonObject &details) {
    QString text=details.value("message").toString(details.value("error").toString(details.value("detail").toString()));
    if(text.isEmpty())return {};
    text=text.left(4096);
    const auto hint=details.value("hint").toString();
    if(!hint.isEmpty())text+="\n"+hint.left(1024);
    const auto code=details.value("code").toString(),id=details.value("request_id").toString();
    if(QRegularExpression("\\ASCOTT-API-[0-9]{3}\\z").match(code).hasMatch()&&QRegularExpression("\\A[a-f0-9]{12}\\z").match(id).hasMatch())
        text+="\n"+code+" · "+id;
    return text;
}
inline QString backendNetworkError(QNetworkReply::NetworkError error) {
    if(error==QNetworkReply::NoError)
        return QStringLiteral("Получен неполный ответ. Проверьте историю перед повторной отправкой.");
    if(error==QNetworkReply::TimeoutError||error==QNetworkReply::OperationCanceledError)
        return QStringLiteral("Ответ занял слишком много времени. Проверьте историю перед повторной отправкой.");
    return QStringLiteral("Backend не отвечает. Проверьте подключение в настройках и откройте «Логи», если ошибка повторится.");
}
