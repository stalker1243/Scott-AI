#include "WindowMotion.h"
#include <QCoreApplication>
#include <QEvent>
#include <QPlatformSurfaceEvent>
#ifdef Q_OS_WIN
#include <qt_windows.h>
#endif

WindowMotion::WindowMotion(QObject *parent) : QObject(parent) {
    QCoreApplication::instance()->installNativeEventFilter(this);
}
WindowMotion::~WindowMotion() {
    QCoreApplication::instance()->removeNativeEventFilter(this);
}
void WindowMotion::attach(QQuickWindow *window) {
    m_window = window;
    window->installEventFilter(this);
    if (window->handle()) m_windowId = window->winId();
    connect(window, &QWindow::visibilityChanged, this, &WindowMotion::changed);
}
bool WindowMotion::eventFilter(QObject *, QEvent *event) {
    if (event->type() == QEvent::PlatformSurface) {
        if (static_cast<QPlatformSurfaceEvent *>(event)->surfaceEventType() == QPlatformSurfaceEvent::SurfaceAboutToBeDestroyed) m_windowId = 0;
        else if (m_window && m_window->handle()) m_windowId = m_window->winId();
    } else if (event->type() == QEvent::Show && m_window && m_window->handle()) m_windowId = m_window->winId();
    return false;
}
void WindowMotion::toggleMaximized() {
    if (!m_window) return;
    if (m_window->visibility() == QWindow::Maximized || m_window->visibility() == QWindow::FullScreen) restore();
    else maximize();
}
void WindowMotion::maximize() { if (m_window) m_window->showMaximized(); }
void WindowMotion::restore() { if (m_window) m_window->showNormal(); }
void WindowMotion::toggleFullScreen() {
    if (!m_window) return;
    if (m_window->visibility() == QWindow::FullScreen) { leaveFullScreen(); return; }
    m_fullScreenReturn = m_window->visibility() == QWindow::Maximized ? QWindow::Maximized : QWindow::Windowed;
    m_window->showFullScreen();
}
void WindowMotion::leaveFullScreen() {
    if (!m_window || m_window->visibility() != QWindow::FullScreen) return;
    if (m_fullScreenReturn == QWindow::Maximized) m_window->showMaximized();
    else m_window->showNormal();
}
bool WindowMotion::nativeEventFilter(const QByteArray &type, void *message, qintptr *result) {
#ifdef Q_OS_WIN
    // A frameless Qt window may ignore these system-menu commands. Forward
    // them to the same native Qt state methods as our caption buttons, without
    // interpolating geometry or opacity. Other HWNDs are never handled.
    if (type != "windows_generic_MSG" || !m_window || !m_windowId) return false;
    const auto *msg = static_cast<MSG *>(message);
    if (msg->hwnd != reinterpret_cast<HWND>(m_windowId) || msg->message != WM_SYSCOMMAND) return false;
    const auto command = msg->wParam & 0xFFF0;
    if (command == SC_RESTORE || command == SC_MAXIMIZE || command == SC_MINIMIZE) {
        QMetaObject::invokeMethod(this, [this, command] {
            if (!m_window) return;
            if (command == SC_MAXIMIZE) maximize();
            else if (command == SC_MINIMIZE) m_window->showMinimized();
            else if (m_window->visibility() == QWindow::Minimized && receivers(SIGNAL(minimizedRestoreRequested()))) emit minimizedRestoreRequested();
            else restore();
        }, Qt::QueuedConnection);
        if (result) *result = 0;
        return true;
    }
#else
    Q_UNUSED(type); Q_UNUSED(message); Q_UNUSED(result);
#endif
    return false;
}
