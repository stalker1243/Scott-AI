#pragma once
#include "TrayController.h"
#include <QAction>
#include <QApplication>
#include <QElapsedTimer>
#include <QQuickWindow>
#include <QTimer>
#include <memory>
#ifdef Q_OS_WIN
#include <qt_windows.h>
#endif

// Only two owned fixture windows. No desktop input, backend or settings writes.
inline void runWindowStackingChecks(QApplication &app,QQuickWindow *window,
                                   TrayController &tray,bool &qmlErrors) {
    struct State { int phase=0;QElapsedTimer elapsed;QQuickWindow other; };
    auto state=std::make_shared<State>();state->elapsed.start();
    state->other.setColor(QColor("#438467"));
    auto *timer=new QTimer(&app);timer->setInterval(25);
    QObject::connect(timer,&QTimer::timeout,&app,[&,window,state,timer] {
        const auto fail=[&](const char *reason){qWarning("Window stacking: %s",reason);timer->stop();app.exit(46);};
        const auto next=[&]{++state->phase;state->elapsed.restart();};
        const auto normal=[&] {
            if(window->flags() & Qt::WindowStaysOnTopHint)return false;
#ifdef Q_OS_WIN
            return !(GetWindowLongPtrW(reinterpret_cast<HWND>(window->winId()),GWL_EXSTYLE)&WS_EX_TOPMOST);
#else
            return true;
#endif
        };
        const auto otherAbove=[&] {
#ifdef Q_OS_WIN
            const auto other=reinterpret_cast<HWND>(state->other.winId());
            for(auto above=GetWindow(reinterpret_cast<HWND>(window->winId()),GW_HWNDPREV);above;above=GetWindow(above,GW_HWNDPREV))
                if(above==other)return true;
            return false;
#else
            return true; // Native stacking is checked on Windows; compositor policy varies.
#endif
        };
        if(qmlErrors || state->elapsed.elapsed()>2500){fail("QML error or deadline");return;}
        if(state->elapsed.elapsed()<350)return;
        if(state->phase==0) {
            if(!normal()){fail("startup pinned the launcher");return;}
            state->other.setGeometry(window->geometry().adjusted(30,30,-30,-30));
            state->other.show();state->other.raise();state->other.requestActivate();next();
        } else if(state->phase==1) {
            if(!normal() || !otherAbove()){fail("launcher covered the foreground fixture");return;}
            tray.menu()->findChild<QAction *>("trayAlwaysOnTop")->trigger();next();
        } else if(state->phase==2) {
            if(!(window->flags() & Qt::WindowStaysOnTopHint)){fail("explicit pin was ignored");return;}
            tray.menu()->findChild<QAction *>("trayAlwaysOnTop")->trigger();
            state->other.raise();state->other.requestActivate();next();
        } else if(state->phase==3) {
            if(!normal() || !otherAbove()){fail("unpin did not return to normal stacking");return;}
            state->other.hide();window->setProperty("styleId","glass");
            QMetaObject::invokeMethod(window,"maximizeAnimated");next();
        } else if(state->phase==4) {
            QMetaObject::invokeMethod(window,"restoreSizeAnimated");next();
        } else if(state->phase==5) {
            state->other.raise();state->other.show();state->other.raise();next();
        } else {
            if(!normal() || !otherAbove()){fail("Glass or window animations retained topmost stacking");return;}
            timer->stop();qInfo("Window stacking: startup, foreground switch, explicit pin/unpin and Glass restore passed");app.exit(0);
        }
    });
    timer->start();
}
