#include "WindowEffects.h"
#include <QCoreApplication>
#include <QEvent>
#include <QPlatformSurfaceEvent>
#include <QTimer>
#include <QOperatingSystemVersion>
#include <QScreen>

#ifdef Q_OS_WIN
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <dwmapi.h>

// The bundled MinGW headers predate these documented Windows 11 attributes.
static constexpr DWORD ImmersiveDarkMode = 20;
static constexpr DWORD SystemBackdropType = 38;
static constexpr int NoBackdrop = 1;
static constexpr int DesktopAcrylic = 3;

// Compatibility backdrop blur keeps the Qt alpha surface visible even when
// inactive. This optional accent policy is resolved dynamically, never linked.
struct AccentPolicy { int state; DWORD flags; DWORD color; DWORD animation; };
struct CompositionData { int attribute; void *data; SIZE_T size; };
using SetComposition = BOOL (WINAPI *)(HWND, const CompositionData *);
static const auto setComposition = reinterpret_cast<SetComposition>(
    GetProcAddress(GetModuleHandleW(L"user32.dll"), "SetWindowCompositionAttribute"));
#endif

WindowEffects::WindowEffects(QObject *parent) : QObject(parent) {
    QCoreApplication::instance()->installNativeEventFilter(this);
}

WindowEffects::~WindowEffects() {
    QCoreApplication::instance()->removeNativeEventFilter(this);
}

void WindowEffects::attach(QQuickWindow *window) {
    m_window = window;
    window->installEventFilter(this);
    connect(window, SIGNAL(glassActiveChanged()), this, SLOT(refresh()));
    connect(window, SIGNAL(glassFrostChanged()), this, SLOT(refresh()));
    connect(window, SIGNAL(darkModeChanged()), this, SLOT(refresh()));
    connect(window, &QWindow::screenChanged, this, &WindowEffects::workAreaChanged);
    for (auto *screen : QGuiApplication::screens())
        connect(screen, &QScreen::availableGeometryChanged, this, &WindowEffects::workAreaChanged);
    refresh();
}

QRect WindowEffects::workArea() const {
    return m_window && m_window->screen() ? m_window->screen()->availableGeometry() : QRect{};
}

void WindowEffects::refresh() {
    if (!m_window || !m_window->handle()) return;
    bool available = false;
    bool active = false;
#ifdef Q_OS_WIN
    m_windowId = m_window->winId();
    const auto hwnd = reinterpret_cast<HWND>(m_windowId);
    const BOOL dark = m_window->property("darkMode").toBool();
    const bool frosted = m_window->property("glassActive").toBool() &&
                         m_window->property("glassFrost").toInt() > 0;
    // Slider movement changes the QML veil. Reconfigure native blur only when
    // switching clear/frosted, changing theme or recreating/restoring a surface.
    if (m_appliedWindowId == m_windowId && m_lastFrosted == frosted && m_lastDark == bool(dark)) return;
    m_appliedWindowId = m_windowId;
    m_lastFrosted = frosted; m_lastDark = dark;
    DwmSetWindowAttribute(hwnd, ImmersiveDarkMode, &dark, sizeof(dark));
    const int backdrop = frosted ? DesktopAcrylic : NoBackdrop;
    bool accent = false;
    if (setComposition && QOperatingSystemVersion::current() >= QOperatingSystemVersion::Windows10) {
        const int disabled = NoBackdrop;
        DwmSetWindowAttribute(hwnd, SystemBackdropType, &disabled, sizeof(disabled));
        AccentPolicy policy{frosted ? 3 : 0, 0, 0, 0};
        CompositionData data{19, &policy, sizeof(policy)};
        accent = setComposition(hwnd, &data);
    }
    available = accent || SUCCEEDED(DwmSetWindowAttribute(hwnd, SystemBackdropType, &backdrop, sizeof(backdrop)));
    active = available && frosted;
    const MARGINS margins = active && !accent ? MARGINS{-1, -1, -1, -1} : MARGINS{0, 0, 0, 0};
    DwmExtendFrameIntoClientArea(hwnd, &margins);
#endif
    if (m_available != available || m_active != active) {
        m_available = available;
        m_active = active;
        emit changed();
    }
}

bool WindowEffects::eventFilter(QObject *, QEvent *event) {
    if (event->type() == QEvent::PlatformSurface &&
        static_cast<QPlatformSurfaceEvent *>(event)->surfaceEventType() == QPlatformSurfaceEvent::SurfaceAboutToBeDestroyed) {
        m_windowId = 0;
        m_appliedWindowId = 0;
        if (m_interacting) { m_interacting = false; emit interactingChanged(); }
        return false;
    }
    if (event->type() == QEvent::Show || event->type() == QEvent::WindowStateChange ||
        (event->type() == QEvent::PlatformSurface &&
         static_cast<QPlatformSurfaceEvent *>(event)->surfaceEventType() == QPlatformSurfaceEvent::SurfaceCreated)) {
        m_appliedWindowId = 0;
        QTimer::singleShot(0, this, &WindowEffects::refresh);
    }
    return false;
}

bool WindowEffects::nativeEventFilter(const QByteArray &, void *message, qintptr *) {
#ifdef Q_OS_WIN
    const auto *msg = static_cast<MSG *>(message);
    if (m_windowId && msg->hwnd == reinterpret_cast<HWND>(m_windowId)) {
        if (msg->message == WM_ENTERSIZEMOVE) {
            m_moveDetected = false; m_interacting = true; emit interactingChanged();
        } else if (msg->message == WM_MOVING) m_moveDetected = true;
        else if (msg->message == WM_EXITSIZEMOVE) {
            m_interacting = false; emit interactingChanged();
            if (m_moveDetected) QTimer::singleShot(0, this, &WindowEffects::moveFinished);
            m_moveDetected = false;
        }
    }
    // winId() can create a platform window. Never call it from a native event
    // filter while Windows/Qt is in the middle of destroying that same window.
    if (m_windowId && msg->hwnd == reinterpret_cast<HWND>(m_windowId) &&
        (msg->message == WM_DWMCOMPOSITIONCHANGED || msg->message == WM_THEMECHANGED || msg->message == WM_SETTINGCHANGE)) {
        m_appliedWindowId = 0;
        QTimer::singleShot(0, this, &WindowEffects::refresh);
    }
#else
    Q_UNUSED(message);
#endif
    return false;
}
