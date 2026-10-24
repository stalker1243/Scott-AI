#include "SetupController.h"
#include <QtTest>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QScopeGuard>
#include <memory>
class SetupTests : public QObject {
    Q_OBJECT
private slots:
    void explicitProfilesReachFreshPython_data() {
        QTest::addColumn<QString>("mode");
        for (const auto &mode : {"auto", "cpu", "compact"}) QTest::newRow(mode) << QString(mode);
    }
    void explicitProfilesReachFreshPython() {
        QFETCH(QString, mode);
        QTemporaryDir directory; QVERIFY(directory.isValid()); SetupController setup;
        QSignalSpy ready(&setup,&SetupController::ready);
        auto probe=QCoreApplication::applicationDirPath()+"/setup_probe";
#ifdef Q_OS_WIN
        probe+=".exe";
#endif
        const auto parentProfile=qgetenv("SCOTT_RUNTIME_PROFILE");
        setup.check(probe,directory.path());QTRY_VERIFY(!setup.busy());
        setup.setRuntimeMode(mode);QCOMPARE(setup.runtimeMode(),mode);
        setup.setRuntimeMode("unknown");QCOMPARE(setup.runtimeMode(),mode);
        qputenv("SCOTT_SETUP_PROBE_EXPECT_MODE",mode.toUtf8());
        const auto cleanup=qScopeGuard([]{qunsetenv("SCOTT_SETUP_PROBE_EXPECT_MODE");});
        setup.prepare();
        setup.setRuntimeMode(mode=="auto" ? "compact" : "auto");
        QCOMPARE(setup.runtimeMode(),mode); // Locked during preparation.
        QTRY_COMPARE(ready.count(),1);
        QCOMPARE(qgetenv("SCOTT_RUNTIME_PROFILE"),parentProfile);
        setup.backendReady();QVERIFY(setup.error().isEmpty());
    }
    void savedModeIsDisplayedWithoutUserMigration() {
        QTemporaryDir directory;SetupController setup;
        auto probe=QCoreApplication::applicationDirPath()+"/setup_probe";
#ifdef Q_OS_WIN
        probe+=".exe";
#endif
        qputenv("SCOTT_SETUP_PROBE_MODE","compact");
        const auto cleanup=qScopeGuard([]{qunsetenv("SCOTT_SETUP_PROBE_MODE");});
        setup.check(probe,directory.path());QTRY_VERIFY(!setup.busy());
        QCOMPARE(setup.runtimeMode(),"compact");
        QCOMPARE(setup.sizeHint(),"Compact capacity estimate");
    }
    void destroyingActivePreparationDisconnectsCallbacks() {
        QTemporaryDir directory;QVERIFY(directory.isValid());
        auto setup=std::make_unique<SetupController>();
        auto probe=QCoreApplication::applicationDirPath()+"/setup_probe";
#ifdef Q_OS_WIN
        probe+=".exe";
#endif
        setup->check(probe,directory.path());QTRY_VERIFY(!setup->busy());
        qputenv("SCOTT_SETUP_PROBE_WAIT","1");
        const auto cleanup=qScopeGuard([]{qunsetenv("SCOTT_SETUP_PROBE_WAIT");});
        setup->prepare();QTRY_COMPARE(setup->progress(),0.5);
        QSignalSpy changed(setup.get(),&SetupController::changed);
        setup.reset();
        QCOMPARE(changed.count(),0);
    }
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
        QVERIFY(setup.visible()); QVERIFY(setup.launching()); QVERIFY(setup.busy());
        setup.backendReady(); QVERIFY(!setup.visible()); QVERIFY(!setup.checking()); QVERIFY(setup.error().isEmpty());
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
        qunsetenv("SCOTT_SETUP_PROBE_FAIL"); setup.prepare(); QTRY_COMPARE(ready.count(), 1);
        QVERIFY(setup.visible()); QVERIFY(setup.prepared());
        setup.backendFailed("Fixture startup failure"); QVERIFY(!setup.busy()); QCOMPARE(setup.error(), "Fixture startup failure");
        setup.prepare(); QCOMPARE(ready.count(), 2); QVERIFY(setup.launching());
        setup.backendReady(); QVERIFY(!setup.visible()); QCOMPARE(setup.progress(), 1.0);
        setup.check(probe, directory.path()); QTRY_VERIFY(!setup.busy());
        qputenv("SCOTT_SETUP_PROBE_WAIT", "1"); setup.prepare(); QTRY_COMPARE(setup.progress(), 0.5); QVERIFY(setup.busy());
        setup.cancel(); QTRY_VERIFY(!setup.busy()); QCOMPARE(ready.count(), 2); qunsetenv("SCOTT_SETUP_PROBE_WAIT");
        QVERIFY(setup.error().isEmpty()); QVERIFY(setup.visible());
        setup.setCompact(true); QVERIFY(setup.compact());
        QCOMPARE(setup.sizeHint(), "CPU capacity estimate");
        qputenv("SCOTT_SETUP_PROBE_EXPECT_CPU", "1"); setup.prepare(); QTRY_COMPARE(ready.count(), 3);
        setup.backendReady();
        qunsetenv("SCOTT_SETUP_PROBE_EXPECT_CPU");
    }
};
QTEST_GUILESS_MAIN(SetupTests)
#include "SetupTests.moc"
