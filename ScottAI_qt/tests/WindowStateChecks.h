#pragma once

#include "WindowMotion.h"
#include "WindowEffects.h"
#include "TrayController.h"
#include <QApplication>
#include <QAction>
#include <QDir>
#include <QElapsedTimer>
#include <QKeyEvent>
#include <QQuickItem>
#include <QScreen>
#include <QTimer>
#include <memory>
#ifdef Q_OS_WIN
#include <qt_windows.h>
#endif

inline QQuickItem *windowStateItem(QQuickItem *parent, const QString &name) {
    if (parent->objectName() == name) return parent;
    for (auto *child : parent->childItems())
        if (auto *found = windowStateItem(child, name)) return found;
    return nullptr;
}

inline void runWindowStateChecks(QApplication &app, QQuickWindow *window, WindowMotion &motion,
                                 WindowEffects &effects, TrayController &tray, bool &qmlErrors, bool &passed) {
    struct State {
        int phase = 0;
        QElapsedTimer elapsed;
        QRect normal;
        bool intermediate = false;
        int geometryFrames = 0;
        QRect lastGeometry;
        bool nativeRestoreAnimated = false;
        bool nativeMaximizeAnimated = false;
    };
    auto state = std::make_shared<State>(); state->elapsed.start();
    auto *timer = new QTimer(&app); timer->setInterval(20);
    const auto fail = [&app, timer](const char *message) {
        qWarning("Window states: %s", message); timer->stop(); app.exit(23);
    };
    const auto recordGeometry = [&motion, window, state, fail] {
        if ((state->phase != 1 && state->phase != 2) || !motion.running() || window->geometry() == state->lastGeometry) return;
#ifdef Q_OS_WIN
        RECT client{};
        if (!GetClientRect(reinterpret_cast<HWND>(window->winId()), &client) ||
            qAbs(qRound((client.right - client.left) / window->devicePixelRatio()) - window->width()) > 1 ||
            qAbs(qRound((client.bottom - client.top) / window->devicePixelRatio()) - window->height()) > 1) {
            fail("native client bounds did not match the animated geometry"); return;
        }
#endif
        state->lastGeometry = window->geometry(); ++state->geometryFrames;
        if (window->geometry() != state->normal && window->geometry() != window->screen()->availableGeometry())
            state->intermediate = true;
    };
    QObject::connect(window, &QWindow::widthChanged, timer, recordGeometry);
    QObject::connect(window, &QWindow::heightChanged, timer, recordGeometry);
    QObject::connect(&motion, &WindowMotion::changed, timer, [state, &motion] {
        if (!motion.running()) return;
        if (state->phase == 17 && motion.targetVisibility() == QWindow::Windowed) state->nativeRestoreAnimated = true;
        if (state->phase == 18 && motion.targetVisibility() == QWindow::Maximized) state->nativeMaximizeAnimated = true;
    });
    QObject::connect(timer, &QTimer::timeout, &app, [&, window, state, timer, fail] {
        const auto elapsed = state->elapsed.elapsed();
        const auto advance = [state] { ++state->phase; state->elapsed.restart(); state->intermediate = false; };
        const auto click = [window](const char *name) {
            auto *button = windowStateItem(window->contentItem(), name);
            return button && QMetaObject::invokeMethod(button, "clicked");
        };
        const auto key = [window](int code) {
            QKeyEvent press(QEvent::KeyPress, code, Qt::NoModifier), release(QEvent::KeyRelease, code, Qt::NoModifier);
            QCoreApplication::sendEvent(window, &press); QCoreApplication::sendEvent(window, &release);
        };
        const auto restore = [&tray] { tray.menu()->findChild<QAction *>("trayChat")->trigger(); };
        const auto systemCommand = [window](quintptr command) {
#ifdef Q_OS_WIN
            // Send only to this fixture's HWND; no desktop input or other app.
            PostMessageW(reinterpret_cast<HWND>(window->winId()), WM_SYSCOMMAND, command, 0);
#else
            Q_UNUSED(window); Q_UNUSED(command);
#endif
        };
        const auto screenshot = [window](const char *name) {
            QDir().mkpath("screenshots");
            return window->grabWindow().save(QString("screenshots/window-%1.png").arg(name));
        };
        if (qmlErrors) { fail("QML warning"); return; }
        if (elapsed > 2200) {
            qWarning("Window state timeout: phase=%d visibility=%d target=%d running=%d opacity=%.3f dismiss=%s",
                     state->phase, int(window->visibility()), motion.targetVisibility(), motion.running(), window->opacity(),
                     qPrintable(window->property("dismissAction").toString()));
            fail("transition timeout"); return;
        }
        if (state->phase == 0 && window->opacity() == 1 && elapsed >= 300) {
            window->setProperty("styleId", "glass");
            const auto area = effects.workArea(); state->normal = QRect(area.topLeft() + QPoint(80, 60), QSize(920, 660));
            window->setGeometry(state->normal);
            if (!click("windowMaximize") || !motion.running()) { fail("maximize button did not animate"); return; }
            advance();
        } else if (state->phase == 1) {
            if (motion.running() && window->geometry() != state->normal && window->geometry() != effects.workArea() && !state->intermediate) {
                state->intermediate = true;
            }
            if (!motion.running()) {
                if (!state->intermediate || state->geometryFrames < 3 || window->visibility() != QWindow::Maximized) { qInfo("Maximize observed: frames=%d intermediate=%d visibility=%d", state->geometryFrames, state->intermediate, int(window->visibility())); fail("maximize skipped intermediate geometry or final state"); return; }
                qInfo("Window maximize: %d distinct native bounds", state->geometryFrames);
                state->geometryFrames = 0;
                click("windowMaximize"); advance();
            }
        } else if (state->phase == 2) {
            if (motion.running() && window->geometry() != state->normal && !state->intermediate) {
                state->intermediate = true;
            }
            if (!motion.running()) {
                if (!state->intermediate || state->geometryFrames < 3 || window->visibility() != QWindow::Windowed || window->geometry() != state->normal) { fail("restore lost normal placement"); return; }
                qInfo("Window restore: %d distinct native bounds", state->geometryFrames);
                click("windowMaximize"); advance();
            }
        } else if (state->phase == 3 && elapsed >= 60) {
            const auto before = window->geometry(); click("windowMaximize");
            if (window->geometry() != before || motion.targetVisibility() != QWindow::Windowed) { fail("rapid toggle jumped instead of reversing"); return; }
            advance();
        } else if (state->phase == 4 && !motion.running()) {
            if (window->geometry() != state->normal) { fail("rapid toggle lost placement"); return; }
            key(Qt::Key_F11);
            if (!motion.running() || motion.targetVisibility() != QWindow::FullScreen) { fail("F11 did not start full screen"); return; }
            advance();
        } else if (state->phase == 5 && !motion.running()) {
            if (window->visibility() != QWindow::FullScreen || window->geometry() != window->screen()->geometry()) { fail("full screen did not fill the screen"); return; }
            screenshot("fullscreen"); key(Qt::Key_Escape); advance();
        } else if (state->phase == 6 && !motion.running()) {
            if (window->visibility() != QWindow::Windowed || window->geometry() != state->normal) { fail("Esc did not restore full screen placement"); return; }
            click("windowMaximize"); advance();
        } else if (state->phase == 7 && elapsed >= 60) {
            window->setProperty("animationsEnabled", false);
            if (motion.running() || window->visibility() != QWindow::Maximized) { fail("disabling motion did not finish maximize"); return; }
            click("windowMinimize");
            if (window->visibility() != QWindow::Minimized) { fail("disabled minimize was not immediate"); return; }
            restore();
            if (window->visibility() != QWindow::Maximized || window->opacity() != 1) { fail("disabled tray restore lost maximized state"); return; }
            window->setProperty("animationsEnabled", true); click("windowMinimize");
            if (!window->property("pendingMinimize").toBool() || window->visibility() != QWindow::Maximized) { fail("minimize skipped its fade"); return; }
            advance();
        } else if (state->phase == 8) {
            if (window->opacity() > 0 && window->opacity() < 1) state->intermediate = true;
            if (window->visibility() == QWindow::Minimized) {
                if (!state->intermediate || window->property("pendingMinimize").toBool()) { fail("minimize did not complete cleanly"); return; }
                // A native restore models the taskbar path without the tray's QML helper.
                window->showMaximized(); advance();
            }
        } else if (state->phase == 9) {
            if (window->opacity() > 0 && window->opacity() < 1) state->intermediate = true;
            if (window->opacity() == 1 && elapsed >= 300) {
                if (!state->intermediate || window->visibility() != QWindow::Maximized) { fail("tray restore did not fade back into maximized state"); return; }
                key(Qt::Key_F11); advance();
            }
        } else if (state->phase == 10 && !motion.running()) {
            if (window->visibility() != QWindow::FullScreen) { fail("maximized to full screen failed"); return; }
            click("windowMinimize"); advance();
        } else if (state->phase == 11 && window->visibility() == QWindow::Minimized) {
            restore(); advance();
        } else if (state->phase == 12 && window->opacity() == 1 && elapsed >= 300) {
            if (window->visibility() != QWindow::FullScreen) { fail("tray restore lost full screen"); return; }
            key(Qt::Key_Escape); advance();
        } else if (state->phase == 13 && !motion.running()) {
            if (window->visibility() != QWindow::Maximized) { fail("Esc did not return to previous maximized state"); return; }
            window->showNormal(); advance();
        } else if (state->phase == 14 && elapsed >= 100) {
            if (window->geometry() != state->normal) { fail("native restore remembered animated full size"); return; }
            click("windowMaximize"); QMetaObject::invokeMethod(window, "hideToBackground"); advance();
        } else if (state->phase == 15 && !window->isVisible()) {
            if (motion.running()) { fail("hidden window kept resizing"); return; }
            restore(); advance();
        } else if (state->phase == 16 && window->opacity() == 1 && elapsed >= 300) {
            if (window->visibility() != QWindow::Maximized || (effects.available() && !effects.active())) { fail("hide during resize lost state or Glass"); return; }
#ifdef Q_OS_WIN
            advance(); systemCommand(SC_RESTORE);
        } else if (state->phase == 17 && !motion.running() && window->visibility() == QWindow::Windowed) {
            if (!state->nativeRestoreAnimated || window->geometry() != state->normal) { fail("Windows restore bypassed animation or lost placement"); return; }
            advance(); systemCommand(SC_MAXIMIZE | 3); systemCommand(SC_MAXIMIZE);
        } else if (state->phase == 18 && !motion.running() && window->visibility() == QWindow::Maximized) {
            if (!state->nativeMaximizeAnimated) { fail("Windows maximize bypassed animation"); return; }
            advance(); systemCommand(SC_MINIMIZE);
        } else if (state->phase == 19) {
            if (window->opacity() > 0 && window->opacity() < 1) state->intermediate = true;
            if (window->visibility() == QWindow::Minimized) {
                if (!state->intermediate) { fail("Windows minimize bypassed animation"); return; }
                advance(); systemCommand(SC_RESTORE);
            }
        } else if (state->phase == 20) {
            if (window->opacity() > 0 && window->opacity() < 1) state->intermediate = true;
            if (window->visibility() == QWindow::Maximized && window->opacity() == 1 && elapsed >= 300) {
                if (!state->intermediate) { fail("Windows restore from minimize bypassed reveal"); return; }
                key(Qt::Key_F11); advance();
            }
        } else if (state->phase == 21 && !motion.running()) {
            if (window->visibility() != QWindow::FullScreen) { fail("full screen before Windows minimize failed"); return; }
            advance(); systemCommand(SC_MINIMIZE);
        } else if (state->phase == 22 && window->visibility() == QWindow::Minimized) {
            advance(); systemCommand(SC_RESTORE);
        } else if (state->phase == 23 && window->opacity() == 1 && elapsed >= 300) {
            if (window->visibility() != QWindow::FullScreen) { fail("Windows restore from minimize lost full screen"); return; }
            key(Qt::Key_Escape); advance();
        } else if (state->phase == 24 && !motion.running()) {
            if (window->visibility() != QWindow::Maximized) { fail("Windows minimize changed full screen return mode"); return; }
            window->setProperty("animationsEnabled", false); advance(); systemCommand(SC_RESTORE);
        } else if (state->phase == 25 && window->visibility() == QWindow::Windowed) {
            if (motion.running() || window->geometry() != state->normal || window->opacity() != 1) { fail("disabled Windows restore lost placement"); return; }
            advance(); systemCommand(SC_MAXIMIZE);
        } else if (state->phase == 26 && window->visibility() == QWindow::Maximized) {
            if (motion.running()) { fail("disabled Windows maximize still animated"); return; }
            advance(); systemCommand(SC_MINIMIZE);
        } else if (state->phase == 27 && window->visibility() == QWindow::Minimized) {
            advance(); systemCommand(SC_RESTORE);
        } else if (state->phase == 28 && window->visibility() == QWindow::Maximized && window->opacity() == 1) {
#endif
            passed = true; timer->stop();
            qInfo("Window states: geometry, reversal, F11/Esc, minimize, tray, Windows commands and disabled motion passed");
            app.exit(0);
        }
    });
    QTimer::singleShot(15000, &app, [fail] { fail("timeout"); });
    timer->start();
}
