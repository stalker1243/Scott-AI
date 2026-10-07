#include "WindowMotion.h"
#include <QCoreApplication>
#include <QEvent>
#include <QPlatformSurfaceEvent>
#include <QScreen>
#ifdef Q_OS_WIN
#include <qt_windows.h>
#endif

WindowMotion::WindowMotion(QObject *parent) : QObject(parent) {
    QCoreApplication::instance()->installNativeEventFilter(this);
    m_animation.setDuration(340);
    m_animation.setEasingCurve(QEasingCurve::InOutCubic);
    connect(&m_animation, &QVariantAnimation::valueChanged, this, [this](const QVariant &value) {
        if (m_window && m_running && m_animation.state() == QAbstractAnimation::Running)
            m_window->setGeometry(value.toRect());
    });
    connect(&m_animation, &QVariantAnimation::finished, this, &WindowMotion::commit);
}

WindowMotion::~WindowMotion() {
    QCoreApplication::instance()->removeNativeEventFilter(this);
}

void WindowMotion::attach(QQuickWindow *window) {
    m_window = window;
    window->installEventFilter(this);
    if (window->handle()) m_windowId = window->winId();
    connect(window, SIGNAL(animationsEnabledChanged()), this, SLOT(motionPreferenceChanged()));
    connect(window, &QWindow::visibilityChanged, this, [this](QWindow::Visibility visibility) {
        if (m_applying || !m_running || (visibility != QWindow::Hidden && visibility != QWindow::Minimized)) return;
        m_animation.stop(); m_running = false;
        // An external hide/minimize must not keep resizing an invisible window.
        if (m_normal.isValid()) m_window->setGeometry(m_normal);
        emit changed();
    });
    connect(window, &QWindow::screenChanged, this, [this] { finish(); });
}

bool WindowMotion::eventFilter(QObject *watched, QEvent *event) {
    if (watched != m_window) return false;
    if (event->type() == QEvent::PlatformSurface) {
        const auto surface = static_cast<QPlatformSurfaceEvent *>(event)->surfaceEventType();
        if (surface == QPlatformSurfaceEvent::SurfaceAboutToBeDestroyed) m_windowId = 0;
        else if (m_window->handle()) m_windowId = m_window->winId();
    } else if (event->type() == QEvent::Show && m_window->handle()) m_windowId = m_window->winId();
    return false;
}

bool WindowMotion::nativeEventFilter(const QByteArray &eventType, void *message, qintptr *result) {
#ifdef Q_OS_WIN
    if (eventType != "windows_generic_MSG" || !m_window || !m_windowId || m_applying) return false;
    const auto *msg = static_cast<MSG *>(message);
    if (msg->hwnd != reinterpret_cast<HWND>(m_windowId) || msg->message != WM_SYSCOMMAND || !m_window->isVisible()) return false;
    const auto command = msg->wParam & 0xFFF0;
    if (m_window->visibility() == QWindow::Minimized) {
        // SC_RESTORE alone can return a minimized Qt window to Windowed even
        // when it was maximized/full screen. Reuse the tray's remembered mode.
        if (command != SC_RESTORE || !receivers(SIGNAL(minimizedRestoreRequested()))) return false;
        QMetaObject::invokeMethod(this, [this] {
            if (m_window && m_window->visibility() == QWindow::Minimized) emit minimizedRestoreRequested();
        }, Qt::QueuedConnection);
        if (result) *result = 0;
        return true;
    }
    const char *method = nullptr;
    if (command == SC_MINIMIZE) method = "minimizeAnimated";
    else if (command == SC_MAXIMIZE) method = "maximizeAnimated";
    else if (command == SC_RESTORE &&
             (effectiveVisibility() == QWindow::Maximized || effectiveVisibility() == QWindow::FullScreen)) method = "restoreSizeAnimated";
    // Run after the native message returns, avoiding a nested Windows state
    // change. Internal commits use m_applying; other HWNDs are never handled.
    if (method && QMetaObject::invokeMethod(m_window, method, Qt::QueuedConnection)) {
        if (result) *result = 0;
        return true;
    }
#else
    Q_UNUSED(eventType); Q_UNUSED(message); Q_UNUSED(result);
#endif
    return false;
}

QWindow::Visibility WindowMotion::effectiveVisibility() const {
    return m_running ? m_target : m_window ? m_window->visibility() : QWindow::Hidden;
}

void WindowMotion::toggleMaximized() {
    const auto current = effectiveVisibility();
    transition(current == QWindow::Maximized || current == QWindow::FullScreen ? QWindow::Windowed : QWindow::Maximized);
}

void WindowMotion::maximize() { transition(QWindow::Maximized); }
void WindowMotion::restore() { transition(QWindow::Windowed); }

void WindowMotion::toggleFullScreen() {
    const auto current = effectiveVisibility();
    if (current == QWindow::FullScreen) transition(m_fullScreenReturn);
    else {
        m_fullScreenReturn = current == QWindow::Maximized ? QWindow::Maximized : QWindow::Windowed;
        transition(QWindow::FullScreen);
    }
}

void WindowMotion::leaveFullScreen() {
    if (effectiveVisibility() == QWindow::FullScreen) transition(m_fullScreenReturn);
}

void WindowMotion::transition(QWindow::Visibility target) {
    if (!m_window || !m_window->screen()) return;
    const bool interrupted = m_running;
    const auto current = m_window->visibility();
    const auto source = m_window->geometry();
    if ((interrupted && m_target == target) || (!interrupted && current == target)) return;
    if (!interrupted && current == QWindow::Windowed) m_normal = source;
    m_animation.stop();
    m_applying = true;
    // Animate native bounds while Windowed, then commit the requested Qt state.
    if (current != QWindow::Windowed) {
        m_window->showNormal();
        if (!m_normal.isValid()) m_normal = m_window->geometry();
        m_window->setGeometry(source);
    }
    m_applying = false;
    m_target = target;
    const auto *screen = m_window->screen();
    m_destination = target == QWindow::FullScreen ? screen->geometry()
                    : target == QWindow::Maximized ? screen->availableGeometry() : m_normal;
    if (!m_destination.isValid()) m_destination = source;
    m_running = true;
    emit changed();
    if (!m_window->property("animationsEnabled").toBool() || !m_window->isVisible() || current == QWindow::Minimized) {
        commit(); return;
    }
    m_animation.setStartValue(source);
    m_animation.setEndValue(m_destination);
    m_animation.start();
}

void WindowMotion::commit() {
    if (!m_window || !m_running) return;
    m_applying = true;
    if (m_target == QWindow::Windowed) {
        m_window->showNormal(); m_window->setGeometry(m_destination);
    } else {
        // Preserve Qt/Windows' normal placement when maximizing. Resetting
        // bounds before showFullScreen can queue a stale Windowed notification.
        if (m_target == QWindow::FullScreen) m_window->showFullScreen();
        else {
            if (m_normal.isValid()) m_window->setGeometry(m_normal);
            m_window->showMaximized();
        }
    }
    m_running = false; m_applying = false;
    emit changed();
}

void WindowMotion::finish() {
    if (!m_running) return;
    m_animation.stop(); commit();
}

void WindowMotion::motionPreferenceChanged() {
    if (m_window && !m_window->property("animationsEnabled").toBool()) finish();
}
