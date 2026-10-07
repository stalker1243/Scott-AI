#include "BackendClient.h"
#include <QtTest>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonArray>
#include <memory>

class ChatTests : public QObject {
    Q_OBJECT
private slots:
    void persistentChatAndMultipartFailures() {
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        const QString id(32, '1'); QString title = "Plan"; QJsonArray messages;
        bool fail = true, documentsSupported = true; int uploads = 0; QByteArray uploadBody;
        auto chat = [&] { return QJsonObject{{"id", id}, {"title", title}, {"messages", messages}}; };
        connect(&server, &QTcpServer::newConnection, this, [&] {
            auto *socket = server.nextPendingConnection(); auto buffer = std::make_shared<QByteArray>();
            connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            connect(socket, &QTcpSocket::readyRead, socket, [&, socket, buffer] {
                *buffer += socket->readAll(); const auto split = buffer->indexOf("\r\n\r\n"); if (split < 0) return;
                int length = 0;
                for (const auto &line : buffer->left(split).split('\n')) if (line.toLower().startsWith("content-length:")) length = line.mid(15).trimmed().toInt();
                if (buffer->size() < split + 4 + length) return;
                const auto path = buffer->split(' ').value(1); const auto method = buffer->split(' ').value(0); int code = 200; QJsonObject response;
                if (path == "/health") response = {{"status", "online"}};
                else if (path == "/chats/capabilities") response = {{"success", true}, {"provider", "OpenRouter"}, {"model", "demo"}, {"enabled", true}, {"capabilities", QJsonObject{{"known", true}, {"documents", documentsSupported}, {"images", false}, {"video", false}, {"image_generation", false}}}};
                else if (path == "/chats") response = {{"success", true}, {"chats", QJsonArray{QJsonObject{{"id", id}, {"title", title}, {"count", messages.size()}}}}};
                else if (path.endsWith("/messages") && method == "POST") {
                    ++uploads; uploadBody = buffer->mid(split + 4, length);
                    if (fail) { code = 400; response = {{"detail", "Unsupported attachment"}}; }
                    else {
                        messages = QJsonArray{QJsonObject{{"role", "user"}, {"text", "Review"}, {"attachments", QJsonArray{}}}, QJsonObject{{"role", "assistant"}, {"text", "Done"}, {"attachments", QJsonArray{}}, {"model", "demo"}}};
                        response = {{"success", true}, {"chat", chat()}};
                    }
                } else if (path.endsWith("/messages") && method == "DELETE") { messages = {}; response = {{"success", true}, {"chat", chat()}}; }
                else if (path == "/chats/" + id.toUtf8()) {
                    if (method == "PATCH") title = QJsonDocument::fromJson(buffer->mid(split + 4, length)).object().value("title").toString();
                    response = {{"success", true}, {"chat", chat()}};
                }
                const auto bytes = QJsonDocument(response).toJson(QJsonDocument::Compact);
                socket->write("HTTP/1.1 " + QByteArray::number(code) + " Result\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: " + QByteArray::number(bytes.size()) + "\r\n\r\n" + bytes); socket->disconnectFromHost(); buffer->clear();
            });
        });
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(server.serverPort())));
        client.refresh(); QTRY_VERIFY(client.online()); client.refreshChats(); QTRY_COMPARE(client.chatId(), id); QTRY_VERIFY(!client.chatsBusy());
        QTemporaryDir directory; QVERIFY(directory.isValid()); const auto path = directory.filePath(QStringLiteral("заметка.txt"));
        QFile file(path); QVERIFY(file.open(QIODevice::WriteOnly)); file.write("document-content-123"); file.close();
        client.stageAttachments({QUrl::fromLocalFile(path)}); QCOMPARE(client.attachments().size(), 1);
        client.sendChatMessage("Draw", true); QVERIFY(!client.error().isEmpty()); QVERIFY(client.error().contains(QStringLiteral("генерация"))); QCOMPARE(uploads, 0);
        const auto photo = directory.filePath("photo.png"); QFile photoFile(photo); QVERIFY(photoFile.open(QIODevice::WriteOnly)); photoFile.write("photo"); photoFile.close();
        client.stageAttachments({QUrl::fromLocalFile(photo)}); QVERIFY(client.error().contains(QStringLiteral("фотографий"))); QCOMPARE(client.attachments().size(), 1);
        QSignalSpy sent(&client, &BackendClient::chatSent);
        client.sendChatMessage("Review"); client.sendChatMessage("Duplicate"); QTRY_VERIFY(!client.busy());
        QCOMPARE(uploads, 1); QVERIFY(uploadBody.contains("document-content-123")); QVERIFY(uploadBody.contains(QStringLiteral("заметка.txt").toUtf8()));
        QCOMPARE(client.attachments().size(), 1); QVERIFY(!client.error().isEmpty()); QCOMPARE(sent.count(), 0);
        fail = false; client.sendChatMessage("Review"); QTRY_COMPARE(sent.count(), 1); QTRY_VERIFY(!client.chatsBusy());
        QCOMPARE(client.attachments().size(), 0); QCOMPARE(client.messages().size(), 2); QCOMPARE(uploads, 2);
        client.renameChat("Renamed"); QTRY_COMPARE(client.chatTitle(), "Renamed"); QTRY_VERIFY(!client.chatsBusy());
        client.clearSavedChat(); QTRY_COMPARE(client.messages().size(), 0); QTRY_VERIFY(!client.chatsBusy());
        client.stageAttachments({QUrl("https://example.com/file.txt")}); QCOMPARE(client.attachments().size(), 0);
        client.stageAttachments({QUrl::fromLocalFile(path)}); QCOMPARE(client.attachments().size(), 1); client.removeAttachment(0); QCOMPARE(client.attachments().size(), 0);
        client.stageAttachments({QUrl::fromLocalFile(path)}); documentsSupported = false; client.refreshChatCapabilities();
        QTRY_VERIFY(!client.chatCapabilities().value("capabilities").toMap().value("documents").toBool());
        client.sendChatMessage("Review after model change"); QVERIFY(client.error().contains(QStringLiteral("файлами")));
        QCOMPARE(uploads, 2); QCOMPARE(client.attachments().size(), 1);
    }
};
QTEST_GUILESS_MAIN(ChatTests)
#include "ChatTests.moc"
