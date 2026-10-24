#pragma once
#include "TrayController.h"
#include "WindowEffects.h"
#include <QApplication>
#include <QAction>
#include <QQuickWindow>
#include <QTimer>
#include <QElapsedTimer>
#include <memory>
#ifdef Q_OS_WIN
#include <qt_windows.h>
#endif
inline void runWindowLifecycleChecks(QApplication &app,QQuickWindow *window,TrayController &tray,
                                    WindowEffects &effects,bool &qmlErrors,bool &passed) {
    app.setQuitOnLastWindowClosed(false);
    struct State {int phase=0;bool intermediate=false;QElapsedTimer elapsed;};
    auto state=std::make_shared<State>();state->elapsed.start();
    auto *timer=new QTimer(&app);timer->setInterval(20);
    auto fail=[&app,timer](const char *message){qWarning("Window lifecycle: %s",message);timer->stop();app.exit(22);};
    QObject::connect(timer,&QTimer::timeout,&app,[&,state,timer,fail,window]{
        if(qmlErrors){fail("QML warning");return;}
        const double progress=window->property("revealProgress").toDouble();
        if(window->isVisible()&&progress>0&&progress<1){
            state->intermediate=true;
#ifdef Q_OS_WIN
            BYTE alpha=255;DWORD flags=0;
            if(!GetLayeredWindowAttributes(reinterpret_cast<HWND>(window->winId()),nullptr,&alpha,&flags)||
               !(flags&LWA_ALPHA)||qAbs(double(alpha)/255-progress)>.015){fail("native window alpha did not follow the fade");return;}
#endif
        }
        auto next=[state]{++state->phase;state->intermediate=false;state->elapsed.restart();};
        if(state->elapsed.elapsed()>2000){fail("transition did not settle");return;}
        if(state->phase==0&&progress==1){
            if(!state->intermediate||!window->isVisible()){fail("startup did not fade");return;}
            window->setProperty("hideToTray",false);window->close();next();
        } else if(state->phase==1&&!window->isVisible()){
            if(!state->intermediate){fail("close did not fade");return;}
            QMetaObject::invokeMethod(window,"restoreFromTray");next();
        } else if(state->phase==2&&progress==1){
            if(!state->intermediate||!window->isVisible()){fail("reopen did not fade");return;}
            window->setProperty("styleId","glass");window->showMaximized();next();
        } else if(state->phase==3&&state->elapsed.elapsed()>120){
            if(progress!=1||window->visibility()!=QWindow::Maximized||(effects.available()&&!effects.active())){fail("native maximize hid Glass");return;}
            QMetaObject::invokeMethod(window,"hideToBackground");next();
        } else if(state->phase==4&&progress>0&&progress<.9){
            const auto before=progress;tray.restoreWindow();
            if(!window->isVisible()||window->property("pendingHide").toBool()||qAbs(window->property("revealProgress").toDouble()-before)>.01){fail("interrupted hide jumped or stayed pending");return;}
            next();
        } else if(state->phase==5&&progress==1){
            if(window->visibility()!=QWindow::Maximized){fail("interrupted reveal lost maximized state");return;}
            window->setProperty("hideToTray",true);window->close();next();
        } else if(state->phase==6&&!window->isVisible()){
            if(!state->intermediate){fail("tray hide did not fade");return;}tray.restoreWindow();next();
        } else if(state->phase==7&&progress==1){
            if(!state->intermediate||window->visibility()!=QWindow::Maximized){fail("tray reveal did not animate or lost mode");return;}
            QMetaObject::invokeMethod(window,"hideToBackground");next();
        } else if(state->phase==8&&progress>0&&progress<.9){
            window->setProperty("animationsEnabled",false);
            if(window->isVisible()||window->property("pendingHide").toBool()){fail("reduced motion did not finish hide");return;}
            tray.restoreWindow();window->setProperty("hideToTray",false);
            if(!window->close()||window->isVisible()){fail("reduced motion close was not immediate");return;}
            tray.restoreWindow();window->showMinimized();window->setProperty("animationsEnabled",true);
            QMetaObject::invokeMethod(window,"requestQuit");
            if(window->isVisible()||window->property("pendingQuit").toBool()){fail("quit while minimized waited on an invisible animation");return;}
            passed=true;timer->stop();qInfo("Window lifecycle: native alpha frames, close, interruption, Glass, tray, reduced motion and minimized quit passed");app.exit(0);
        }
    });
    QTimer::singleShot(10000,&app,[fail]{fail("timeout");});timer->start();
}
