#include "DesktopSupport.h"
#include "WindowMotion.h"
#include <QtTest>
#include <QQuickWindow>

class MotionWindow : public QQuickWindow {
    Q_OBJECT
    Q_PROPERTY(bool animationsEnabled MEMBER animationsEnabled NOTIFY animationsEnabledChanged)
public:
    bool animationsEnabled = false;
signals:
    void animationsEnabledChanged();
};
class DesktopTests : public QObject {
    Q_OBJECT
private slots:
    void platformPolicy() {
        QVERIFY(!DesktopSupport::supportsWindowPositioning("wayland"));
        QVERIFY(!DesktopSupport::supportsWindowPositioning("wayland-egl"));
        QVERIFY(DesktopSupport::supportsWindowPositioning("xcb"));
        QVERIFY(DesktopSupport::supportsWindowPositioning("windows"));
    }
    void trayChangesAreObservedWithoutRepeatedSignals() {
        bool available = false;
        DesktopSupport desktop("wayland", [&] { return available; });
        QSignalSpy changes(&desktop, &DesktopSupport::trayAvailableChanged);
        QVERIFY(!desktop.trayAvailable()); QVERIFY(!desktop.windowPositioning());
        available = true; desktop.refresh(); QCOMPARE(changes.count(), 1); QVERIFY(desktop.trayAvailable());
        desktop.refresh(); QCOMPARE(changes.count(), 1);
        available = false; QTRY_COMPARE_WITH_TIMEOUT(changes.count(), 2, 2500); QVERIFY(!desktop.trayAvailable());
    }
    void nativeWindowStates() {
        MotionWindow window; window.resize(800, 560); window.show();
        WindowMotion motion; motion.attach(&window);
        const bool wayland = !DesktopSupport::supportsWindowPositioning(QGuiApplication::platformName());
        if (wayland) window.animationsEnabled = true;
        motion.maximize(); QVERIFY(!motion.running()); QTRY_COMPARE(window.visibility(), QWindow::Maximized);
        motion.toggleFullScreen(); QVERIFY(!motion.running()); QTRY_COMPARE(window.visibility(), QWindow::FullScreen);
        motion.leaveFullScreen(); QTRY_COMPARE(window.visibility(), QWindow::Maximized);
        motion.restore(); QTRY_COMPARE(window.visibility(), QWindow::Windowed);
        QVERIFY(!motion.running());
    }
};
QTEST_MAIN(DesktopTests)
#include "DesktopTests.moc"
