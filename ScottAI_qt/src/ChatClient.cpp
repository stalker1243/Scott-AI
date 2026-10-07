#include "BackendClient.h"
#include <QFileDialog>
#include <QFile>
#include <QFileInfo>
#include <QHttpMultiPart>
#include <QJsonDocument>
#include <QJsonArray>
#include <QNetworkReply>
#include <QSaveFile>
#include <QRegularExpression>
#include <QMimeDatabase>

namespace {
bool chatIdValid(const QString &id) { return QRegularExpression("^[a-f0-9]{32}$").match(id).hasMatch(); }
constexpr qint64 MaxBytes = 20 * 1024 * 1024;
}

bool BackendClient::acceptChat(const QJsonObject &chat) {
    if (!chatIdValid(chat.value("id").toString()) || !chat.value("title").isString() || !chat.value("messages").isArray()) return false;
    QVariantList rows;
    for (const auto &value : chat.value("messages").toArray()) {
        const auto row = value.toObject();
        if (!QStringList{"user", "assistant"}.contains(row.value("role").toString()) || !row.value("text").isString() || !row.value("attachments").isArray()) return false;
        auto message = row.toVariantMap(); QVariantList media;
        for (const auto &entry : row.value("attachments").toArray()) {
            auto asset = entry.toObject().toVariantMap(); const auto path = asset.value("url").toString();
            if (!QRegularExpression("^/chats/assets/[a-f0-9]{32}$").match(path).hasMatch()) return false;
            auto url = m_base; url.setPath(path); asset["url"] = url.toString(); media.append(asset);
        }
        message["attachments"] = media; rows.append(message);
    }
    m_chatId = chat.value("id").toString(); m_chatTitle = chat.value("title").toString(); m_messages = rows;
    emit messagesChanged(); emit chatsChanged(); return true;
}

void BackendClient::refreshChatCapabilities() {
    if (!m_online) return;
    const auto generation = ++m_chatCapabilitiesGeneration;
    request("/chats/capabilities", nullptr, 25000, [this, generation](const QJsonObject &data, const QString &error) {
        if (generation != m_chatCapabilitiesGeneration) return;
        m_chatCapabilities = error.isEmpty() && data.value("success").toBool() && data.value("capabilities").isObject() ? data.toVariantMap() : QVariantMap{};
        emit chatsChanged();
    });
}

void BackendClient::refreshChats() {
    if (!m_online || m_busy || m_chatsBusy) return;
    m_chatsBusy = true; emit chatsChanged();
    request("/chats", nullptr, 6000, [this](const QJsonObject &data, const QString &error) {
        m_chatsBusy = false;
        if (error.isEmpty() && data.value("success").toBool() && data.value("chats").isArray()) {
            QVariantList rows;
            for (const auto &entry : data.value("chats").toArray()) {
                const auto row = entry.toObject();
                if (!chatIdValid(row.value("id").toString()) || !row.value("title").isString()) { m_error = QStringLiteral("Некорректная история диалогов"); emit stateChanged(); return; }
                rows.append(row.toVariantMap());
            }
            m_chats = rows; m_chatsReady = true;
            if (m_chatId.isEmpty() && !rows.isEmpty()) openChat(rows.first().toMap().value("id").toString());
        } else { m_error = error.isEmpty() ? QStringLiteral("Не удалось загрузить историю") : error; emit stateChanged(); }
        emit chatsChanged();
    });
    refreshChatCapabilities();
}

void BackendClient::chatMutation(const QString &path, const QJsonObject *body, bool remove, bool patch) {
    if (!m_online || m_busy || m_chatsBusy) return;
    m_chatsBusy = true; m_error.clear(); emit chatsChanged(); emit stateChanged();
    request(path, body, 10000, [this, remove, path](const QJsonObject &data, const QString &error) {
        m_chatsBusy = false;
        if (!error.isEmpty() || !data.value("success").toBool()) m_error = error.isEmpty() ? QStringLiteral("Не удалось изменить диалог") : error;
        else if (data.value("chat").isObject()) {
            if (!acceptChat(data.value("chat").toObject())) m_error = QStringLiteral("Некорректный диалог от backend");
        } else if (remove && !path.endsWith("/messages")) {
            m_chatId.clear(); m_chatTitle.clear(); m_messages.clear(); m_attachments.clear();
            emit attachmentsChanged(); emit messagesChanged();
        }
        emit chatsChanged(); emit stateChanged(); if (m_error.isEmpty()) refreshChats();
    }, remove, false, patch);
}
void BackendClient::newChat() { const QJsonObject body; chatMutation("/chats", &body); }
void BackendClient::openChat(const QString &id) {
    if (!chatIdValid(id) || !m_online || m_busy || m_chatsBusy) return;
    chatMutation("/chats/" + id, nullptr);
}
void BackendClient::renameChat(const QString &title) {
    const auto text = title.trimmed(); if (!chatIdValid(m_chatId) || text.isEmpty() || text.size() > 100) return;
    const QJsonObject body{{"title", text}}; chatMutation("/chats/" + m_chatId, &body, false, true);
}
void BackendClient::deleteChat(bool all) { if (all || chatIdValid(m_chatId)) chatMutation(all ? "/chats" : "/chats/" + m_chatId, nullptr, true); }
void BackendClient::clearSavedChat() { if (chatIdValid(m_chatId)) chatMutation("/chats/" + m_chatId + "/messages", nullptr, true); }

void BackendClient::chooseAttachments(bool photos) {
    if (m_busy) return;
    const auto files = QFileDialog::getOpenFileNames(nullptr, photos ? QStringLiteral("Прикрепить фото") : QStringLiteral("Прикрепить файлы"), {}, photos ? QStringLiteral("Изображения (*.png *.jpg *.jpeg *.webp *.bmp *.gif)") : QStringLiteral("Документы, код и медиа (*.txt *.md *.pdf *.docx *.csv *.json *.xml *.yml *.yaml *.ini *.log *.py *.js *.ts *.cs *.cpp *.c *.h *.java *.go *.rs *.html *.css *.sql *.ps1 *.png *.jpg *.jpeg *.webp *.bmp *.gif *.mp4 *.webm *.mov *.mpeg);;Все файлы (*)"));
    QList<QUrl> urls; for (const auto &path : files) urls.append(QUrl::fromLocalFile(path)); stageAttachments(urls);
}
QString BackendClient::unsupportedChatFeature(const QString &feature) const {
    const auto caps = m_chatCapabilities.value("capabilities").toMap();
    if (caps.value(feature).toBool()) return {};
    const QMap<QString, QString> names{{"documents", QStringLiteral("работа с файлами")}, {"images", QStringLiteral("анализ фотографий")}, {"video", QStringLiteral("анализ видео")}, {"image_generation", QStringLiteral("генерация изображений")}};
    const auto model = m_chatCapabilities.value("model").toString();
    return caps.value("known").toBool()
        ? QStringLiteral("Модель «%1» не поддерживает: %2. Выберите подходящую модель на вкладке «Модели».").arg(model, names.value(feature))
        : QStringLiteral("Для модели «%1» поддержка функции «%2» не подтверждена. Проверьте её на вкладке «Модели».").arg(model, names.value(feature));
}
void BackendClient::stageAttachments(const QList<QUrl> &urls) {
    if (m_busy) return;
    auto candidate = m_attachments; qint64 total = 0; for (const auto &entry : candidate) total += entry.toMap().value("size").toLongLong();
    for (const auto &url : urls) {
        if (!url.isLocalFile()) { m_error = QStringLiteral("Прикрепите локальный файл"); emit stateChanged(); return; }
        const QFileInfo info(url.toLocalFile()); bool duplicate = false;
        for (const auto &entry : candidate) if (entry.toMap().value("path").toString() == info.absoluteFilePath()) duplicate = true;
        if (duplicate) continue;
        const auto mime = QMimeDatabase().mimeTypeForFile(info).name();
        const auto caps = m_chatCapabilities.value("capabilities").toMap();
        const auto feature = mime.startsWith("image/") ? "images" : mime.startsWith("video/") ? "video" : "documents";
        if (caps.contains(feature) && !caps.value(feature).toBool()) {
            m_error = unsupportedChatFeature(feature); emit stateChanged(); return;
        }
        if (!info.isFile() || !info.isReadable() || candidate.size() >= 4 || total + info.size() > MaxBytes) {
            m_error = QStringLiteral("До четырёх файлов, общий размер — до 20 МБ. Проверьте доступ к файлу."); emit stateChanged(); return;
        }
        total += info.size();
        candidate.append(QVariantMap{{"name", info.fileName()}, {"path", info.absoluteFilePath()}, {"url", url.toString()}, {"size", info.size()}, {"mime", mime}});
    }
    m_attachments = candidate; m_error.clear(); emit attachmentsChanged(); emit stateChanged();
}
void BackendClient::removeAttachment(int index) { if (!m_busy && index >= 0 && index < m_attachments.size()) { m_attachments.removeAt(index); emit attachmentsChanged(); } }

void BackendClient::sendChatMessage(const QString &text, bool image, bool command) {
    const auto question = text.trimmed();
    if (!m_online || m_busy || m_chatsBusy || (question.isEmpty() && m_attachments.isEmpty())) return;
    if (!command) {
        QString issue;
        if (image) issue = unsupportedChatFeature("image_generation");
        for (const auto &entry : m_attachments) {
            const auto mime = entry.toMap().value("mime").toString();
            const auto feature = mime.startsWith("image/") ? "images" : mime.startsWith("video/") ? "video" : "documents";
            const auto warning = unsupportedChatFeature(feature);
            if (!warning.isEmpty()) { issue = warning; break; }
        }
        if (!issue.isEmpty()) { m_error = issue; emit stateChanged(); return; }
    }
    if (m_chatId.isEmpty()) {
        m_chatsBusy = true; emit chatsChanged(); const QJsonObject body;
        request("/chats", &body, 10000, [this, question, image, command](const QJsonObject &data, const QString &error) {
            m_chatsBusy = false;
            if (!error.isEmpty() || !data.value("success").toBool() || !acceptChat(data.value("chat").toObject())) { m_error = error.isEmpty() ? QStringLiteral("Не удалось создать диалог") : error; emit stateChanged(); emit chatsChanged(); return; }
            sendChatMessage(question, image, command);
        }); return;
    }
    auto *multipart = new QHttpMultiPart(QHttpMultiPart::FormDataType);
    auto field = [multipart](const QByteArray &name, const QByteArray &value) { QHttpPart part; part.setHeader(QNetworkRequest::ContentDispositionHeader, "form-data; name=\"" + name + "\""); part.setBody(value); multipart->append(part); };
    field("question", question.toUtf8()); field("mode", image ? "image" : command ? "command" : "chat");
    qint64 total = 0;
    for (const auto &entry : m_attachments) {
        const auto item = entry.toMap(); auto *file = new QFile(item.value("path").toString(), multipart);
        if (!file->open(QIODevice::ReadOnly) || (total += file->size()) > MaxBytes) { delete multipart; m_error = QStringLiteral("Вложение изменилось или недоступно. Прикрепите файл заново."); emit stateChanged(); return; }
        auto name = item.value("name").toString(); name.replace('"', '_'); name.replace('\r', '_'); name.replace('\n', '_');
        QHttpPart part; part.setHeader(QNetworkRequest::ContentDispositionHeader, "form-data; name=\"files\"; filename=\"" + name.toUtf8() + "\"");
        part.setHeader(QNetworkRequest::ContentTypeHeader, "application/octet-stream"); part.setBodyDevice(file); multipart->append(part);
    }
    m_busy = true; m_error.clear(); m_chatNotice.clear(); emit stateChanged();
    auto url = m_base; url.setPath("/chats/" + m_chatId + "/messages"); QNetworkRequest req(url);
    req.setTransferTimeout(image ? 240000 : 150000); req.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    auto *reply = m_network.post(req, multipart); multipart->setParent(reply);
    connect(reply, &QNetworkReply::finished, this, [this, reply] {
        m_busy = false; QJsonParseError parse; const auto data = QJsonDocument::fromJson(reply->readAll(), &parse).object();
        if (reply->error() == QNetworkReply::NoError && parse.error == QJsonParseError::NoError && data.value("success").toBool() && acceptChat(data.value("chat").toObject())) {
            m_attachments.clear(); emit attachmentsChanged(); QStringList notes;
            for (const auto &note : data.value("notes").toArray()) notes.append(note.toString()); m_chatNotice = notes.join("\n");
            emit chatSent(); refreshChats();
        } else m_error = data.value("detail").toString(data.value("error").toString(QStringLiteral("Не удалось отправить: ") + reply->errorString()));
        reply->deleteLater(); emit stateChanged(); emit chatsChanged();
    });
}

void BackendClient::saveChatImage(const QString &value) {
    const QUrl url(value);
    if (url.scheme() != m_base.scheme() || url.host() != m_base.host() || url.port() != m_base.port() || !QRegularExpression("^/chats/assets/[a-f0-9]{32}$").match(url.path()).hasMatch()) return;
    const auto path = QFileDialog::getSaveFileName(nullptr, QStringLiteral("Сохранить изображение"), "Scott-image.png", "PNG (*.png)");
    if (path.isEmpty()) return;
    QNetworkRequest req(url); req.setTransferTimeout(15000); req.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    auto *reply = m_network.get(req);
    connect(reply, &QNetworkReply::downloadProgress, reply, [reply](qint64 size, qint64) { if (size > MaxBytes) reply->abort(); });
    connect(reply, &QNetworkReply::finished, this, [this, reply, path] {
        QSaveFile file(path);
        if (reply->error() != QNetworkReply::NoError || !file.open(QIODevice::WriteOnly) || file.write(reply->readAll()) < 0 || !file.commit()) { m_error = QStringLiteral("Не удалось сохранить изображение"); emit stateChanged(); }
        reply->deleteLater();
    });
}
