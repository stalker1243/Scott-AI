#include "BackendClient.h"
#include "ApiError.h"
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
#include <QUuid>
#include <QDateTime>
#include <memory>

namespace {
bool chatIdValid(const QString &id) { return QRegularExpression("^[a-f0-9]{32}$").match(id).hasMatch(); }
constexpr qint64 MaxBytes = 20 * 1024 * 1024;
struct ChatTransfer {
    QByteArray buffer;
    QString text;
    QJsonObject result;
    QVariantList original;
    bool streaming = false, terminal = false, invalid = false, shown = false;
    qint64 bytes = 0;
};
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
    const auto id = chat.value("id").toString();
    if (id != m_chatId) { m_requestId.clear(); m_requestBody.clear(); m_recoveryChecks = 0; }
    m_chatId = id; m_chatTitle = chat.value("title").toString(); m_messages = rows;
    const auto pending = chat.value("pending_request").toObject();
    if (m_requestId.isEmpty() && chatIdValid(pending.value("id").toString()) && pending.value("question").isString()) {
        m_requestId = pending.value("id").toString(); m_requestChat = id;
        m_requestQuestion = pending.value("question").toString().left(12000);
        m_requestBody.clear(); m_recoveryChecks = 0;
        m_chatNotice = QStringLiteral("Сохранено незавершённое сообщение. Проверяем результат запроса.");
        emit restoreChatDraft(m_requestQuestion);
    }
    emit messagesChanged(); emit chatsChanged(); return true;
}

void BackendClient::reconcileChatRequest() {
    if (!m_online || m_busy || m_chatsBusy || m_reconciling || !m_receiptsSupported || m_requestId.isEmpty() || m_requestChat != m_chatId || m_recoveryChecks >= 12) return;
    const auto id = m_requestId, chat = m_requestChat;
    ++m_recoveryChecks; m_reconciling = true;
    request("/chats/" + chat + "/requests/" + id, nullptr, 5000, [this, id, chat](const QJsonObject &data, const QString &error) {
        m_reconciling = false;
        if (id != m_requestId || chat != m_chatId || !error.isEmpty()) return;
        const auto receipt = data.value("request").toObject();
        if (receipt.value("id").toString() != id) return;
        if (receipt.value("state").toString() == "completed" && data.value("chat").toObject().value("id").toString() == chat && acceptChat(data.value("chat").toObject())) {
            m_requestId.clear(); m_requestBody.clear(); m_error.clear();
            m_attachments.clear(); emit attachmentsChanged();
            m_chatNotice = QStringLiteral("Ответ восстановлен после переподключения. Запрос повторно не выполнялся.");
            emit chatRecovered(m_requestQuestion);
        } else if (receipt.value("state").toString() != "running") {
            m_chatNotice = receipt.value("message").toString();
        }
        emit chatsChanged(); emit stateChanged();
    });
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
            if (remove) { m_requestId.clear(); m_requestBody.clear(); }
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
        m_error.clear(); m_chatsBusy = true;
        m_creatingChatPreview = {{"role", "user"}, {"text", question}, {"attachments", m_attachments}};
        emit messagesChanged(); emit chatSubmitted(question);
        emit chatsChanged(); const QJsonObject body;
        request("/chats", &body, 10000, [this, question, image, command](const QJsonObject &data, const QString &error) {
            m_chatsBusy = false;
            if (!error.isEmpty() || !data.value("success").toBool() || !acceptChat(data.value("chat").toObject())) {
                m_creatingChatPreview.clear(); emit messagesChanged(); emit restoreChatDraft(question);
                m_error = error.isEmpty() ? QStringLiteral("Не удалось создать диалог") : error; emit stateChanged(); emit chatsChanged(); return;
            }
            sendChatMessage(question, image, command);
            if (!m_creatingChatPreview.isEmpty()) {
                // Validation can fail after creating the chat (e.g. a file
                // disappeared). Preserve the draft without a phantom message.
                m_creatingChatPreview.clear(); emit messagesChanged(); emit restoreChatDraft(question);
            }
        }); return;
    }
    auto *multipart = new QHttpMultiPart(QHttpMultiPart::FormDataType);
    auto field = [multipart](const QByteArray &name, const QByteArray &value) { QHttpPart part; part.setHeader(QNetworkRequest::ContentDispositionHeader, "form-data; name=\"" + name + "\""); part.setBody(value); multipart->append(part); };
    const QString mode = image ? "image" : command ? "command" : "chat";
    QJsonArray fileKeys;
    for (const auto &entry : m_attachments) {
        const auto item = entry.toMap(); const QFileInfo info(item.value("path").toString());
        fileKeys.append(QJsonObject{{"path", info.absoluteFilePath()}, {"size", info.size()}, {"modified", info.lastModified().toMSecsSinceEpoch()}});
    }
    const auto key = QJsonDocument(QJsonObject{{"question", question}, {"mode", mode}, {"files", fileKeys}}).toJson(QJsonDocument::Compact);
    const bool retry = !m_requestId.isEmpty() && m_requestChat == m_chatId && m_requestQuestion == question && (m_requestBody.isEmpty() || m_requestBody == key);
    if (retry && !m_receiptsSupported) {
        delete multipart;
        m_error = QStringLiteral("Результат предыдущего запроса не подтверждён. Проверьте историю и обновите backend перед повторной отправкой.");
        emit stateChanged(); return;
    }
    qint64 total = 0;
    for (const auto &entry : m_attachments) {
        const auto item = entry.toMap(); auto *file = new QFile(item.value("path").toString(), multipart);
        if (!file->open(QIODevice::ReadOnly) || (total += file->size()) > MaxBytes) { delete multipart; m_error = QStringLiteral("Вложение изменилось или недоступно. Прикрепите файл заново."); emit stateChanged(); return; }
        auto name = item.value("name").toString(); name.replace('"', '_'); name.replace('\r', '_'); name.replace('\n', '_');
        QHttpPart part; part.setHeader(QNetworkRequest::ContentDispositionHeader, "form-data; name=\"files\"; filename=\"" + name.toUtf8() + "\"");
        part.setHeader(QNetworkRequest::ContentTypeHeader, "application/octet-stream"); part.setBodyDevice(file); multipart->append(part);
    }
    if (!retry) { m_requestId = QUuid::createUuid().toString(QUuid::WithoutBraces).remove('-'); m_recoveryChecks = 0; }
    m_requestChat = m_chatId; m_requestQuestion = question; m_requestBody = key;
    field("question", question.toUtf8()); field("mode", mode.toUtf8()); field("stream", "true"); field("request_id", m_requestId.toUtf8());
    m_busy = true; m_error.clear(); m_chatNotice.clear(); emit stateChanged();
    auto url = m_base; url.setPath("/chats/" + m_chatId + "/messages"); QNetworkRequest req(url);
    req.setRawHeader("Accept", "text/event-stream, application/json");
    // A plain chat request may generate an image after backend classification.
    req.setTransferTimeout(command ? 150000 : 240000); req.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    auto *reply = m_network.post(req, multipart); multipart->setParent(reply);
    m_chatReply = reply;
    auto state = std::make_shared<ChatTransfer>(); state->original = m_messages;
    // Show the outgoing message before the first token or HTTP result. The
    // server's final chat replaces this preview; it is never submitted twice.
    const bool alreadyShown = !m_creatingChatPreview.isEmpty();
    m_creatingChatPreview.clear();
    m_messages.append(QVariantMap{{"role", "user"}, {"text", question}, {"attachments", m_attachments}});
    emit messagesChanged(); if (!alreadyShown) emit chatSubmitted(question);
    auto *paint = new QTimer(reply); paint->setSingleShot(true); paint->setInterval(40);
    connect(paint, &QTimer::timeout, this, [this, state] {
        if (state->invalid || state->terminal || state->text.isEmpty()) return;
        if (!state->shown) {
            m_messages.append(QVariantMap{{"role", "assistant"}, {"text", QString{}}, {"attachments", QVariantList{}}});
            state->shown = true;
        }
        auto row = m_messages.last().toMap(); row["text"] = state->text; m_messages.last() = row;
        emit messagesChanged();
    });
    auto consume = [this, reply, state, paint] {
        if (!reply->header(QNetworkRequest::ContentTypeHeader).toString().startsWith("text/event-stream")) return;
        state->streaming = true;
        const auto bytes = reply->readAll(); state->bytes += bytes.size(); state->buffer += bytes;
        if (state->bytes > 32 * 1024 * 1024 || state->buffer.size() > 8 * 1024 * 1024) { state->invalid = true; reply->abort(); return; }
        state->buffer.replace("\r\n", "\n");
        qsizetype split;
        while ((split = state->buffer.indexOf("\n\n")) >= 0) {
            const auto frame = state->buffer.left(split); state->buffer.remove(0, split + 2);
            QByteArray kind, data;
            for (const auto &line : frame.split('\n')) {
                if (line.startsWith("event:")) kind = line.mid(6).trimmed();
                else if (line.startsWith("data:")) { if (!data.isEmpty()) data += '\n'; data += line.mid(5).trimmed(); }
            }
            if (data.isEmpty()) continue; // Heartbeat/comment.
            QJsonParseError parse; const auto value = QJsonDocument::fromJson(data, &parse);
            if (state->terminal || parse.error != QJsonParseError::NoError || !value.isObject()) { state->invalid = true; reply->abort(); return; }
            const auto object = value.object();
            if (kind == "delta" && object.value("text").isString()) {
                state->text += object.value("text").toString();
                if (state->text.size() > 128 * 1024) { state->invalid = true; reply->abort(); return; }
                if (!paint->isActive()) paint->start();
            } else if (kind == "done" || kind == "error") {
                state->result = object; state->terminal = true; paint->stop();
            } else { state->invalid = true; reply->abort(); return; }
        }
    };
    connect(reply, &QNetworkReply::readyRead, this, consume);
    connect(reply, &QNetworkReply::finished, this, [this, reply, state, consume, paint] {
        consume(); paint->stop(); m_chatReply.clear(); m_busy = false;
        QJsonParseError parse; const auto data = state->streaming ? state->result : QJsonDocument::fromJson(reply->readAll(), &parse).object();
        if (reply->error() == QNetworkReply::NoError && !state->invalid && (!state->streaming || state->terminal) && parse.error == QJsonParseError::NoError && data.value("success").toBool() && data.value("chat").toObject().value("id").toString() == m_chatId && acceptChat(data.value("chat").toObject())) {
            m_attachments.clear(); emit attachmentsChanged(); QStringList notes;
            m_requestId.clear(); m_requestBody.clear();
            for (const auto &note : data.value("notes").toArray()) notes.append(note.toString()); m_chatNotice = notes.join("\n");
            emit chatSent(); refreshChats(); refreshBrowser();
        } else {
            state->invalid = true;
            m_messages = state->original; emit messagesChanged();
            emit restoreChatDraft(m_requestQuestion);
            m_error = reply->property("scottUserCancelled").toBool()
                ? QStringLiteral("Ответ остановлен. Проверьте историю перед повторной отправкой.") : apiErrorMessage(data);
            if(m_error.isEmpty())m_error=backendNetworkError(reply->error());
        }
        reply->deleteLater(); emit stateChanged(); emit chatsChanged();
    });
}

void BackendClient::cancelChatMessage() {
    if (m_chatReply) { m_chatReply->setProperty("scottUserCancelled", true); m_chatReply->abort(); }
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
