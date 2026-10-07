#include "SetupController.h"
#include <QtTest>
#include <QSignalSpy>
#include <QTemporaryDir>
class SetupTests : public QObject {
    Q_OBJECT
private slots:
    void preparationRetryAndCancellation() {
        QTemporaryDir directory; QVERIFY(directory.isValid()); SetupController setup;
        QSignalSpy ready(&setup, &SetupController::ready);
        const auto probe = QCoreApplication::applicationDirPath() + "/setup_probe.exe";
        setup.check(probe, directory.path()); QTRY_VERIFY(!setup.busy()); QVERIFY(setup.visible()); QCOMPARE(ready.count(), 0);
        qputenv("SCOTT_SETUP_PROBE_FAIL", "1"); setup.prepare(); QTRY_VERIFY(!setup.busy());
        QVERIFY(setup.visible()); QCOMPARE(setup.error(), "Network unavailable"); QCOMPARE(ready.count(), 0);
        qunsetenv("SCOTT_SETUP_PROBE_FAIL"); setup.prepare(); QTRY_COMPARE(ready.count(), 1); QVERIFY(!setup.visible()); QCOMPARE(setup.progress(), 1.0);
        qputenv("SCOTT_SETUP_PROBE_WAIT", "1"); setup.prepare(); QTRY_COMPARE(setup.progress(), 0.5); QVERIFY(setup.busy());
        setup.cancel(); QTRY_VERIFY(!setup.busy()); QCOMPARE(ready.count(), 1); qunsetenv("SCOTT_SETUP_PROBE_WAIT");
    }
};
QTEST_GUILESS_MAIN(SetupTests)
#include "SetupTests.moc"
