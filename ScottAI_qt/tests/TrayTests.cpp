#include "TrayController.h"
#include <QtTest>
#include <QTcpServer>
#include <QTcpSocket>
#include <QJsonDocument>
#include <QJsonArray>
#include <QAction>
#include <memory>

class TestWindow : public QQuickWindow {
    Q_OBJECT
public:
    int saves = 0;
    int quits = 0;
    Q_INVOKABLE void persistWorkspace() { ++saves; }
    Q_INVOKABLE void restoreFromTray() { show(); }
    Q_INVOKABLE void hideToBackground() { hide(); }
    Q_INVOKABLE void requestQuit() { ++quits; }
};

class TrayTests : public QObject {
    Q_OBJECT
    static QAction *item(TrayController &tray, const char *name) {
        return tray.menu()->findChild<QAction *>(name);
    }
private slots:
    void navigationAndLocalPreferences() {
        BackendClient client;
        QSystemTrayIcon icon;
        TestWindow window;
        window.setProperty("trayNotifications", true);
        window.setProperty("alwaysOnTop", false);
        TrayController tray(&icon, &client, &window, true);
        QVERIFY(!item(tray, "trayPauseVoice")->isEnabled());
        QVERIFY(!item(tray, "trayQuiet")->isEnabled());
        QVERIFY(!item(tray, "trayStop")->isEnabled());
        QVERIFY(item(tray, "trayStart")->isEnabled());
        item(tray, "trayChat")->trigger();
        QCOMPARE(window.property("selectedTab").toInt(), 1); QVERIFY(window.isVisible());
        item(tray, "trayToggle")->trigger(); QVERIFY(!window.isVisible());
        item(tray, "traySettings")->trigger();
        QCOMPARE(window.property("selectedTab").toInt(), 5); QVERIFY(window.isVisible());
        item(tray, "trayAlwaysOnTop")->trigger(); QVERIFY(window.property("alwaysOnTop").toBool());
        item(tray, "trayNotifications")->trigger(); QVERIFY(!window.property("trayNotifications").toBool());
        QCOMPARE(window.saves, 2);
        window.showMaximized(); QTRY_COMPARE(window.visibility(), QWindow::Maximized);
        window.showMinimized(); QTRY_COMPARE(window.visibility(), QWindow::Minimized);
        item(tray, "trayChat")->trigger(); QTRY_COMPARE(window.visibility(), QWindow::Maximized);
        item(tray, "trayToggle")->trigger(); QVERIFY(!window.isVisible());
        item(tray, "trayChat")->trigger(); QTRY_COMPARE(window.visibility(), QWindow::Maximized);
        item(tray, "trayQuit")->trigger(); QCOMPARE(window.quits, 1);
        window.showFullScreen(); QTRY_COMPARE(window.visibility(), QWindow::FullScreen);
        window.showMinimized(); QTRY_COMPARE(window.visibility(), QWindow::Minimized);
        item(tray, "trayChat")->trigger(); QTRY_COMPARE(window.visibility(), QWindow::FullScreen);
        item(tray, "trayToggle")->trigger(); QVERIFY(!window.isVisible());
        item(tray, "trayChat")->trigger(); QTRY_COMPARE(window.visibility(), QWindow::FullScreen);
    }
    void voicePauseQuietAndNotifications() {
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        bool listening = true, quiet = false, failWrite = false, available = true;
        int posts = 0; QByteArray lastPath;
        connect(&server, &QTcpServer::newConnection, this, [&] {
            auto *socket = server.nextPendingConnection();
            auto buffer = std::make_shared<QByteArray>();
            connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            connect(socket, &QTcpSocket::readyRead, socket, [&, socket, buffer] {
                *buffer += socket->readAll();
                const int split = buffer->indexOf("\r\n\r\n"); if (split < 0) return;
                int length = 0;
                for (const auto &line : buffer->left(split).split('\n'))
                    if (line.toLower().startsWith("content-length:")) length = line.mid(15).trimmed().toInt();
                if (buffer->size() < split + 4 + length) return;
                const auto path = buffer->left(split).split(' ').value(1);
                const bool post = buffer->startsWith("POST ");
                QJsonObject response; bool bad = false;
                if (post) {
                    ++posts; lastPath = path;
                    if (failWrite) { bad = true; response = {{"success", false}, {"message", "Write failed"}}; }
                    else if (path == "/listen/stop" || path == "/listen/start") {
                        listening = path == "/listen/start";
                        response = {{"success", true}, {"listening", listening}, {"available", available}};
                    } else if (path == "/audio/quiet") {
                        quiet = QJsonDocument::fromJson(buffer->mid(split + 4, length)).object().value("quiet").toBool();
                        response = {{"success", true}};
                    } else if (path == "/ask") response = {{"success", true}, {"data", QJsonObject{{"answer", "Private answer"}}}};
                } else if (path == "/health") response = {{"status", "online"}};
                else if (path == "/metrics") response = {{"metrics", QJsonObject{{"cpu", 12}, {"ram", 30}}}};
                else if (path == "/listen/status") response = {{"listening", listening}, {"available", available}};
                else if (path == "/audio/settings") response = {{"success", true}, {"available", true}, {"settings", QJsonObject{{"quiet", quiet}}}, {"devices", QJsonObject{}}};
                else if (path == "/settings/device") response = {{"engines", QJsonObject{}}};
                else if (path == "/voice/available?gender=male") response = {{"voices", QJsonArray{}}};
                else if (path == "/audio/characters") response = {{"characters", QJsonArray{}}};
                else if (path == "/versions/items") response = {{"data", QJsonArray{}}};
                const auto body = QJsonDocument(response).toJson(QJsonDocument::Compact);
                socket->write(QByteArray(bad ? "HTTP/1.1 400 Bad Request\r\n" : "HTTP/1.1 200 OK\r\n") + "Content-Type: application/json\r\nConnection: close\r\nContent-Length: " + QByteArray::number(body.size()) + "\r\n\r\n" + body);
                socket->disconnectFromHost();
            });
        });
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(server.serverPort())));
        QSystemTrayIcon icon; TestWindow window; window.setProperty("trayNotifications", true);
        TrayController tray(&icon, &client, &window, true);
        QSignalSpy notices(&tray, &TrayController::notificationRequested);
        client.refresh(); QTRY_VERIFY(client.listeningReady());
        client.refreshSettings(); QTRY_VERIFY(!client.settingsBusy());
        QCOMPARE(posts, 0); // Opening/refreshing never toggles the microphone.
        auto *pause = item(tray, "trayPauseVoice"); QVERIFY(pause->isEnabled()); QVERIFY(!pause->isChecked());
        pause->trigger(); QVERIFY(!pause->isEnabled());
        client.setListening(false); // A second click cannot write while the first is pending.
        QTRY_VERIFY(!client.listeningBusy()); QCOMPARE(posts, 1); QCOMPARE(lastPath, QByteArray("/listen/stop"));
        QVERIFY(pause->isChecked()); QVERIFY(!client.listening());
        pause->trigger(); QTRY_VERIFY(!client.listeningBusy()); QCOMPARE(lastPath, QByteArray("/listen/start")); QVERIFY(client.listening());
        failWrite = true;
        pause->trigger(); QTRY_VERIFY(!client.listeningBusy()); QVERIFY(client.listeningReady());
        QVERIFY(client.listening()); QVERIFY(!pause->isChecked()); QVERIFY(!client.listeningError().isEmpty());
        QCOMPARE(notices.count(), 1); notices.clear(); failWrite = false;
        item(tray, "trayQuiet")->trigger(); QTRY_VERIFY(!client.settingsBusy());
        QCOMPARE(lastPath, QByteArray("/audio/quiet")); QVERIFY(item(tray, "trayQuiet")->isChecked());
        window.hide(); client.sendMessage("Hidden question"); QTRY_VERIFY(!client.busy());
        QCOMPARE(notices.count(), 1); QVERIFY(!notices.first().at(1).toString().contains("Private answer"));
        client.clearChat(); window.show(); client.sendMessage("Visible question"); QTRY_VERIFY(!client.busy()); QCOMPARE(notices.count(), 1);
        window.hide(); window.setProperty("trayNotifications", false);
        client.sendMessage("Muted question"); QTRY_VERIFY(!client.busy()); QCOMPARE(notices.count(), 1);
        window.setProperty("trayNotifications", true); client.clearChat(); client.sendMessage("After clear"); QTRY_VERIFY(!client.busy()); QCOMPARE(notices.count(), 2);
        available = false; client.refreshListening(); QTRY_VERIFY(!client.listeningBusy());
        QVERIFY(!pause->isEnabled()); const int previousPosts = posts;
        client.setListening(false); QCOMPARE(posts, previousPosts);
    }
};
QTEST_MAIN(TrayTests)
#include "TrayTests.moc"
