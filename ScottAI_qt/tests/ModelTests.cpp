#include "BackendClient.h"
#include <QtTest>
#include <QTcpServer>
#include <QTcpSocket>
#include <QJsonDocument>
#include <QJsonArray>
#include <memory>

class ModelTests : public QObject {
    Q_OBJECT
private slots:
    void configurationContract() {
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        QJsonObject catalog{{"active_provider", "Groq"}, {"active_model", "before"}, {"enabled", true},
            {"providers", QJsonArray{
                QJsonObject{{"id", "Groq"}, {"configured", true}, {"api_key", "server-secret"}, {"models", QJsonArray{QJsonObject{{"id", "before"}}}}},
                QJsonObject{{"id", "OpenAI"}, {"configured", false}, {"models", QJsonArray{QJsonObject{{"id", "demo"}}}}}}}};
        int posts = 0; QJsonObject posted; bool fail = false, malformed = false, invalidCatalog = false, connected = true;
        connect(&server, &QTcpServer::newConnection, this, [&] {
            auto *socket = server.nextPendingConnection(); auto buffer = std::make_shared<QByteArray>();
            connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            connect(socket, &QTcpSocket::readyRead, socket, [&, socket, buffer] {
                *buffer += socket->readAll(); const auto split = buffer->indexOf("\r\n\r\n"); if (split < 0) return;
                int length = 0;
                for (const auto &line : buffer->left(split).split('\n'))
                    if (line.toLower().startsWith("content-length:")) length = line.mid(15).trimmed().toInt();
                if (buffer->size() < split + 4 + length) return;
                QJsonObject response;
                if (buffer->startsWith("GET /health ")) response = {{"status", connected ? "online" : "offline"}};
                else if (buffer->startsWith("GET /metrics ")) response = {{"metrics", QJsonObject{}}};
                else if (buffer->startsWith("GET /listen/status ")) response = {{"listening", false}, {"available", false}};
                else if (buffer->startsWith("GET /ai/providers ")) response = invalidCatalog ? QJsonObject{{"providers", QJsonArray{}}} : catalog;
                else if (buffer->startsWith("POST /ai/configure ")) {
                    ++posts; posted = QJsonDocument::fromJson(buffer->mid(split + 4, length)).object();
                    if (fail) response = {{"success", false}, {"error", "Provider echoed " + posted.value("api_key").toString()}};
                    else if (malformed) response = {{"success", true}};
                    else response = {{"success", true}, {"provider", posted.value("provider")}, {"model", "actual-fallback"}, {"note", "Selected a supported fallback model"}};
                }
                const auto body = QJsonDocument(response).toJson(QJsonDocument::Compact);
                socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: " + QByteArray::number(body.size()) + "\r\n\r\n" + body);
                socket->disconnectFromHost();
            });
        });
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(server.serverPort())));
        QSignalSpy saved(&client, &BackendClient::modelConfigured);
        client.configureModel("OpenAI", "demo", "test-key"); QCOMPARE(posts, 0); QVERIFY(!client.modelsError().isEmpty());
        client.refresh(); QTRY_VERIFY(client.online()); client.refreshModels(); QTRY_VERIFY(!client.modelsBusy());
        QVERIFY(client.modelsReady()); QCOMPARE(client.aiState().value("model").toString(), "before");
        QVERIFY(!QJsonDocument::fromVariant(client.aiProviders()).toJson().contains("server-secret"));
        client.configureModel("OpenAI", "demo", ""); QCOMPARE(posts, 0); QVERIFY(!client.modelsError().isEmpty());
        client.configureModel("Unknown", "demo", "test-key");
        client.configureModel("OpenAI", "bad model", "test-key");
        client.configureModel("OpenAI", "demo", "key\nsecond"); QCOMPARE(posts, 0);
        client.configureModel("OpenAI", "  vendor/custom-next  ", "  test-key  ");
        client.configureModel("Groq", "before", "");
        QTRY_VERIFY(!client.modelsBusy()); QCOMPARE(posts, 1); QCOMPARE(saved.count(), 1);
        QCOMPARE(posted.value("provider").toString(), "OpenAI"); QCOMPARE(posted.value("model").toString(), "vendor/custom-next");
        QCOMPARE(posted.value("api_key").toString(), "test-key"); QCOMPARE(client.aiState().value("model").toString(), "actual-fallback");
        QVERIFY(client.aiProviders().at(1).toMap().value("configured").toBool()); QVERIFY(!client.modelsNotice().isEmpty());
        client.configureModel("OpenAI", "another-custom", ""); QTRY_VERIFY(!client.modelsBusy()); QCOMPARE(posts, 2);
        QVERIFY(!posted.contains("api_key"));
        const auto confirmed = client.aiState(); fail = true;
        client.configureModel("OpenAI", "demo", "test-secret"); QTRY_VERIFY(!client.modelsBusy());
        QCOMPARE(client.aiState(), confirmed); QCOMPARE(saved.count(), 2);
        QVERIFY(!client.modelsError().contains("test-secret")); QVERIFY(client.modelsError().contains("["));
        fail = false; malformed = true; client.configureModel("OpenAI", "demo", "test-secret"); QTRY_VERIFY(!client.modelsBusy());
        QCOMPARE(client.aiState(), confirmed); QCOMPARE(saved.count(), 2); QVERIFY(!client.modelsError().isEmpty());
        invalidCatalog = true; client.refreshModels(); QTRY_VERIFY(!client.modelsBusy()); QVERIFY(!client.modelsReady());
        const auto count = posts; client.configureModel("OpenAI", "demo", "test-key"); QCOMPARE(posts, count);
        invalidCatalog = false; client.refreshModels(); QTRY_VERIFY(!client.modelsBusy()); QVERIFY(client.modelsReady());
        connected = false; client.refresh(); QTRY_VERIFY(!client.online()); QVERIFY(!client.modelsReady());
        client.configureModel("OpenAI", "demo", "test-key"); QCOMPARE(posts, count);
        connected = true; client.refresh(); QTRY_VERIFY(client.online()); client.refreshModels(); QTRY_VERIFY(!client.modelsBusy()); QVERIFY(client.modelsReady());
    }
};
QTEST_GUILESS_MAIN(ModelTests)
#include "ModelTests.moc"
