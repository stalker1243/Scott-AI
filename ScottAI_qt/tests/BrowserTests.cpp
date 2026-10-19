#include "BackendClient.h"
#include <QtTest>
#include <QTcpServer>
#include <QTcpSocket>
#include <QJsonDocument>
#include <memory>

class BrowserTests : public QObject {
    Q_OBJECT
private slots:
    void jobsSelectionCancellationAndOffline() {
        QTcpServer server; QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        const QString id(32, 'a'), resultId(32, 'b');
        QJsonObject state{{"state", "idle"}, {"id", id}, {"enabled", true}, {"installed", true}};
        QJsonObject last; QString lastPath; int mutations = 0; bool available = true;
        QPointer<QTcpSocket> delayed;
        bool delayNext = false;
        const auto send = [](QTcpSocket *socket, const QJsonObject &body, int code = 200) {
            const auto bytes = QJsonDocument(body).toJson(QJsonDocument::Compact);
            socket->write("HTTP/1.1 " + QByteArray::number(code) + " Result\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: " + QByteArray::number(bytes.size()) + "\r\n\r\n" + bytes);
            socket->disconnectFromHost();
        };
        connect(&server, &QTcpServer::newConnection, this, [&] {
            auto *socket = server.nextPendingConnection(); auto buffer = std::make_shared<QByteArray>();
            connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            connect(socket, &QTcpSocket::readyRead, socket, [&, socket, buffer] {
                *buffer += socket->readAll(); const auto split = buffer->indexOf("\r\n\r\n"); if (split < 0) return;
                int length = 0;
                for (const auto &line : buffer->left(split).split('\n')) if (line.toLower().startsWith("content-length:")) length = line.mid(15).trimmed().toInt();
                if (buffer->size() < split + 4 + length) return;
                const auto path = buffer->split(' ').value(1); const auto method = buffer->split(' ').value(0);
                QJsonObject response;
                if (path == "/health") {
                    send(socket, {{"status", available ? "online" : "offline"}}); buffer->clear(); return;
                }
                if (path == "/browser" && method == "GET") {
                    if (delayNext) { delayNext = false; delayed = socket; buffer->clear(); return; }
                    response = state;
                } else if (path.startsWith("/browser") && method == "POST") {
                    ++mutations; lastPath = QString::fromUtf8(path);
                    last = QJsonDocument::fromJson(buffer->mid(split + 4, length)).object();
                    if (path.endsWith("settings")) state.insert("enabled", last.value("enabled"));
                    else state.insert("state", path.endsWith("cancel") ? "cancelled" : "running");
                    response = state;
                }
                send(socket, response); buffer->clear();
            });
        });
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(server.serverPort())));
        client.startBrowser("home"); QCOMPARE(mutations, 0);
        client.refresh(); QTRY_VERIFY(client.online()); QTRY_VERIFY(client.browserReady());
        client.startBrowser("search", QStringLiteral("уроки Qt")); client.startBrowser("search", "duplicate");
        QTRY_COMPARE(mutations, 1); QTRY_COMPARE(client.browserState().value("state").toString(), "running");
        QTRY_VERIFY(client.browserReady());
        QCOMPARE(last.value("query").toString(), QStringLiteral("уроки Qt"));
        client.cancelBrowser(); client.cancelBrowser(); QTRY_COMPARE(mutations, 2);
        QTRY_COMPARE(client.browserState().value("state").toString(), "cancelled");
        QCOMPARE(lastPath, "/browser/cancel"); QCOMPARE(last.value("id").toString(), id);
        state.insert("state", "complete"); state.insert("results_id", resultId);
        client.refreshBrowser(); QTRY_COMPARE(client.browserState().value("results_id").toString(), resultId);
        delayNext = true; client.refreshBrowser(); QTRY_VERIFY(delayed);
        client.startBrowser("select", "", 1); QTRY_COMPARE(mutations, 3);
        QCOMPARE(last.value("index").toInt(), 1); QCOMPARE(last.value("results_id").toString(), resultId);
        send(delayed, {{"state", "idle"}, {"id", "stale"}});
        QTest::qWait(150);
        QCOMPARE(client.browserState().value("state").toString(), "running");
        state.insert("state", "complete"); client.refreshBrowser();
        QTRY_COMPARE(client.browserState().value("state").toString(), "complete");
        client.setBrowserEnabled(false); QTRY_COMPARE(mutations, 4);
        QCOMPARE(lastPath, "/browser/settings"); QVERIFY(!last.value("enabled").toBool(true));
        available = false; client.refresh(); QTRY_VERIFY(!client.online()); QVERIFY(!client.browserReady());
        client.cancelBrowser(); client.startBrowser("home"); QTest::qWait(50); QCOMPARE(mutations, 4);
    }
};
QTEST_GUILESS_MAIN(BrowserTests)
#include "BrowserTests.moc"
