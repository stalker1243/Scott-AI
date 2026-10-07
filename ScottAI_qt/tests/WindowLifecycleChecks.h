#pragma once

#include "TrayController.h"
#include "WindowEffects.h"
#include "BackdropFixture.h"
#include <QAction>
#include <QApplication>
#include <QElapsedTimer>
#include <QQuickWindow>
#include <QTimer>
#include <QScreen>
#include <memory>

// Exercise the actual QML window with synthetic data. Never target another
// desktop window, create a backend process, or write the user's preferences.
inline void runWindowLifecycleChecks(QApplication &app, QQuickWindow *window,
                                     TrayController &tray, WindowEffects &effects,
                                     bool &qmlErrors, bool &passed) {
    app.setQuitOnLastWindowClosed(false); // Reopen after testing the real close event.
    struct State {
        int phase = 0;
        QElapsedTimer elapsed;
        bool intermediate = false;
        int style = 0;
        QImage composite;
        QVector<QPoint> foreground;
    };
    auto state = std::make_shared<State>();
    auto underlay = std::make_shared<BackdropFixture>();
    const QColor behind("#617f91");
    state->elapsed.start();
    auto *timer = new QTimer(&app);
    timer->setInterval(20);
    const auto fail = [&app, timer](const char *message) {
        qWarning("Window lifecycle: %s", message); timer->stop(); app.exit(22);
    };
    const auto invoke = [window](const char *method) { QMetaObject::invokeMethod(window, method); };
    if (!window->isVisible() || window->opacity() != 0) {
        fail("startup was not prepared at zero opacity");
        QTimer::singleShot(0, &app, [&app] { app.exit(22); });
        return;
    }
    QObject::connect(&app, &QCoreApplication::aboutToQuit, &app, [&passed, &qmlErrors, state, underlay, timer, window] {
        timer->stop();
        underlay->hide();
        passed = state->phase == 13 && state->intermediate && !window->isVisible() &&
                 !window->property("pendingQuit").toBool() && window->opacity() == 1 && !qmlErrors;
        if (passed) qInfo("Window lifecycle: startup, interrupted fades, close, disabled motion and tray exit passed");
        else qWarning("Window lifecycle: application exited before the final fade completed");
    });
    QObject::connect(timer, &QTimer::timeout, &app, [&tray, &effects, &qmlErrors, window, state, underlay, behind, fail, invoke] {
        const auto elapsed = state->elapsed.elapsed();
        const auto advance = [state] { ++state->phase; state->elapsed.restart(); state->intermediate = false; };
        const auto capture = [window, underlay] {
            underlay->presentBehind(window);
            QCoreApplication::processEvents();
            if (!underlay->ownsCaptureArea(window)) return QImage{};
            const auto screen = window->screen()->geometry();
            const auto bounds = window->geometry();
            return window->screen()->grabWindow(0, bounds.x() - screen.x(), bounds.y() - screen.y(), bounds.width(), bounds.height()).toImage();
        };
        const auto fadeError = [state, behind](const QImage &frame, double alpha) {
            if (frame.isNull() || frame.size() != state->composite.size() || state->foreground.isEmpty()) return 1000.0;
            double error = 0;
            for (const auto point : state->foreground) {
                const auto full = state->composite.pixelColor(point), actual = frame.pixelColor(point);
                error += qAbs(actual.red() - (full.red() * alpha + behind.red() * (1 - alpha)));
                error += qAbs(actual.green() - (full.green() * alpha + behind.green() * (1 - alpha)));
                error += qAbs(actual.blue() - (full.blue() * alpha + behind.blue() * (1 - alpha)));
            }
            return error / (3 * state->foreground.size());
        };
        if (qmlErrors) { fail("QML warning"); return; }
        if (elapsed >= 20 && window->isVisible() &&
            window->opacity() > 0 && window->opacity() < 1) state->intermediate = true;
        if (state->phase == 0 && elapsed >= 300 && window->opacity() == 1) {
            if (!state->intermediate || window->opacity() != 1) { fail("startup did not fade to full opacity"); return; }
            window->setProperty("styleId", "glass"); window->setProperty("glassFrost", 40);
            window->setProperty("hideToTray", true);
            window->close();
            if (!window->isVisible() || !window->property("pendingHide").toBool()) { fail("close-to-tray skipped its animation"); return; }
            advance();
        } else if (state->phase == 1 && elapsed >= 100) {
            if (!state->intermediate) { fail("hide did not fade the whole window"); return; }
            const auto alpha = window->opacity(); invoke("restoreFromTray");
            if (window->opacity() != alpha || window->property("pendingHide").toBool()) { fail("reversing a hide jumped or retained its pending action"); return; }
            advance();
        } else if (state->phase == 2 && elapsed >= 300 && window->opacity() == 1) {
            if (!window->isVisible() || window->opacity() != 1) { fail("reversed reveal did not settle"); return; }
            invoke("hideToBackground"); invoke("hideToBackground"); advance();
        } else if (state->phase == 3 && elapsed >= 350) {
            if (window->isVisible() || window->property("pendingHide").toBool() || window->opacity() != 1) { fail("repeated hide did not finish cleanly"); return; }
            invoke("restoreFromTray"); window->setProperty("animationsEnabled", false);
            if (!window->isVisible() || window->opacity() != 1) { fail("disabling reveal left a transparent window"); return; }
            invoke("hideToBackground");
            if (window->isVisible()) { fail("disabled hide was deferred"); return; }
            invoke("restoreFromTray");
            if (!window->isVisible() || window->opacity() != 1) { fail("disabled reveal was deferred"); return; }
            window->setProperty("animationsEnabled", true); window->setProperty("hideToTray", false);
            window->close();
            if (!window->isVisible() || !window->property("pendingQuit").toBool()) { fail("normal close skipped its animation"); return; }
            advance();
        } else if (state->phase == 4 && elapsed >= 350) {
            if (!state->intermediate || window->isVisible() || window->property("pendingQuit").toBool()) { fail("normal close did not finish"); return; }
            invoke("restoreFromTray"); advance();
        } else if (state->phase == 5 && elapsed >= 300 && window->opacity() == 1) {
            if (!window->isVisible() || window->opacity() != 1 || (effects.available() && !effects.active())) { fail("Glass did not recover after closing and reopening"); return; }
            window->close(); advance();
        } else if (state->phase == 6 && elapsed >= 100) {
            if (!state->intermediate) { fail("second close did not fade"); return; }
            window->setProperty("animationsEnabled", false);
            if (window->isVisible() || window->property("pendingQuit").toBool()) { fail("disabling motion did not complete the close"); return; }
            invoke("restoreFromTray");
            if (!window->close() || window->isVisible()) { fail("disabled normal close was not accepted immediately"); return; }
            invoke("restoreFromTray"); window->setProperty("animationsEnabled", true); advance();
        } else if (state->phase == 7 && elapsed >= 400) {
            window->setProperty("animationsEnabled", false); window->setProperty("alwaysOnTop", true);
            const auto area = effects.workArea();
            window->setPosition(area.topLeft() + QPoint(3, 3)); invoke("snapToScreenEdge");
            if (window->position() != area.topLeft() + QPoint(8, 8)) {
                qWarning("Window docking: position=%d,%d expected=%d,%d visibility=%d visible=%d animations=%d",
                         window->x(), window->y(), area.x() + 8, area.y() + 8, int(window->visibility()), window->isVisible(), window->property("animationsEnabled").toBool());
                fail("docking after reveal did not settle"); return;
            }
            window->setProperty("alwaysOnTop", false);
            window->setProperty("styleId", "glass");
            underlay->setColor(behind); underlay->presentBehind(window); advance();
        } else if (state->phase == 8 && elapsed >= 250) {
            const auto scene = window->grabWindow();
            state->composite = capture(); state->foreground.clear();
            if (state->composite.isNull() || state->composite.size() != scene.size()) { fail("owned fade capture unavailable"); return; }
            // The header stays at the same position during the content slide.
            // Opaque foreground pixels also detect overlays before comparing fades.
            double error = 0;
            for (int y = 8; y < qRound(36 * scene.devicePixelRatio()); y += 2)
                for (int x = 12; x < scene.width() - 12; x += 2) {
                    const auto expected = scene.pixelColor(x, y);
                    if (expected.alpha() != 255) continue;
                    const auto actual = state->composite.pixelColor(x, y);
                    error += qAbs(expected.red() - actual.red()) + qAbs(expected.green() - actual.green()) + qAbs(expected.blue() - actual.blue());
                    state->foreground.append(QPoint(x, y));
                }
            if (state->foreground.size() < 10 || error / (3 * state->foreground.size()) > 15) { fail("owned fade foreground mismatch"); return; }
            window->setProperty("revealProgress", 0.4); advance();
        } else if (state->phase == 9 && elapsed >= 250) {
            const auto error = fadeError(capture(), 0.4);
            qInfo("Native window fade: style=%d alpha=0.4 mean error=%g", state->style, error);
            if (error > 15) { fail("native compositor did not fade the visible foreground"); return; }
            window->setProperty("revealProgress", 0.05); advance();
        } else if (state->phase == 10 && elapsed >= 250) {
            const auto error = fadeError(capture(), 0.05);
            qInfo("Native window fade: style=%d alpha=0.05 mean error=%g", state->style, error);
            if (error > 15) { fail("native compositor did not fade to the owned backdrop"); return; }
            window->setProperty("revealProgress", 1);
            if (++state->style < 3) {
                window->setProperty("styleId", state->style == 1 ? "classic" : "terminal-pro");
                state->phase = 8; state->elapsed.restart();
            } else advance();
        } else if (state->phase == 11 && elapsed >= 250) {
            underlay->hide(); advance();
        } else if (state->phase == 12 && elapsed >= 250) {
            window->setProperty("animationsEnabled", true);
            window->setProperty("hideToTray", true);
            invoke("hideToBackground");
            auto *quit = tray.menu()->findChild<QAction *>("trayQuit");
            if (!quit) { fail("tray quit action missing"); return; }
            quit->trigger(); quit->trigger();
            if (!window->isVisible() || !window->property("pendingQuit").toBool() || window->property("pendingHide").toBool()) { fail("tray exit did not supersede hide"); return; }
            advance();
        }
    });
    QTimer::singleShot(10000, &app, [fail] { fail("timeout"); });
    timer->start();
}
