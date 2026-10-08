#include "BackendClient.h"
#include "ProfileAvatar.h"
#include <QtTest>
#include <QTcpServer>
#include <QTcpSocket>
#include <QJsonDocument>
#include <QJsonArray>
#include <QTemporaryDir>
#include <QPainter>
#include <QFile>
#include <memory>
#include <cmath>

class ProfileTests : public QObject {
    Q_OBJECT
private slots:
    void backendContract() {
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        QJsonObject state{{"success", true}, {"name", "Before"}, {"about", "Original"}, {"style", "friendly"}, {"interests", QJsonArray{"Music"}}};
        const QJsonArray styles{QJsonObject{{"id", "friendly"}, {"title", "Friendly"}}, QJsonObject{{"id", "brief"}, {"title", "Brief"}}};
        bool failWrite = false, malformed = false, failRead = false; int posts = 0;
        QJsonObject posted;
        connect(&server, &QTcpServer::newConnection, this, [&] {
            auto *socket = server.nextPendingConnection(); auto buffer = std::make_shared<QByteArray>();
            connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            connect(socket, &QTcpSocket::readyRead, socket, [&, socket, buffer] {
                *buffer += socket->readAll(); const int split = buffer->indexOf("\r\n\r\n"); if (split < 0) return;
                int length = 0;
                for (const auto &line : buffer->left(split).split('\n'))
                    if (line.toLower().startsWith("content-length:")) length = line.mid(15).trimmed().toInt();
                if (buffer->size() < split + 4 + length) return;
                QJsonObject response; bool bad = false;
                if (buffer->startsWith("GET /health ")) response = {{"status", "online"}};
                else if (buffer->startsWith("GET /metrics ")) response = {{"metrics", QJsonObject{}}};
                else if (buffer->startsWith("GET /listen/status ")) response = {{"listening", false}, {"available", false}};
                else if (buffer->startsWith("GET /personality ")) {
                    response = failRead ? QJsonObject{{"success", false}} : state;
                    if (!failRead) response["styles"] = styles;
                } else if (buffer->startsWith("POST /personality ")) {
                    ++posts; posted = QJsonDocument::fromJson(buffer->mid(split + 4, length)).object();
                    if (failWrite) { bad = true; response = {{"success", false}, {"message", "Save failed"}}; }
                    else if (malformed) response = {{"success", true}};
                    else { state = posted; state["success"] = true; state["name"] = posted["name"].toString().toUpper(); response = state; }
                }
                const auto body = QJsonDocument(response).toJson(QJsonDocument::Compact);
                socket->write(QByteArray(bad ? "HTTP/1.1 500 Error\r\n" : "HTTP/1.1 200 OK\r\n") + "Content-Type: application/json\r\nConnection: close\r\nContent-Length: " + QByteArray::number(body.size()) + "\r\n\r\n" + body);
                socket->disconnectFromHost();
            });
        });
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(server.serverPort())));
        QSignalSpy saved(&client, &BackendClient::profileSaved);
        client.saveProfile("No read", "", "friendly", {}); QCOMPARE(posts, 0);
        client.refresh(); QTRY_VERIFY(client.online()); client.refreshProfile(); QTRY_VERIFY(!client.profileBusy());
        QVERIFY(client.profileReady()); QCOMPARE(posts, 0);
        client.saveProfile("  alice  ", "  New bio  ", "brief", {" C++ "});
        client.saveProfile("Double", "", "brief", {});
        QTRY_VERIFY(!client.profileBusy()); QCOMPARE(posts, 1); QCOMPARE(saved.count(), 1);
        QCOMPARE(posted.value("name").toString(), "alice"); QCOMPARE(posted.value("about").toString(), "New bio");
        QCOMPARE(client.profile().value("name").toString(), "ALICE"); QVERIFY(!client.profile().value("styles").toList().isEmpty());
        client.saveProfile("", QString(301, 'x'), "brief", {});
        client.saveProfile("", "", "unknown", {});
        client.saveProfile("", "", "brief", {"Same", "Same"});
        QCOMPARE(posts, 1);
        failWrite = true; client.saveProfile("Unsaved", "", "brief", {}); QTRY_VERIFY(!client.profileBusy());
        QCOMPARE(client.profile().value("name").toString(), "ALICE"); QCOMPARE(saved.count(), 1); QVERIFY(!client.profileError().isEmpty());
        failWrite = false; malformed = true; client.saveProfile("Bad", "", "brief", {}); QTRY_VERIFY(!client.profileBusy());
        QCOMPARE(saved.count(), 1); QCOMPARE(client.profile().value("name").toString(), "ALICE");
        malformed = false; client.saveProfile("", "", "friendly", {}); QTRY_VERIFY(!client.profileBusy());
        QCOMPARE(client.profile().value("name").toString(), ""); QCOMPARE(saved.count(), 2); QVERIFY(client.profileError().isEmpty());
        failRead = true; client.refreshProfile(); QTRY_VERIFY(!client.profileBusy()); QVERIFY(!client.profileReady());
        const int previous = posts; client.saveProfile("Blocked", "", "friendly", {}); QCOMPARE(posts, previous);
        failRead = false; client.refreshProfile(); QTRY_VERIFY(!client.profileBusy()); QVERIFY(client.profileReady());
    }
    void photoCropPersistenceAndFailures() {
        QTemporaryDir directory; QVERIFY(directory.isValid());
        const auto picture = directory.path() + "/source.png";
        QImage seed(400, 200, QImage::Format_RGB32); seed.fill(Qt::red);
        { QPainter painter(&seed); painter.fillRect(200, 0, 200, 200, Qt::blue); }
        QVERIFY(seed.save(picture));
        const auto destination = directory.path() + "/profile";
        ProfileAvatar avatar(destination);
        QVERIFY(avatar.loadFile(picture)); QVERIFY(avatar.hasAvatar());
        auto preview = avatar.preview(); QCOMPARE(preview.pixelColor(0, 0).alpha(), 0); QCOMPARE(preview.pixelColor(50, 110), QColor(Qt::red));
        const auto source = avatar.source(); avatar.setCrop(2, 999, -999);
        QCOMPARE(avatar.source(), source); QCOMPARE(avatar.crop().value("x").toDouble(), 330.0); QCOMPARE(avatar.crop().value("y").toDouble(), -110.0);
        QVERIFY(avatar.save()); QVERIFY(!avatar.dirty());
        ProfileAvatar restored(destination); QCOMPARE(restored.crop(), avatar.crop()); QCOMPARE(restored.preview(), avatar.preview());
        restored.resetCrop(); QVERIFY(restored.dirty()); restored.revert(); QCOMPARE(restored.crop(), avatar.crop());
        QFile bad(directory.path() + "/bad.png"); QVERIFY(bad.open(QIODevice::WriteOnly)); bad.write("invalid image"); bad.close();
        QVERIFY(!restored.loadFile(bad.fileName())); QVERIFY(restored.hasAvatar()); QCOMPARE(restored.preview(), avatar.preview());
        restored.remove(); QVERIFY(restored.save()); ProfileAvatar cleared(destination); QVERIFY(!cleared.hasAvatar()); QVERIFY(cleared.error().isEmpty());
        ProfileAvatar unwritable(bad.fileName()); QVERIFY(unwritable.loadFile(picture)); QVERIFY(!unwritable.save()); QVERIFY(unwritable.dirty());
        ProfileAvatar temporary(directory.path() + "/no-write", true); QVERIFY(temporary.loadFile(picture)); QVERIFY(temporary.save()); QVERIFY(!QFile::exists(directory.path() + "/no-write/avatar.json"));
    }
    void rectangularCropAndDraftCancellation() {
        QTemporaryDir directory; QVERIFY(directory.isValid());
        const auto photo = directory.path() + "/wide.png";
        QImage wide(600, 200, QImage::Format_RGB32); wide.fill(Qt::red);
        { QPainter p(&wide); p.fillRect(400, 0, 200, 200, Qt::blue); }
        QVERIFY(wide.save(photo));
        ProfileAvatar avatar(directory.path() + "/profile");
        QVERIFY(avatar.loadFile(photo)); avatar.setCrop(1, -999, 999);
        QCOMPARE(avatar.crop().value("x").toDouble(), -220.0);
        QCOMPARE(avatar.crop().value("y").toDouble(), 0.0);
        QCOMPARE(avatar.preview().pixelColor(110, 110), QColor(Qt::blue));
        QVERIFY(avatar.save());
        avatar.setCrop(1, 80, 0); const auto draft = avatar.crop();
        avatar.beginCrop(); avatar.setCrop(3, 999, 999); avatar.finishCrop(false);
        QCOMPARE(avatar.crop(), draft); QVERIFY(avatar.dirty());
        avatar.beginCrop(); avatar.remove(); avatar.finishCrop(false);
        QVERIFY(avatar.hasAvatar()); QCOMPARE(avatar.crop(), draft);
        avatar.resetCrop(); avatar.zoomAt(2, 40, 0);
        QCOMPARE(avatar.crop().value("x").toDouble(), -40.0);
        avatar.beginCrop(); avatar.resetCrop(); avatar.finishCrop(true);
        QCOMPARE(avatar.crop().value("zoom").toDouble(), 1.0);
        QVERIFY(avatar.dirty());
        QImage tall(200, 600, QImage::Format_RGB32); tall.fill(Qt::green);
        QVERIFY(tall.save(photo)); QVERIFY(avatar.loadFile(photo)); avatar.setCrop(1, 999, -999);
        QCOMPARE(avatar.crop().value("x").toDouble(), 0.0);
        QCOMPARE(avatar.crop().value("y").toDouble(), -220.0);
        // Every interior pixel stays covered even at the extreme offset.
        const auto preview = avatar.preview();
        for (int y = 5; y < 215; ++y) for (int x = 5; x < 215; ++x)
            if (std::hypot(x - 110.0, y - 110.0) < 100) QCOMPARE(preview.pixelColor(x, y).alpha(), 255);
    }
};
QTEST_GUILESS_MAIN(ProfileTests)
#include "ProfileTests.moc"
