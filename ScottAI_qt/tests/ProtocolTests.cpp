#include "BackendClient.h"
#include "ProtocolFiles.h"
#include "ProtocolValidation.h"
#include <QtTest>
#include <QTcpServer>
#include <QTcpSocket>
#include <QJsonDocument>
#include <QTemporaryDir>
#include <QFile>
#include <memory>

class ProtocolTests : public QObject {
    Q_OBJECT
private:
    QJsonObject record() {
        return {{"id", "sample"}, {"name", "A / B? #"}, {"description", "Description"}, {"enabled", true}, {"repeat_count", 2}, {"stop_on_error", true},
                {"steps", QJsonArray{QJsonObject{{"text", "open app"}, {"pause", 2}, {"enabled", true}}}}, {"phrases", QJsonArray{"start work"}},
                {"schedule_text", ""}, {"schedule", QJsonValue::Null}, {"runs", 0}, {"last_run", QJsonValue::Null}, {"created", "2026-10-02T10:00:00"}};
    }
private slots:
    void backendContract() {
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        QJsonArray catalog{record()}; QJsonObject job, posted; QByteArray method;
        bool online = true, fail = false, malformed = false, lostStart = false; int saves = 0, starts = 0, cancels = 0, deletes = 0;
        connect(&server, &QTcpServer::newConnection, this, [&] {
            auto *socket = server.nextPendingConnection(); auto buffer = std::make_shared<QByteArray>();
            connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            connect(socket, &QTcpSocket::readyRead, socket, [&, socket, buffer] {
                *buffer += socket->readAll(); const auto split = buffer->indexOf("\r\n\r\n"); if (split < 0) return;
                int length = 0; for (const auto &line : buffer->left(split).split('\n')) if (line.toLower().startsWith("content-length:")) length = line.mid(15).trimmed().toInt();
                if (buffer->size() < split + 4 + length) return;
                const auto route = buffer->left(buffer->indexOf("\r\n"));
                QJsonObject data; bool bad = false;
                if (route.startsWith("GET /health ")) data = {{"status", online ? "online" : "offline"}};
                else if (route.startsWith("GET /metrics ")) data = {{"metrics", QJsonObject{}}};
                else if (route.startsWith("GET /listen/status ")) data = {{"listening", false}, {"available", false}};
                else if (route.startsWith("GET /protocols ")) data = fail ? QJsonObject{{"success", false}} : QJsonObject{{"success", true}, {"protocols", catalog}};
                else if (route.startsWith("POST /protocols ") || route.startsWith("PATCH /protocols/id/sample ")) {
                    ++saves; method = route; posted = QJsonDocument::fromJson(buffer->mid(split + 4, length)).object();
                    if (fail) { bad = true; data = {{"error", "Write failed"}}; }
                    else if (malformed) data = {{"success", true}};
                    else { auto saved = catalog[0].toObject(); for (auto it = posted.begin(); it != posted.end(); ++it) if (it.key() != "schedule") saved[it.key()] = it.value(); saved["name"] = saved["name"].toString().toUpper(); catalog[0] = saved; data = {{"success", true}, {"protocol", saved}}; }
                } else if (route.startsWith("POST /protocols/id/sample/start ")) {
                    ++starts;
                    job = {{"id", "job1"}, {"protocol_id", "sample"}, {"name", "Run"}, {"state", "running"}, {"current", 1}, {"total", 2}, {"message", "Running"}, {"error", ""}, {"steps", QJsonArray{QJsonObject{{"text", "first"}, {"ok", true}, {"response", "Done"}}}}};
                    if (lostStart) { bad = true; data = {{"error", "Lost reply"}}; } else data = {{"success", true}, {"job", job}};
                } else if (route.startsWith("GET /protocols/jobs/")) data = {{"success", true}, {"job", job}};
                else if (route.startsWith("POST /protocols/jobs/job1/cancel ")) { ++cancels; job["state"] = "cancelled"; job["message"] = "Stopped"; data = {{"success", true}, {"job", job}}; }
                else if (route.startsWith("DELETE /protocols/id/sample ")) { ++deletes; catalog = {}; data = {{"success", true}}; }
                else { bad = true; data = {{"error", "Unexpected endpoint"}}; }
                const auto bytes = QJsonDocument(data).toJson(QJsonDocument::Compact);
                socket->write(QByteArray(bad ? "HTTP/1.1 500 Error\r\n" : "HTTP/1.1 200 OK\r\n") + "Content-Type: application/json\r\nConnection: close\r\nContent-Length: " + QByteArray::number(bytes.size()) + "\r\n\r\n" + bytes);
                socket->disconnectFromHost(); buffer->clear();
            });
        });
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(server.serverPort())));
        QSignalSpy saved(&client, &BackendClient::protocolSaved);
        client.refresh(); QTRY_VERIFY(client.online()); client.refreshProtocols(); QTRY_VERIFY(client.protocolsReady()); QTRY_VERIFY(client.protocolJobReady());
        QCOMPARE(saves, 0); QCOMPARE(starts, 0);
        const auto initial = client.protocols(); auto draft = protocolDraft(record()); draft["name"] = "edited / name"; draft["repeat_count"] = 3;
        const auto json = QString::fromUtf8(QJsonDocument(draft).toJson(QJsonDocument::Compact));
        client.saveProtocol("sample", json); client.saveProtocol("sample", json); QTRY_VERIFY(!client.protocolsBusy());
        QCOMPARE(saves, 1); QVERIFY(method.startsWith("PATCH /protocols/id/sample ")); QCOMPARE(saved.count(), 1);
        QCOMPARE(posted["repeat_count"].toInt(), 3); QCOMPARE(client.protocols()[0].toMap()["name"].toString(), "EDITED / NAME");
        fail = true; client.saveProtocol("sample", json); QTRY_VERIFY(!client.protocolsBusy()); QCOMPARE(saved.count(), 1); QVERIFY(!client.protocolsError().isEmpty());
        fail = false; malformed = true; client.saveProtocol("sample", json); QTRY_VERIFY(!client.protocolsBusy()); QCOMPARE(saved.count(), 1);
        malformed = false; client.saveProtocol("sample", "{}"); QCOMPARE(saves, 3);
        client.runProtocol("sample"); client.runProtocol("sample"); QTRY_VERIFY(client.protocolRunning()); QCOMPARE(starts, 1);
        client.deleteProtocol("sample"); QCOMPARE(deletes, 0);
        client.cancelProtocol(); client.cancelProtocol(); QTRY_VERIFY(!client.protocolRunning()); QCOMPARE(cancels, 1);
        QTRY_VERIFY(!client.protocolsBusy()); QTRY_VERIFY(!client.protocolJobBusy());
        lostStart = true; client.runProtocol("sample"); QTRY_COMPARE(starts, 2); QTRY_VERIFY(client.protocolRunning());
        client.runProtocol("sample"); QCOMPARE(starts, 2); // A lost start reply cannot cause a duplicate run.
        online = false; client.refresh(); QTRY_VERIFY(!client.online()); QVERIFY(!client.protocolsReady());
        job = {}; online = true; client.refresh(); QTRY_VERIFY(client.online()); QTRY_VERIFY(!client.protocolRunning());
        client.refreshProtocols(); QTRY_VERIFY(client.protocolsReady()); QTRY_VERIFY(!client.protocolsBusy());
        const auto current = client.protocols(); fail = true; client.refreshProtocols(); QTRY_VERIFY(!client.protocolsBusy());
        QVERIFY(!client.protocolsReady()); QCOMPARE(client.protocols(), current);
        fail = false; client.refreshProtocols(); QTRY_VERIFY(client.protocolsReady());
        client.deleteProtocol("sample"); QTRY_VERIFY(!client.protocolsBusy()); QCOMPARE(deletes, 1); QVERIFY(client.protocols().isEmpty());
        QVERIFY(client.messages().isEmpty());
    }
    void filesRoundTripAndInvalidInput() {
        QTemporaryDir dir; QVERIFY(dir.isValid()); ProtocolFiles files;
        QSignalSpy imported(&files, &ProtocolFiles::imported);
        auto draft = protocolDraft(record()); draft["schedule"] = QStringLiteral("по будням в 09:00");
        const auto json = QString::fromUtf8(QJsonDocument(draft).toJson());
        const auto path = dir.filePath("protocol.json"); QVERIFY(files.exportFile(path, json)); QVERIFY(files.importFile(path));
        QCOMPARE(imported.count(), 1); const auto result = imported[0][0].toMap();
        QCOMPARE(result["repeat_count"].toInt(), 2); QVERIFY(!result["enabled"].toBool()); QCOMPARE(result["schedule"].toString(), "");
        QCOMPARE(result["steps"].toList().first().toMap()["pause"].toInt(), 2);
        QFile file(path); QVERIFY(file.open(QIODevice::WriteOnly)); file.write("{\"format\":\"scott-protocol\",\"version\":99}"); file.close();
        QVERIFY(!files.importFile(path)); QCOMPARE(imported.count(), 1);
        QVERIFY(!files.exportFile(dir.filePath("none/protocol.json"), json)); QVERIFY(!files.error().isEmpty());
    }
};
QTEST_GUILESS_MAIN(ProtocolTests)
#include "ProtocolTests.moc"
