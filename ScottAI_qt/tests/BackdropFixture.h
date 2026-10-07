#pragma once
#include <QPainter>
#include <QWidget>
#include <QQuickWindow>
#ifdef Q_OS_WIN
#include <qt_windows.h>
#endif

// An owned window behind the launcher proves the desktop blur using real edges.
class BackdropFixture final : public QWidget {
public:
    BackdropFixture() : QWidget(nullptr, Qt::Window | Qt::FramelessWindowHint) {
        setAttribute(Qt::WA_ShowWithoutActivating);
    }
    void setColor(const QColor &color) { m_color = color; m_pattern = false; update(); }
    void setPattern() { m_pattern = true; update(); }
    void presentBehind(QQuickWindow *window) {
        // Leave enough owned pixels outside the probe for the blur kernel.
        setGeometry(window->geometry().adjusted(-96, -96, 96, 96));
        m_viewport = QRect(QPoint(96, 96), window->size());
        show(); window->show(); window->raise();
#ifdef Q_OS_WIN
        // Keep both owned test windows above unrelated apps for the duration
        // of compositor checks, without changing normal launcher window flags.
        const auto hwnd = reinterpret_cast<HWND>(window->winId());
        SetWindowPos(reinterpret_cast<HWND>(winId()), HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
        SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
#endif
    }
    bool ownsCaptureArea(QQuickWindow *window) const {
#ifdef Q_OS_WIN
        const auto hwnd = reinterpret_cast<HWND>(window->winId());
        if (GetWindow(hwnd, GW_HWNDNEXT) != reinterpret_cast<HWND>(winId()) || !IsWindowVisible(hwnd) ||
            !IsWindowVisible(reinterpret_cast<HWND>(winId()))) return false;
        RECT bounds{}; GetWindowRect(hwnd, &bounds);
        for (auto above = GetWindow(hwnd, GW_HWNDPREV); above; above = GetWindow(above, GW_HWNDPREV)) {
            RECT other{}, overlap{};
            if (IsWindowVisible(above) && !IsIconic(above) && GetWindowRect(above, &other) && IntersectRect(&overlap, &bounds, &other)) return false;
        }
        return true;
#else
        return window->isActive();
#endif
    }
protected:
    void paintEvent(QPaintEvent *) override {
        QPainter painter(this);
        painter.fillRect(rect(), m_color);
        if (m_pattern) {
            painter.fillRect(0, 0, width() / 2, height(), QColor("#b84c52"));
            painter.fillRect(width() / 2, 0, width() - width() / 2, height(), QColor("#365eaf"));
            for (int x = 0; x < width(); x += 12)
                painter.fillRect(x, m_viewport.bottom() - 24, 12, 121, (x / 12) % 2 ? QColor("#eeeeee") : QColor("#202020"));
        }
    }
private:
    QColor m_color{"#617f91"};
    bool m_pattern = false;
    QRect m_viewport;
};
