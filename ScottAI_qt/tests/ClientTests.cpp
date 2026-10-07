#include "BackendClient.h"
#include <QtTest>
#include <QTcpServer>
#include <QTcpSocket>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QSignalSpy>
#include <QUrlQuery>

class ClientTests : public QObject {
    Q_OBJECT
private slots:
    void settingsContractAndFailures() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        QJsonObject audio{{"volume", 75}, {"quiet", false}, {"input_device", ""}, {"output_device", ""}, {"character", "natural"}};
        QJsonObject engines{{"whisper", QJsonObject{{"choice", "auto"}, {"device", "cpu"}, {"locked_by_env", false}}},
                                  {"silero", QJsonObject{{"choice", "cpu"}, {"device", "cpu"}, {"locked_by_env", true}}}};
        bool amdAvailable = false;
        int posts = 0, voiceReads = 0;
        bool failWrite = false, failRead = false, scottAvailable = false, selectedStreaming = false, selectedAcceleration = false;
        QString selectedVoice = "demo", selectedProfile = "natural", selectedBuffer = "immediate";
        QJsonObject voiceJob{{"id", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}, {"state", "idle"}, {"installed", false}, {"supported", true}};
        QJsonObject voicePreparation{{"id", ""}, {"state", "idle"}, {"model_loaded", false}, {"message", ""}};
        QByteArray postedPath, previewBody, previewHeaders;
        QJsonObject posted;
        connect(&server, &QTcpServer::newConnection, this, [&] {
            auto *socket = server.nextPendingConnection();
            auto buffer = std::make_shared<QByteArray>();
            connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            connect(socket, &QTcpSocket::readyRead, socket, [&, socket, buffer] {
                *buffer += socket->readAll();
                const int split = buffer->indexOf("\r\n\r\n");
                if (split < 0) return;
                int length = 0;
                for (const auto &line : buffer->left(split).split('\n'))
                    if (line.toLower().startsWith("content-length:")) length = line.mid(15).trimmed().toInt();
                if (buffer->size() < split + 4 + length) return;
                const auto header = buffer->left(split);
                const auto path = header.split(' ').value(1);
                QJsonObject response;
                bool bad = false;
                if (header.startsWith("POST ")) {
                    ++posts; postedPath = path;
                    posted = QJsonDocument::fromJson(buffer->mid(split + 4, length)).object();
                    if (failWrite) { bad = true; response = {{"success", false}, {"message", "Save failed"}}; }
                    else {
                        if (path == "/audio/settings") for (auto it = posted.begin(); it != posted.end(); ++it) audio[it.key()] = it.value();
                        if (path == "/audio/quiet") audio["quiet"] = posted["quiet"];
                        if (path == "/voice/select") {
                            selectedVoice = posted.value("voice").toString();
                            if (posted.contains("profile")) selectedProfile = posted.value("profile").toString();
                            if (posted.contains("streaming")) selectedStreaming = posted.value("streaming").toBool();
                            if (posted.contains("acceleration")) selectedAcceleration = posted.value("acceleration").toBool();
                            if (posted.contains("buffer")) selectedBuffer = posted.value("buffer").toString();
                        }
                        if (path == "/speak") { previewBody = buffer->mid(split + 4, length); previewHeaders = header; }
                        response = {{"success", true}, {"message", "Saved"}};
                        if (path == "/voice/install") {
                            voiceJob["state"] = "running";
                            voiceJob["action"] = posted.value("action");
                            response = voiceJob;
                        }
                        if (path == "/voice/install/cancel") {
                            voiceJob["state"] = "cancelled";
                            response = voiceJob;
                        }
                        if (path == "/voice/prepare") {
                            voicePreparation["id"] = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
                            voicePreparation["state"] = "running";
                            response = voicePreparation;
                        }
                        if (path == "/voice/prepare/cancel") {
                            voicePreparation["state"] = "cancelled";
                            voicePreparation["model_loaded"] = false;
                            response = voicePreparation;
                        }
                    }
                } else if (path == "/health") response = {{"status", "online"}};
                else if (path == "/metrics") response = {{"metrics", QJsonObject{}}};
                else if (path == "/audio/settings") response = failRead ? QJsonObject{{"success", false}} : QJsonObject{
                    {"success", true}, {"available", true}, {"settings", audio},
                    {"devices", QJsonObject{{"input", QJsonArray{}}, {"output", QJsonArray{}}}}};
                else if (path == "/settings/device") response = {{"success", true}, {"cuda_available", false}, {"rocm_available", amdAvailable}, {"engines", engines}};
                else if (path == "/voice/install") response = voiceJob;
                else if (path == "/voice/prepare") response = voicePreparation;
                else if (path == "/voice/available") { ++voiceReads; response = {
                    {"voices", QJsonArray{QJsonObject{{"id", "demo"}, {"label", "Demo"}},
                        QJsonObject{{"id", "scott-voice"}, {"label", "Scott Voice"}, {"available", scottAvailable}, {"streaming_available", scottAvailable}, {"acceleration_available", scottAvailable}}}},
                    {"current", selectedVoice}, {"scott_profile", selectedProfile}, {"scott_streaming", selectedStreaming},
                    {"scott_acceleration", selectedAcceleration}, {"scott_buffer", selectedBuffer},
                    {"scott_buffers", QJsonArray{QJsonObject{{"id", "immediate"}, {"title", "Immediate"}},
                        QJsonObject{{"id", "2s"}, {"title", "Two seconds"}}, QJsonObject{{"id", "4s"}, {"title", "Four seconds"}},
                        QJsonObject{{"id", "complete"}, {"title", "Complete"}}}},
                    {"scott_profiles", QJsonArray{QJsonObject{{"id", "natural"}, {"title", "Original"}},
                        QJsonObject{{"id", "digital"}, {"title", "Digital"}}}}}; }
                else if (path == "/audio/characters") response = {{"success", true}, {"characters", QJsonArray{QJsonObject{{"id", "natural"}, {"title", "Natural"}}}}, {"current", "natural"}};
                else if (path == "/versions/items") response = {{"success", true}, {"data", QJsonArray{}}};
                else response = {{"success", false}, {"error", "Unexpected request"}};
                const auto body = QJsonDocument(response).toJson(QJsonDocument::Compact);
                socket->write(QByteArray(bad ? "HTTP/1.1 400 Bad Request\r\n" : "HTTP/1.1 200 OK\r\n") + "Content-Type: application/json\r\nConnection: close\r\nContent-Length: " + QByteArray::number(body.size()) + "\r\n\r\n" + body);
                socket->disconnectFromHost();
            });
        });
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(server.serverPort())));
        client.refresh(); QTRY_VERIFY(client.online());
        client.refreshSettings(); QTRY_VERIFY(!client.settingsBusy());
        QCOMPARE(client.settingsReady().size(), 5);
        QCOMPARE(posts, 0); QCOMPARE(voiceReads, 1); // Loading must never write preferences.
        client.applySetting("audio", {{"volume", 30}});
        client.applySetting("audio", {{"volume", 99}}); // Double click is blocked while saving.
        QTRY_VERIFY(!client.settingsBusy());
        QCOMPARE(posts, 1); QCOMPARE(postedPath, QByteArray("/audio/settings"));
        QCOMPARE(posted.value("volume").toInt(), 30);
        QCOMPARE(client.settings().value("audio").toMap().value("settings").toMap().value("volume").toInt(), 30);
        client.applySetting("device", {{"engine", "silero"}, {"choice", "auto"}});
        client.applySetting("device", {{"engine", "whisper"}, {"choice", "cuda"}});
        client.applySetting("audio", {{"volume", 101}});
        QCOMPARE(posts, 1); // Environment lock, unavailable GPU, invalid percentage.
        client.applySetting("device", {{"engine", "whisper"}, {"choice", "cpu"}});
        QTRY_VERIFY(!client.settingsBusy()); QCOMPARE(posts, 2);
        QCOMPARE(posted.value("engine").toString(), "whisper");
        client.applySetting("quiet", {{"quiet", true}});
        QTRY_VERIFY(!client.settingsBusy()); QCOMPARE(postedPath, QByteArray("/audio/quiet"));
        QVERIFY(client.settings().value("audio").toMap().value("settings").toMap().value("quiet").toBool());
        client.applySetting("voice", {{"voice", "demo"}});
        QTRY_VERIFY(!client.settingsBusy()); QCOMPARE(postedPath, QByteArray("/voice/select"));
        client.applySetting("audio", {{"character", "natural"}});
        QTRY_VERIFY(!client.settingsBusy()); QCOMPARE(posted.value("character").toString(), "natural");
        client.previewVoice(); QTRY_VERIFY(!client.settingsBusy());
        QVERIFY(previewHeaders.toLower().contains("content-type: application/x-www-form-urlencoded"));
        QVERIFY(previewBody.contains("force=true")); QVERIFY(previewBody.contains("text="));
        failWrite = true;
        client.applySetting("audio", {{"volume", 80}});
        QTRY_VERIFY(!client.settingsBusy()); QCOMPARE(client.settingsError(), "Save failed");
        QCOMPARE(client.settings().value("audio").toMap().value("settings").toMap().value("volume").toInt(), 30);
        failRead = true;
        client.refreshSettings(); QTRY_VERIFY(!client.settingsBusy());
        QVERIFY(!client.settingsReady().contains("audio"));
        QVERIFY(client.settingsReady().contains("voices"));
        QVERIFY(!client.settingsError().isEmpty());
        const int previousPosts = posts;
        client.applySetting("audio", {{"volume", 10}}); QCOMPARE(posts, previousPosts);
        failRead = false;
        client.refreshSettings(); QTRY_VERIFY(!client.settingsBusy());
        QVERIFY(client.settingsError().isEmpty()); QVERIFY(client.settingsReady().contains("audio"));
        // The server's engine options govern availability, even if a global
        // capability flag would otherwise permit that choice.
        auto whisper = engines.value("whisper").toObject();
        whisper["options"] = QJsonArray{QJsonObject{{"id", "auto"}, {"available", true}},
            QJsonObject{{"id", "rocm"}, {"available", true}},
            QJsonObject{{"id", "cuda"}, {"available", false}}};
        engines["whisper"] = whisper;
        amdAvailable = true;
        client.refreshSettings(); QTRY_VERIFY(!client.settingsBusy());
        client.applySetting("device", {{"engine", "whisper"}, {"choice", "rocm"}});
        QTRY_VERIFY(!client.settingsBusy());
        QCOMPARE(postedPath, QByteArray("/settings/device"));
        QCOMPARE(posted, (QJsonObject{{"engine", "whisper"}, {"choice", "rocm"}}));
        const int amdPosts = posts;
        whisper["options"] = QJsonArray{QJsonObject{{"id", "rocm"}, {"available", false}}};
        engines["whisper"] = whisper;
        client.refreshSettings(); QTRY_VERIFY(!client.settingsBusy());
        client.applySetting("device", {{"engine", "whisper"}, {"choice", "rocm"}});
        client.applySetting("device", {{"engine", "silero"}, {"choice", "rocm"}});
        QCOMPARE(posts, amdPosts); // Unavailable option and environment lock.
        client.applySetting("voice", {{"voice", "scott-voice"}});
        QCOMPARE(posts, amdPosts); // Missing optional runtime never changes preferences.
        failWrite = false;
        scottAvailable = true;
        client.refreshSettings(); QTRY_VERIFY(!client.settingsBusy());
        client.applySetting("voiceProfile", {{"voice", "scott-voice"}, {"profile", "digital"}});
        QCOMPARE(posts, amdPosts); // A profile is available only for the selected engine.
        client.applySetting("voice", {{"voice", "scott-voice"}});
        QTRY_VERIFY(!client.settingsBusy()); QCOMPARE(selectedVoice, "scott-voice");
        const int scottPosts = posts;
        client.applySetting("voiceProfile", {{"voice", "scott-voice"}, {"profile", "unknown"}});
        QCOMPARE(posts, scottPosts);
        client.applySetting("voiceProfile", {{"voice", "scott-voice"}, {"profile", "digital"}});
        QTRY_VERIFY(!client.settingsBusy());
        QCOMPARE(postedPath, QByteArray("/voice/select"));
        QCOMPARE(selectedProfile, "digital");
        const int beforeStream = posts;
        client.applySetting("voiceStreaming", {{"voice", "scott-voice"}, {"streaming", "true"}});
        QCOMPARE(posts, beforeStream);
        client.applySetting("voiceStreaming", {{"voice", "scott-voice"}, {"streaming", true}});
        QTRY_VERIFY(!client.settingsBusy());
        QVERIFY(selectedStreaming);
        QCOMPARE(posted, (QJsonObject{{"voice", "scott-voice"}, {"streaming", true}}));
        const int beforeAcceleration = posts;
        client.applySetting("voiceAcceleration", {{"voice", "scott-voice"}, {"acceleration", "true"}});
        QCOMPARE(posts, beforeAcceleration);
        client.applySetting("voiceAcceleration", {{"voice", "scott-voice"}, {"acceleration", true}});
        QTRY_VERIFY(!client.settingsBusy());
        QVERIFY(selectedAcceleration);
        QCOMPARE(posted, (QJsonObject{{"voice", "scott-voice"}, {"acceleration", true}}));
        client.applySetting("voiceAcceleration", {{"voice", "scott-voice"}, {"acceleration", false}});
        QTRY_VERIFY(!client.settingsBusy());
        QVERIFY(!selectedAcceleration);
        const int beforeBuffer = posts;
        client.applySetting("voiceBuffer", {{"voice", "scott-voice"}, {"buffer", "unknown"}});
        client.applySetting("voiceBuffer", {{"voice", "scott-voice"}, {"buffer", 4}});
        QCOMPARE(posts, beforeBuffer);
        client.applySetting("voiceBuffer", {{"voice", "scott-voice"}, {"buffer", "4s"}});
        QTRY_VERIFY(!client.settingsBusy());
        QCOMPARE(selectedBuffer, QString("4s"));
        QCOMPARE(posted, (QJsonObject{{"voice", "scott-voice"}, {"buffer", "4s"}}));
        client.previewVoice();
        QVERIFY(client.settingsNotice().contains(QStringLiteral("Готовим Scott Voice")));
        QTRY_VERIFY(!client.settingsBusy());
        QCOMPARE(QUrlQuery(QString::fromUtf8(previewBody)).queryItemValue("text", QUrl::FullyDecoded), QStringLiteral("Скотт на связи. Всё в порядке."));
        QTRY_VERIFY(client.voiceInstallReady());
        const int beforeInstall = posts;
        client.prepareScottVoice(); client.prepareScottVoice();
        QTRY_COMPARE(posts, beforeInstall + 1);
        QTRY_COMPARE(client.voiceInstall().value("action").toString(), QString("install"));
        QVERIFY(!client.settingsBusy());
        client.prepareScottVoice(true); QCOMPARE(posts, beforeInstall + 1);
        client.cancelScottVoice();
        QTRY_COMPARE(client.voiceInstall().value("state").toString(), QString("cancelled"));
        QCOMPARE(posted.value("id").toString(), QString("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"));
        client.prepareScottVoice(true);
        QTRY_COMPARE(client.voiceInstall().value("action").toString(), QString("check"));
        const int beforeComplete = voiceReads;
        voiceJob["state"] = "complete"; voiceJob["installed"] = true;
        client.refreshVoiceInstall();
        QTRY_COMPARE(client.voiceInstall().value("state").toString(), QString("complete"));
        QTRY_COMPARE(voiceReads, beforeComplete + 1);
        QCOMPARE(selectedVoice, QString("scott-voice"));
        client.refreshVoiceInstall(); QTest::qWait(100);
        QCOMPARE(voiceReads, beforeComplete + 1);
        QTRY_VERIFY(client.voicePreparationReady());
        const int beforePrepare = posts;
        client.warmScottVoice(); client.warmScottVoice();
        QTRY_COMPARE(posts, beforePrepare + 1);
        QTRY_COMPARE(client.voicePreparation().value("id").toString(), QString("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"));
        QCOMPARE(posted, QJsonObject{});
        client.releaseScottVoice();
        QTRY_COMPARE(client.voicePreparation().value("state").toString(), QString("cancelled"));
        QCOMPARE(posted.value("id").toString(), QString("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"));
        voicePreparation["state"] = "complete"; voicePreparation["model_loaded"] = true;
        client.refreshVoicePreparation();
        QTRY_VERIFY(client.voicePreparation().value("model_loaded").toBool());
        const int beforeLoaded = posts;
        client.warmScottVoice();
        QCOMPARE(posts, beforeLoaded);
        voicePreparation["state"] = "untrusted";
        client.refreshVoicePreparation();
        QTRY_VERIFY(!client.voicePreparationReady());
        client.warmScottVoice();
        QCOMPARE(posts, beforeLoaded);
    }
    void memoryContractAndFailures() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        QJsonArray records{QJsonObject{{"id", "seed1"}, {"text", "Example fact"}, {"kind", "fact"}, {"created", 1790000000}}};
        const QJsonArray kinds{QJsonObject{{"id", "fact"}, {"title", "Facts"}}, QJsonObject{{"id", "note"}, {"title", "Notes"}}};
        int posts = 0, deletes = 0;
        bool failWrite = false, failRead = false;
        QJsonObject posted;
        bool autoCapture = true;
        int archivedTurns = 8, policyWrites = 0, clears = 0;
        connect(&server, &QTcpServer::newConnection, this, [&] {
            auto *socket = server.nextPendingConnection();
            auto buffer = std::make_shared<QByteArray>();
            connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            connect(socket, &QTcpSocket::readyRead, socket, [&, socket, buffer] {
                *buffer += socket->readAll();
                const int split = buffer->indexOf("\r\n\r\n");
                if (split < 0) return;
                int length = 0;
                for (const auto &line : buffer->left(split).split('\n'))
                    if (line.toLower().startsWith("content-length:")) length = line.mid(15).trimmed().toInt();
                if (buffer->size() < split + 4 + length) return;
                QJsonObject response;
                if (buffer->startsWith("GET /health ")) response = {{"status", "online"}};
                else if (buffer->startsWith("GET /metrics ")) response = {{"metrics", QJsonObject{}}};
                else if (buffer->startsWith("GET /memories ")) {
                    response = failRead ? QJsonObject{{"success", false}} : QJsonObject{{"success", true}, {"memories", records}, {"kinds", kinds}, {"auto_capture", autoCapture}, {"archived_turns", archivedTurns}};
                } else if (buffer->startsWith("POST /memories/settings ")) {
                    ++policyWrites;
                    posted = QJsonDocument::fromJson(buffer->mid(split + 4, length)).object();
                    if (failWrite) response = {{"success", false}, {"error", "Policy failed"}};
                    else { autoCapture = posted.value("auto_capture").toBool(); response = {{"success", true}}; }
                } else if (buffer->startsWith("POST /ai/clear-memory ")) {
                    ++clears;
                    if (failWrite) response = {{"status", "error"}, {"error", "Clear failed"}};
                    else { archivedTurns = 0; response = {{"status", "success"}}; }
                } else if (buffer->startsWith("POST /memories ")) {
                    ++posts;
                    posted = QJsonDocument::fromJson(buffer->mid(split + 4, length)).object();
                    if (failWrite) response = {{"success", false}, {"error", "Write failed"}};
                    else {
                        const QJsonObject record{{"id", "new1"}, {"text", posted.value("text")}, {"kind", posted.value("kind")}};
                        if (records.size() == 1) { records.append(record); response = {{"success", true}, {"memory", record}}; }
                        else response = {{"success", true}, {"note", "Already remembered"}};
                    }
                } else if (buffer->startsWith("DELETE /memories/new1 ")) {
                    ++deletes;
                    if (failWrite) response = {{"success", false}, {"error", "Delete failed"}};
                    else { records.removeAt(1); response = {{"success", true}}; }
                } else response = {{"success", false}, {"error", "Unexpected endpoint"}};
                const auto body = QJsonDocument(response).toJson(QJsonDocument::Compact);
                socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: " + QByteArray::number(body.size()) + "\r\n\r\n" + body);
                socket->disconnectFromHost();
            });
        });
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(server.serverPort())));
        QSignalSpy added(&client, &BackendClient::memoryAdded);
        client.refresh(); QTRY_VERIFY(client.online());
        client.refreshMemories(); QTRY_VERIFY(!client.memoryBusy());
        QCOMPARE(client.memories().size(), 1);
        QCOMPARE(client.memoryKinds().size(), 2);
        client.addMemory(QString(201, 'x'), "fact");
        client.addMemory("Wrong kind", "unknown");
        QCOMPARE(posts, 0);
        client.addMemory("  New note  ", "note");
        QVERIFY(client.memoryBusy());
        client.addMemory("Duplicate click", "note");
        QTRY_VERIFY(!client.memoryBusy());
        QCOMPARE(posts, 1);
        QCOMPARE(posted.value("text").toString(), "New note");
        QCOMPARE(posted.value("kind").toString(), "note");
        QCOMPARE(client.memories().size(), 2);
        QCOMPARE(added.count(), 1);
        client.addMemory("New note", "note"); QTRY_VERIFY(!client.memoryBusy());
        QCOMPARE(client.memoryNotice(), "Already remembered");
        QCOMPARE(client.memories().size(), 2);
        failWrite = true;
        client.addMemory("Do not clear draft", "fact"); QTRY_VERIFY(!client.memoryBusy());
        QCOMPARE(client.memoryError(), "Write failed");
        QCOMPARE(added.count(), 2); // Failed writes must not clear the editor.
        client.forgetMemory("new1"); QTRY_VERIFY(!client.memoryBusy());
        QCOMPARE(client.memoryError(), "Delete failed");
        QCOMPARE(client.memories().size(), 2);
        client.forgetMemory("../clear"); client.forgetMemory("missing");
        QCOMPARE(deletes, 1);
        failWrite = false;
        client.forgetMemory("new1"); client.forgetMemory("new1");
        QTRY_VERIFY(!client.memoryBusy());
        QCOMPARE(deletes, 2); QCOMPARE(client.memories().size(), 1);
        failRead = true;
        client.refreshMemories(); QTRY_VERIFY(!client.memoryBusy());
        QVERIFY(!client.memoryError().isEmpty());
        QCOMPARE(client.memories().size(), 1); // Preserve cached records on a failed refresh.
        failRead = false;
        client.refreshMemories(); QTRY_VERIFY(!client.memoryBusy());
        QVERIFY(client.memoryError().isEmpty());
        QVERIFY(client.memorySettingsAvailable()); QVERIFY(client.autoMemoryEnabled());
        QCOMPARE(client.archivedTurns(), 8);
        client.setAutoMemoryEnabled(false); client.setAutoMemoryEnabled(true);
        QTRY_VERIFY(!client.memoryBusy());
        QCOMPARE(policyWrites, 1); QVERIFY(!client.autoMemoryEnabled());
        QCOMPARE(posted, (QJsonObject{{"auto_capture", false}}));
        failWrite = true;
        client.setAutoMemoryEnabled(true); QTRY_VERIFY(!client.memoryBusy());
        QVERIFY(!client.autoMemoryEnabled()); QCOMPARE(client.memoryError(), "Policy failed");
        client.clearConversationMemory(); QTRY_VERIFY(!client.memoryBusy());
        QCOMPARE(client.archivedTurns(), 8); QCOMPARE(client.memoryError(), "Clear failed");
        failWrite = false;
        client.clearConversationMemory(); QTRY_VERIFY(!client.memoryBusy());
        QCOMPARE(clears, 2); QCOMPARE(client.archivedTurns(), 0);
        QCOMPARE(client.memories().size(), 1); // History clearing keeps saved facts.
    }
    void chatContractAndRecovery() {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        int asks = 0;
        QJsonObject posted;
        bool malformed = false;
        connect(&server, &QTcpServer::newConnection, this, [&] {
            auto socket = server.nextPendingConnection();
            auto buffer = std::make_shared<QByteArray>();
            connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            connect(socket, &QTcpSocket::readyRead, socket, [&, socket, buffer] {
                *buffer += socket->readAll();
                const int split = buffer->indexOf("\r\n\r\n");
                if (split < 0) return;
                int length = 0;
                for (const auto &line : buffer->left(split).split('\n'))
                    if (line.toLower().startsWith("content-length:")) length = line.mid(15).trimmed().toInt();
                if (buffer->size() < split + 4 + length) return;
                QByteArray body;
                if (buffer->startsWith("GET /health ")) body = R"({"status":"online"})";
                else if (buffer->startsWith("GET /metrics ")) body = R"({"metrics":{"cpu":12,"ram":34}})";
                else if (buffer->startsWith("GET /listen/status ")) body = R"({"listening":false,"available":true})";
                else if (buffer->startsWith("POST /ask ")) {
                    ++asks;
                    posted = QJsonDocument::fromJson(buffer->mid(split + 4, length)).object();
                    body = malformed ? QByteArray("not json") : QByteArray(R"({"success":true,"data":{"answer":"Test answer"}})");
                } else body = R"({"success":false,"message":"Unexpected request"})";
                socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: " + QByteArray::number(body.size()) + "\r\n\r\n" + body);
                socket->disconnectFromHost();
            });
        });
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(server.serverPort())));
        client.refresh();
        QTRY_VERIFY(client.online());
        QTRY_COMPARE(client.metrics().value("cpu").toInt(), 12);
        QVERIFY(!client.ownsBackend());
        client.stopBackend(); // An externally hosted backend remains available.
        client.sendMessage("  Hello Scott  ");
        QVERIFY(client.busy());
        client.sendMessage("duplicate");
        QTRY_VERIFY(!client.busy());
        QCOMPARE(asks, 1);
        QCOMPARE(posted.value("question").toString(), "Hello Scott");
        QCOMPARE(posted.value("quiet_mode").toBool(), true);
        QCOMPARE(client.messages().last().toMap().value("text").toString(), "Test answer");
        malformed = true;
        client.sendMessage("Invalid response");
        QTRY_VERIFY(!client.busy());
        QVERIFY(!client.error().isEmpty());
        QCOMPARE(client.messages().last().toMap().value("role").toString(), "error");
        malformed = false;
        client.sendMessage("Retry");
        QTRY_VERIFY(!client.busy());
        QVERIFY(client.error().isEmpty());
        QCOMPARE(client.messages().last().toMap().value("role").toString(), "assistant");
        server.close();
        client.refresh();
        QTRY_VERIFY(!client.online());
        QVERIFY(client.metrics().isEmpty());
        const auto count = client.messages().size();
        client.sendMessage("offline");
        QCOMPARE(client.messages().size(), count);
        QVERIFY(!client.busy());
    }
};
QTEST_GUILESS_MAIN(ClientTests)
#include "ClientTests.moc"
