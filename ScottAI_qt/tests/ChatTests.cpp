#include "BackendClient.h"
#include <QtTest>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonArray>
#include <QRegularExpression>
#include <memory>

class ChatTests : public QObject {
    Q_OBJECT
private slots:

    void outgoingVisibleWhileCreatingChat() {
        QTcpServer server;QVERIFY(server.listen(QHostAddress::LocalHost,0));
        QPointer<QTcpSocket> creation,upload;const QString id(32,'9');
        auto respond=[](QTcpSocket *socket,const QJsonObject &data){const auto body=QJsonDocument(data).toJson(QJsonDocument::Compact);socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "+QByteArray::number(body.size())+"\r\n\r\n"+body);socket->disconnectFromHost();};
        connect(&server,&QTcpServer::newConnection,this,[&]{
            auto *socket=server.nextPendingConnection();auto bytes=std::make_shared<QByteArray>();
            connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
            connect(socket,&QTcpSocket::readyRead,socket,[&,socket,bytes]{
                *bytes+=socket->readAll();if(!bytes->contains("\r\n\r\n"))return;
                const auto path=bytes->split(' ').value(1);
                if(path=="/chats"&&bytes->startsWith("POST")){creation=socket;return;}
                if(path.endsWith("/messages")){upload=socket;return;}
                respond(socket,path=="/health"?QJsonObject{{"status","online"}}:QJsonObject{});
            });
        });
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(server.serverPort())));
        QSignalSpy submitted(&client,&BackendClient::chatSubmitted),draft(&client,&BackendClient::restoreChatDraft);
        client.refresh();QTRY_VERIFY(client.online());client.sendChatMessage("First message");
        QCOMPARE(client.messages().size(),1);QCOMPARE(submitted.count(),1);QVERIFY(client.chatId().isEmpty());
        QTRY_VERIFY(creation);QTest::qWait(150);QCOMPARE(client.messages().size(),1);QVERIFY(!upload);
        respond(creation,{{"success",true},{"chat",QJsonObject{{"id",id},{"title","New"},{"messages",QJsonArray{}}}}});
        QTRY_VERIFY(upload);QCOMPARE(client.chatId(),id);QCOMPARE(submitted.count(),1);
        QCOMPARE(client.messages().size(),1);QCOMPARE(client.messages().first().toMap().value("text").toString(),QString("First message"));
        client.cancelChatMessage();QTRY_VERIFY(!client.busy());QCOMPARE(client.messages().size(),0);
        QCOMPARE(draft.count(),1);QCOMPARE(draft.first().first().toString(),QString("First message"));
    }
    void streamedReply_data() {
        QTest::addColumn<int>("ending");
        QTest::newRow("complete") << 0;
        QTest::newRow("safe-error") << 1;
        QTest::newRow("disconnect") << 2;
        QTest::newRow("cancel") << 3;
        QTest::newRow("malformed") << 4;
    }
    void streamedReply() {
        QFETCH(int, ending);
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        const QString id(32, '2'); QJsonArray saved;
        QPointer<QTcpSocket> upload;
        const auto chat = [&] { return QJsonObject{{"id", id}, {"title", "Stream"}, {"messages", saved}}; };
        const auto event = [](const QByteArray &kind, const QJsonObject &data) { return "event: " + kind + "\ndata: " + QJsonDocument(data).toJson(QJsonDocument::Compact) + "\n\n"; };
        connect(&server, &QTcpServer::newConnection, this, [&] {
            auto *socket = server.nextPendingConnection(); auto buffer = std::make_shared<QByteArray>();
            connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            connect(socket, &QTcpSocket::readyRead, socket, [&, socket, buffer] {
                *buffer += socket->readAll(); const auto split = buffer->indexOf("\r\n\r\n"); if (split < 0) return;
                int length = 0;
                for (const auto &line : buffer->left(split).split('\n')) if (line.toLower().startsWith("content-length:")) length = line.mid(15).trimmed().toInt();
                if (buffer->size() < split + 4 + length) return;
                const auto path = buffer->split(' ').value(1);
                if (path.endsWith("/messages")) {
                    QVERIFY(buffer->contains("name=\"stream\""));
                    upload = socket;
                    socket->write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n\r\n: heartbeat\n\n");
                    const auto bytes = event("delta", {{"text", QStringLiteral("Привет. ")}});
                    const auto cut = bytes.indexOf(QStringLiteral("П").toUtf8()) + 1;
                    socket->write(bytes.left(cut));
                    QTimer::singleShot(10, socket, [socket, bytes, cut] { socket->write(bytes.mid(cut)); });
                } else {
                    QJsonObject data{{"success", true}, {"chat", chat()}};
                    if (path == "/health") data = {{"status", "online"}, {"features", QJsonObject{{"request_receipts", 1}}}};
                    if (path == "/chats") data["chats"] = QJsonArray{chat()};
                    const auto bytes = QJsonDocument(data).toJson(QJsonDocument::Compact);
                    socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: " + QByteArray::number(bytes.size()) + "\r\n\r\n" + bytes);
                    socket->disconnectFromHost();
                }
                buffer->clear();
            });
        });
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(server.serverPort())));
        client.refresh(); QTRY_VERIFY(client.online()); client.newChat(); QTRY_COMPARE(client.chatId(), id); QTRY_VERIFY(!client.chatsBusy());
        QSignalSpy sent(&client, &BackendClient::chatSent), submitted(&client,&BackendClient::chatSubmitted), draft(&client,&BackendClient::restoreChatDraft);
        client.sendChatMessage("Question");
        QCOMPARE(client.messages().size(),1); // Before any event loop/network response.
        QCOMPARE(client.messages().first().toMap().value("role").toString(),QString("user"));
        QCOMPARE(client.messages().first().toMap().value("text").toString(),QString("Question"));
        QCOMPARE(submitted.count(),1);QCOMPARE(sent.count(),0);
        QTRY_VERIFY(upload); QTRY_COMPARE(client.messages().size(), 2);
        QCOMPARE(client.messages().last().toMap().value("text").toString(), QStringLiteral("Привет. "));
        QVERIFY(client.busy()); QCOMPARE(sent.count(), 0); // Actual first bytes before server completes.
        if (ending == 0) {
            saved = QJsonArray{QJsonObject{{"role", "user"}, {"text", "Question"}, {"attachments", QJsonArray{}}},
                               QJsonObject{{"role", "assistant"}, {"text", QStringLiteral("Привет. Готово.")}, {"attachments", QJsonArray{}}}};
            upload->write(event("done", {{"success", true}, {"chat", chat()}})); upload->disconnectFromHost();
        } else if (ending == 1) {
            upload->write(event("error", {{"success", false}, {"message", "Provider interrupted"}, {"code", "SCOTT-API-502"}})); upload->disconnectFromHost();
        } else if (ending == 3) client.cancelChatMessage();
        else if (ending == 4) { upload->write("event: delta\ndata: {broken}\n\n"); upload->disconnectFromHost(); }
        else upload->disconnectFromHost();
        QTRY_VERIFY(!client.busy());
        QTest::qWait(100); // A late paint timer must not resurrect a rolled-back row.
        if (ending == 0) { QCOMPARE(sent.count(), 1); QCOMPARE(client.messages().last().toMap().value("text").toString(), QStringLiteral("Привет. Готово.")); QVERIFY(client.error().isEmpty()); QCOMPARE(client.messages().size(),2); QCOMPARE(draft.count(),0); }
        else { QCOMPARE(draft.count(),1); QCOMPARE(draft.first().first().toString(),QString("Question")); QCOMPARE(sent.count(), 0); QCOMPARE(client.messages().size(), 0); QVERIFY(!client.error().isEmpty()); }
    }
    void lostReplyRecoveredWithoutAnotherPost() {
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        const QString chatId(32, '4'); QString requestId; int posts=0, statusReads=0;
        QJsonArray saved;
        auto chat = [&] { return QJsonObject{{"id",chatId},{"title","Recovery"},{"messages",saved}}; };
        connect(&server,&QTcpServer::newConnection,this,[&] {
            auto *socket=server.nextPendingConnection(); auto buffer=std::make_shared<QByteArray>();
            connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
            connect(socket,&QTcpSocket::readyRead,socket,[&,socket,buffer] {
                *buffer+=socket->readAll(); const auto split=buffer->indexOf("\r\n\r\n"); if(split<0)return;
                int length=0; for(const auto &line:buffer->left(split).split('\n')) if(line.toLower().startsWith("content-length:"))length=line.mid(15).trimmed().toInt();
                if(buffer->size()<split+4+length)return;
                const auto path=buffer->split(' ').value(1); QJsonObject data{{"success",true},{"chat",chat()}};
                if(path.endsWith("/messages")) {
                    ++posts;
                    const auto body=QString::fromUtf8(buffer->mid(split+4));
                    const auto match=QRegularExpression("name=\"request_id\"\\r\\n\\r\\n([a-f0-9]{32})").match(body);
                    QVERIFY(match.hasMatch()); requestId=match.captured(1);
                    saved=QJsonArray{QJsonObject{{"role","user"},{"text","Question"},{"attachments",QJsonArray{}}},
                                     QJsonObject{{"role","assistant"},{"text","Done once"},{"attachments",QJsonArray{}}}};
                    socket->disconnectFromHost(); buffer->clear(); return; // Commit happened, HTTP reply lost.
                }
                if(path=="/health")data={{"status","online"},{"features",QJsonObject{{"request_receipts",1}}}};
                if(path.contains("/requests/")) { ++statusReads; data["request"]=QJsonObject{{"id",requestId},{"state","completed"}}; }
                const auto bytes=QJsonDocument(data).toJson(QJsonDocument::Compact);
                socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "+QByteArray::number(bytes.size())+"\r\n\r\n"+bytes);
                socket->disconnectFromHost(); buffer->clear();
            });
        });
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(server.serverPort())));
        client.refresh(); QTRY_VERIFY(client.online()); client.openChat(chatId); QTRY_COMPARE(client.chatId(),chatId); QTRY_VERIFY(!client.chatsBusy());
        QSignalSpy sent(&client,&BackendClient::chatSent), recovered(&client,&BackendClient::chatRecovered);
        client.sendChatMessage("Question"); QTRY_COMPARE(posts,1); QTRY_VERIFY(!client.busy()); QVERIFY(!client.error().isEmpty());
        client.refresh(); QTRY_COMPARE(recovered.count(),1); QCOMPARE(recovered.first().first().toString(),"Question");
        QCOMPARE(client.messages().size(),2); QCOMPARE(posts,1); QCOMPARE(sent.count(),0); QVERIFY(client.error().isEmpty());
        client.refresh(); QTest::qWait(100); QCOMPARE(posts,1); QCOMPARE(statusReads,1);
    }
    void pendingRequestRestoresDraftAndKeepsSameId() {
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost,0));
        const QString id(32,'5'), receipt(32,'6'); int posts=0; QByteArray submitted;
        connect(&server,&QTcpServer::newConnection,this,[&] {
            auto *socket=server.nextPendingConnection(); auto buffer=std::make_shared<QByteArray>();
            connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
            connect(socket,&QTcpSocket::readyRead,socket,[&,socket,buffer] {
                *buffer+=socket->readAll(); const auto split=buffer->indexOf("\r\n\r\n"); if(split<0)return;
                int length=0; for(const auto &line:buffer->left(split).split('\n'))if(line.toLower().startsWith("content-length:"))length=line.mid(15).trimmed().toInt();
                if(buffer->size()<split+4+length)return;
                const auto path=buffer->split(' ').value(1); bool reject=false;
                QJsonObject chat{{"id",id},{"title","Pending"},{"messages",QJsonArray{}},
                    {"pending_request",QJsonObject{{"id",receipt},{"question","Original draft"},{"state","uncertain"}}}};
                QJsonObject data{{"success",true},{"chat",chat}};
                if(path=="/health")data={{"status","online"},{"features",QJsonObject{{"request_receipts",1}}}};
                if(path.endsWith("/messages")) { ++posts; submitted=*buffer; reject=true; data={{"success",false},{"message","Unconfirmed outcome; never repeated"}}; }
                const auto bytes=QJsonDocument(data).toJson(QJsonDocument::Compact);
                socket->write(QByteArray(reject?"HTTP/1.1 409 Conflict\r\n":"HTTP/1.1 200 OK\r\n")+"Content-Type: application/json\r\nConnection: close\r\nContent-Length: "+QByteArray::number(bytes.size())+"\r\n\r\n"+bytes);
                socket->disconnectFromHost(); buffer->clear();
            });
        });
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(server.serverPort())));
        QSignalSpy draft(&client,&BackendClient::restoreChatDraft);
        client.refresh(); QTRY_VERIFY(client.online()); client.openChat(id); QTRY_COMPARE(draft.count(),1); QTRY_VERIFY(!client.chatsBusy());
        QCOMPARE(draft.first().first().toString(),"Original draft"); QCOMPARE(posts,0);
        client.sendChatMessage("Original draft"); QTRY_COMPARE(posts,1); QTRY_VERIFY(!client.busy());
        QVERIFY(submitted.contains(receipt.toUtf8())); QVERIFY(!client.error().isEmpty());
    }
    void legacyBackendDoesNotReceiveAnUnconfirmedRetry() {
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        const QString id(32, 'a'); int posts=0, receipts=0;
        connect(&server,&QTcpServer::newConnection,this,[&] {
            auto *socket=server.nextPendingConnection(); auto buffer=std::make_shared<QByteArray>();
            connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
            connect(socket,&QTcpSocket::readyRead,this,[&,socket,buffer] {
                buffer->append(socket->readAll()); const auto split=buffer->indexOf("\r\n\r\n"); if(split<0)return;
                const auto length=QRegularExpression("Content-Length: ([0-9]+)",QRegularExpression::CaseInsensitiveOption).match(QString::fromLatin1(buffer->left(split))).captured(1).toInt();
                if(buffer->size()<split+4+length)return;
                const auto parts=buffer->left(buffer->indexOf("\r\n")).split(' '); const auto method=parts.value(0), path=parts.value(1);
                QJsonObject response{{"success",true}}; int code=200;
                if(path=="/health")response={{"status","online"}}; // No receipt support.
                else if(path=="/chats/"+id.toUtf8())response={{"success",true},{"chat",QJsonObject{{"id",id},{"title","Fixture"},{"messages",QJsonArray{}}}}};
                else if(method=="POST"){++posts;code=500;response={{"detail","Fixture lost result"}};}
                if(path.contains("/requests/"))++receipts;
                auto bytes=QJsonDocument(response).toJson(QJsonDocument::Compact);
                socket->write("HTTP/1.1 "+QByteArray::number(code)+" Result\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "+QByteArray::number(bytes.size())+"\r\n\r\n"+bytes);socket->disconnectFromHost();buffer->clear();
            });
        });
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(server.serverPort())));
        client.refresh();QTRY_VERIFY(client.online());client.openChat(id);QTRY_VERIFY(!client.chatsBusy());
        client.sendChatMessage("Original request");QTRY_COMPARE(posts,1);QTRY_VERIFY(!client.busy());
        client.refresh();QTest::qWait(150);QCOMPARE(posts,1);QCOMPARE(receipts,0);
        client.sendChatMessage("Original request");QTest::qWait(150);QCOMPARE(posts,1);
        QVERIFY(client.error().contains(QStringLiteral("обновите backend")));
        client.sendChatMessage("Explicit new request");QTRY_COMPARE(posts,2);QTRY_VERIFY(!client.busy());
    }
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
                if (path == "/health") response = {{"status", "online"}, {"features", QJsonObject{{"request_receipts", 1}}}};
                else if (path == "/chats/capabilities") response = {{"success", true}, {"provider", "OpenRouter"}, {"model", "demo"}, {"enabled", true}, {"capabilities", QJsonObject{{"known", true}, {"documents", documentsSupported}, {"images", false}, {"video", false}, {"image_generation", false}}}};
                else if (path == "/chats") response = {{"success", true}, {"chats", QJsonArray{QJsonObject{{"id", id}, {"title", title}, {"count", messages.size()}}}}};
                else if (path.endsWith("/messages") && method == "POST") {
                    ++uploads; uploadBody = buffer->mid(split + 4, length);
                    if (fail) { code = 400; response = {{"message", "Unsupported attachment"}, {"hint", "Choose a supported file"}, {"code", "SCOTT-API-400"}, {"request_id", "0123456789ab"}}; }
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
        QVERIFY(client.error().contains("Unsupported attachment"));QVERIFY(client.error().contains("Choose a supported file"));QVERIFY(client.error().contains("SCOTT-API-400 · 0123456789ab"));
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
