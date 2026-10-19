#include "DiagnosticsController.h"
#include "AppLog.h"
#include <QtTest>
#include <QTemporaryDir>
class DiagnosticsTests : public QObject {
    Q_OBJECT
private slots:
    void offlineReadAndExport() {
        QTemporaryDir directory; QVERIFY(directory.isValid());
        AppLog::directory = directory.path() + "/logs";
        QFile module(directory.path() + "/diagnostics.py"); QVERIFY(module.open(QIODevice::WriteOnly)); module.close();
        auto probe = QCoreApplication::applicationDirPath() + "/diagnostics_probe";
#ifdef Q_OS_WIN
        probe += ".exe";
#endif
        DiagnosticsController diagnostics; diagnostics.configure(probe, directory.path());
        diagnostics.refresh("setup.log"); QTRY_VERIFY(!diagnostics.busy());
        QVERIFY2(diagnostics.error().isEmpty(), qPrintable(diagnostics.error()));
        QCOMPARE(diagnostics.logs().size(), 1); QVERIFY(diagnostics.text().contains("synthetic install failure"));
        diagnostics.exportTo(directory.path() + "/support.zip"); QTRY_VERIFY(!diagnostics.busy());
        QVERIFY2(diagnostics.error().isEmpty(), qPrintable(diagnostics.error()));
        QCOMPARE(diagnostics.archivePath(), directory.path() + "/support.zip");
        QVERIFY(QFileInfo::exists(diagnostics.archivePath())); QVERIFY(!diagnostics.notice().isEmpty());
    }
    void missingPythonIsExplained() {
        DiagnosticsController diagnostics; diagnostics.configure("/missing-python", "/missing-backend");
        diagnostics.refresh(); QVERIFY(!diagnostics.busy()); QVERIFY(!diagnostics.error().isEmpty());
    }
};
QTEST_GUILESS_MAIN(DiagnosticsTests)
#include "DiagnosticsTests.moc"
