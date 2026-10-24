#include "BackendClient.h"
#include <QtTest>
#include <QTcpServer>
#include <QNetworkReply>
#include <QFile>
#include <QTemporaryDir>

class RecoveryTests : public QObject {
    Q_OBJECT
    QString probe() const {
        auto path = QCoreApplication::applicationDirPath() + "/recovery_probe";
#ifdef Q_OS_WIN
        path += ".exe";
#endif
        return path;
    }
    int count(const QString &path) const { QFile file(path); if (!file.open(QIODevice::ReadOnly)) return 0; return file.readAll().toInt(); }
    quint16 configure(const QString &path) {
        QTcpServer reserve; if (!reserve.listen(QHostAddress::LocalHost, 0)) return 0;
        const auto port = reserve.serverPort(); reserve.close();
        qputenv("SCOTT_RECOVERY_PORT", QByteArray::number(port));
        qputenv("SCOTT_RECOVERY_COUNT", QFile::encodeName(path + "/starts"));
        QFile main(path + "/main.py"); if (!main.open(QIODevice::WriteOnly)) return 0; main.write("fixture");
        return port;
    }
private slots:
    void cleanup() { qunsetenv("SCOTT_RECOVERY_PORT"); qunsetenv("SCOTT_RECOVERY_COUNT"); qunsetenv("SCOTT_RECOVERY_CRASH_LOOP"); }
    void ownedCrashRecoversAndManualStopStaysStopped() {
        QTemporaryDir dir; const auto port = configure(dir.path()); QVERIFY(port);
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(port)));
        client.configureProcess(dir.path(), probe()); client.beginPolling(); client.startBackend();
        QTRY_VERIFY_WITH_TIMEOUT(client.online(), 15000); QVERIFY(client.ownsBackend());
        QNetworkAccessManager network;
        auto *crash = network.get(QNetworkRequest(QUrl(QString("http://127.0.0.1:%1/fixture/crash").arg(port))));
        QTRY_VERIFY_WITH_TIMEOUT(crash->isFinished(), 5000); crash->deleteLater();
        QTRY_COMPARE_WITH_TIMEOUT(count(dir.path()+"/starts"), 2, 15000);
        QTRY_VERIFY_WITH_TIMEOUT(client.online(), 15000); QVERIFY(client.ownsBackend()); QVERIFY(client.error().isEmpty());
        client.stopBackend(); QVERIFY(!client.ownsBackend()); QVERIFY(!client.starting());
        QTest::qWait(1500); QCOMPARE(count(dir.path()+"/starts"), 2);
    }
    void crashLoopHasBoundedRetriesAndStopCancelsPendingRecovery() {
        QTemporaryDir dir; const auto port = configure(dir.path()); QVERIFY(port);
        qputenv("SCOTT_RECOVERY_CRASH_LOOP", "1");
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(port)));
        client.configureProcess(dir.path(), probe()); client.beginPolling(); client.startBackend();
        QTRY_COMPARE_WITH_TIMEOUT(count(dir.path()+"/starts"), 4, 25000);
        QTRY_VERIFY_WITH_TIMEOUT(!client.starting(), 5000); QVERIFY(!client.error().isEmpty());
        QTest::qWait(1500); QCOMPARE(count(dir.path()+"/starts"), 4);
        client.startBackend(); QTRY_COMPARE_WITH_TIMEOUT(count(dir.path()+"/starts"), 5, 5000);
        QTRY_VERIFY_WITH_TIMEOUT(client.status().contains(QStringLiteral("Восстанавливаю")), 5000);
        client.stopBackend(); QTest::qWait(1500); QCOMPARE(count(dir.path()+"/starts"), 5);
    }
    void externalBackendIsNeverStoppedOrSupervised() {
        QTemporaryDir dir; const auto port = configure(dir.path()); QVERIFY(port);
        QProcess external; external.start(probe(), {}); QVERIFY(external.waitForStarted());
        QVERIFY(external.waitForReadyRead(5000)); QVERIFY(external.readAllStandardOutput().contains("READY"));
        QTRY_COMPARE_WITH_TIMEOUT(count(dir.path()+"/starts"), 1, 5000);
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(port)));
        client.configureProcess(dir.path(), probe()); client.startBackend();
        QTRY_VERIFY_WITH_TIMEOUT(client.online(), 5000); QVERIFY(!client.ownsBackend());
        client.stopBackend(); QCOMPARE(external.state(), QProcess::Running);
        // This fixture was created above; no user process is selected by PID/name.
        external.kill(); QVERIFY(external.waitForFinished(3000));
        QTest::qWait(1500); QCOMPARE(count(dir.path()+"/starts"), 1);
    }
    void stopDuringHealthProbeCancelsLaunch() {
        QTemporaryDir dir; const auto port = configure(dir.path()); QVERIFY(port);
        QTcpServer silent; QVERIFY(silent.listen(QHostAddress::LocalHost, port));
        BackendClient client(QUrl(QString("http://127.0.0.1:%1").arg(port)));
        client.configureProcess(dir.path(), probe()); client.startBackend();
        QTRY_VERIFY_WITH_TIMEOUT(silent.hasPendingConnections(), 3000);
        auto *socket = silent.nextPendingConnection();
        client.stopBackend(); QTest::qWait(3000);
        QVERIFY(!client.starting()); QVERIFY(!client.ownsBackend()); QCOMPARE(count(dir.path()+"/starts"), 0);
        delete socket;
    }
};
QTEST_GUILESS_MAIN(RecoveryTests)
#include "RecoveryTests.moc"
