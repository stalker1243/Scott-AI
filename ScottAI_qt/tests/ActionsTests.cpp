#include "BackendClient.h"
#include <QtTest>
#include <QTcpServer>
#include <QTcpSocket>
#include <QJsonDocument>
#include <QJsonArray>
#include <memory>

class ActionsTests : public QObject {
    Q_OBJECT
private slots:
    void catalogFailuresAndRecovery() {
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        const QJsonObject available{{"id", "open"}, {"title", "Open app"}, {"detail", "By name"}, {"state", "ready"}, {"reason", ""}, {"examples", QJsonArray{"open notepad"}}};
        const QJsonObject unavailable{{"id", "voice"}, {"title", "Voice"}, {"detail", "By wake word"}, {"state", "off"}, {"reason", "No microphone"}, {"examples", QJsonArray{"Scott, time"}}};
        const QJsonObject catalog{{"success", true}, {"total", 2}, {"ready", 1}, {"groups", QJsonArray{QJsonObject{{"group", "Actions"}, {"items", QJsonArray{available, unavailable}}}}}};
        QJsonObject response = catalog;
        bool healthOnline = true, fail = false; int reads = 0, writes = 0;
        connect(&server, &QTcpServer::newConnection, this, [&] {
            auto *socket = server.nextPendingConnection(); auto buffer = std::make_shared<QByteArray>();
            connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            connect(socket, &QTcpSocket::readyRead, socket, [&, socket, buffer] {
                *buffer += socket->readAll(); if (!buffer->contains("\r\n\r\n")) return;
                QJsonObject body; bool error = false;
                if (buffer->startsWith("GET /health ")) body = {{"status", healthOnline ? "online" : "offline"}};
                else if (buffer->startsWith("GET /metrics ")) body = {{"metrics", QJsonObject{}}};
                else if (buffer->startsWith("GET /listen/status ")) body = {{"listening", false}, {"available", false}};
                else if (buffer->startsWith("GET /abilities ")) { ++reads; body = response; error = fail; }
                else { ++writes; error = true; }
                const auto bytes = QJsonDocument(body).toJson(QJsonDocument::Compact);
                socket->write(QByteArray(error ? "HTTP/1.1 503 Error\r\n" : "HTTP/1.1 200 OK\r\n") + "Content-Type: application/json\r\nConnection: close\r\nContent-Length: " + QByteArray::number(bytes.size()) + "\r\n\r\n" + bytes);
                socket->disconnectFromHost(); buffer->clear();
            });
        });
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(server.serverPort())));
        QSignalSpy metrics(&client, &BackendClient::metricsChanged);
        client.refreshAbilities(); QCOMPARE(reads, 0);
        client.refresh(); QTRY_VERIFY(client.online()); QTRY_COMPARE(metrics.count(), 1);
        client.refreshAbilities(); client.refreshAbilities(); QVERIFY(client.abilitiesBusy());
        QTRY_VERIFY(!client.abilitiesBusy()); QVERIFY(client.abilitiesReady()); QCOMPARE(reads, 1);
        QCOMPARE(client.abilitiesTotal(), 2); QCOMPARE(client.abilitiesReadyCount(), 1);
        const auto saved = client.abilities();
        QCOMPARE(saved.first().toMap().value("items").toList().last().toMap().value("reason").toString(), "No microphone");
        fail = true; client.refreshAbilities(); QTRY_VERIFY(!client.abilitiesBusy());
        QVERIFY(!client.abilitiesReady()); QVERIFY(!client.abilitiesError().isEmpty()); QCOMPARE(client.abilities(), saved);
        fail = false;
        QList<QJsonObject> invalid;
        auto bad = catalog; bad["ready"] = 2; invalid.append(bad);
        bad = catalog; bad["total"] = 2.5; invalid.append(bad);
        bad = catalog; bad["success"] = false; invalid.append(bad);
        bad = catalog; bad["groups"] = "wrong"; invalid.append(bad);
        for (const auto &state : {QString("unknown"), QString("ready")}) {
            auto item = unavailable; item["state"] = state;
            if (state == "ready") item["examples"] = QJsonArray{42};
            bad = catalog; bad["groups"] = QJsonArray{QJsonObject{{"group", "Actions"}, {"items", QJsonArray{available, item}}}}; invalid.append(bad);
        }
        bad = catalog; bad["groups"] = QJsonArray{QJsonObject{{"group", "Actions"}, {"items", QJsonArray{available, available}}}}; invalid.append(bad);
        for (const auto &invalidResponse : invalid) {
            response = invalidResponse; client.refreshAbilities(); QTRY_VERIFY(!client.abilitiesBusy());
            QVERIFY(!client.abilitiesReady()); QCOMPARE(client.abilities(), saved);
        }
        response = catalog; client.refreshAbilities(); QTRY_VERIFY(!client.abilitiesBusy());
        QVERIFY(client.abilitiesReady()); QVERIFY(client.abilitiesError().isEmpty());
        healthOnline = false; client.refresh(); QTRY_VERIFY(!client.online());
        QVERIFY(!client.abilitiesReady()); QCOMPARE(client.abilities(), saved);
        const int before = reads; client.refreshAbilities(); QCOMPARE(reads, before);
        healthOnline = true; client.refresh(); QTRY_VERIFY(client.online()); QTRY_COMPARE(metrics.count(), 3);
        response = {{"success", true}, {"total", 0}, {"ready", 0}, {"groups", QJsonArray{}}};
        client.refreshAbilities(); QTRY_VERIFY(!client.abilitiesBusy()); QVERIFY(client.abilitiesReady()); QVERIFY(client.abilities().isEmpty());
        QCOMPARE(client.abilitiesTotal(), 0); QCOMPARE(writes, 0); QVERIFY(client.messages().isEmpty());
    }
};
QTEST_GUILESS_MAIN(ActionsTests)
#include "ActionsTests.moc"
