#include "SetupController.h"
#include <QtTest>
#include <QSignalSpy>
#include <QTemporaryDir>
class SetupTests : public QObject {
    Q_OBJECT
private slots:
    void readyStartupDoesNotRequestInstallation() {
        QTemporaryDir directory; SetupController setup;
        QSignalSpy ready(&setup, &SetupController::ready);
        auto probe = QCoreApplication::applicationDirPath() + "/setup_probe";
#ifdef Q_OS_WIN
        probe += ".exe";
#endif
        qputenv("SCOTT_SETUP_PROBE_READY", "1");
        setup.check(probe, directory.path()); QVERIFY(setup.checking());
        QTRY_COMPARE(ready.count(), 1); qunsetenv("SCOTT_SETUP_PROBE_READY");
        QVERIFY(!setup.visible()); QVERIFY(!setup.checking()); QVERIFY(setup.error().isEmpty());
    }
    void preparationRetryAndCancellation() {
        QTemporaryDir directory; QVERIFY(directory.isValid()); SetupController setup;
        QSignalSpy ready(&setup, &SetupController::ready);
        auto probe = QCoreApplication::applicationDirPath() + "/setup_probe";
#ifdef Q_OS_WIN
        probe += ".exe";
#endif
        QVERIFY2(QFileInfo::exists(probe), qPrintable(probe));
        setup.check(probe, directory.path()); QVERIFY(setup.checking()); QTRY_VERIFY(!setup.busy()); QVERIFY(!setup.checking()); QVERIFY(setup.visible()); QCOMPARE(ready.count(), 0);
        QCOMPARE(setup.sizeHint(), "GPU capacity estimate");
        qputenv("SCOTT_SETUP_PROBE_FAIL", "1"); setup.prepare(); QTRY_VERIFY(!setup.busy());
        QVERIFY(setup.visible()); QCOMPARE(setup.error(), "Network unavailable"); QCOMPARE(ready.count(), 0);
        qunsetenv("SCOTT_SETUP_PROBE_FAIL"); setup.prepare(); QTRY_COMPARE(ready.count(), 1); QVERIFY(!setup.visible()); QCOMPARE(setup.progress(), 1.0);
        qputenv("SCOTT_SETUP_PROBE_WAIT", "1"); setup.prepare(); QTRY_COMPARE(setup.progress(), 0.5); QVERIFY(setup.busy());
        setup.cancel(); QTRY_VERIFY(!setup.busy()); QCOMPARE(ready.count(), 1); qunsetenv("SCOTT_SETUP_PROBE_WAIT");
        QVERIFY(setup.error().isEmpty()); QVERIFY(setup.visible());
        setup.setCompact(true); QVERIFY(setup.compact());
        QCOMPARE(setup.sizeHint(), "CPU capacity estimate");
        qputenv("SCOTT_SETUP_PROBE_EXPECT_CPU", "1"); setup.prepare(); QTRY_COMPARE(ready.count(), 2);
        qunsetenv("SCOTT_SETUP_PROBE_EXPECT_CPU");
    }
};
QTEST_GUILESS_MAIN(SetupTests)
#include "SetupTests.moc"
