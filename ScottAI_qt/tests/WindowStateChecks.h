#pragma once
#include "WindowMotion.h"
#include "WindowEffects.h"
#include "TrayController.h"
#include <QApplication>
#include <QAction>
#include <QKeyEvent>
#include <QQuickItem>
#include <QScreen>
#include <QTimer>
#include <QElapsedTimer>
#include <memory>
#ifdef Q_OS_WIN
#include <qt_windows.h>
#endif
inline QQuickItem *windowStateItem(QQuickItem *p,const QString &n) {
    if(p->objectName()==n)return p;
    for(auto *c:p->childItems())if(auto *found=windowStateItem(c,n))return found;
    return nullptr;
}
// Native transitions are observed at their settled state. DWM/compositor
// animation frames are not client geometry frames and must not be asserted.
inline void runWindowStateChecks(QApplication &app,QQuickWindow *window,WindowMotion &motion,
                                 WindowEffects &effects,TrayController &tray,bool &qmlErrors,bool &passed) {
    auto step=std::make_shared<int>(0);auto normal=std::make_shared<QRect>();
    auto *timer=new QTimer(&app);timer->setInterval(160);
    auto fail=[&app,timer](const char *message){qWarning("Native window states: %s",message);timer->stop();app.exit(23);};
    auto click=[window](const char *name){auto *item=windowStateItem(window->contentItem(),name);return item&&QMetaObject::invokeMethod(item,"clicked");};
    auto key=[window](int code){QKeyEvent p(QEvent::KeyPress,code,Qt::NoModifier),r(QEvent::KeyRelease,code,Qt::NoModifier);QCoreApplication::sendEvent(window,&p);QCoreApplication::sendEvent(window,&r);};
    auto restore=[&tray]{tray.menu()->findChild<QAction *>("trayChat")->trigger();};
    QObject::connect(timer,&QTimer::timeout,&app,[&,step,normal,timer,fail,click,key,restore,window]{
        if(qmlErrors){fail("QML warning");return;}
        if(motion.running()){fail("client geometry animation must be disabled");return;}
        if(window->property("presentationAnimating").toBool())return;
        if(window->opacity()!=1){fail("state transition made the window transparent");return;}
        const int phase=(*step)++;
        auto expect=[&](QWindow::Visibility state){return window->visibility()==state && (state==QWindow::Minimized || window->isVisible());};
        if(phase==0){window->setProperty("styleId","glass");*normal=QRect(effects.workArea().topLeft()+QPoint(80,60),QSize(920,660));window->setGeometry(*normal);click("windowMaximize");}
        else if(phase==1){if(!expect(QWindow::Maximized)){fail("maximize failed");return;}click("windowMaximize");}
        else if(phase==2){if(!expect(QWindow::Windowed)||window->geometry()!=*normal){fail("restore lost placement");return;}for(int i=0;i<10;++i)motion.toggleMaximized();}
        else if(phase==3){if(!expect(QWindow::Windowed)||window->geometry()!=*normal){fail("rapid toggles lost placement");return;}key(Qt::Key_F11);}
        else if(phase==4){if(!expect(QWindow::FullScreen)||window->geometry()!=window->screen()->geometry()){fail("F11 failed");return;}key(Qt::Key_Escape);}
        else if(phase==5){if(!expect(QWindow::Windowed)||window->geometry()!=*normal){fail("Esc lost placement");return;}motion.maximize();key(Qt::Key_F11);}
        else if(phase==6){if(!expect(QWindow::FullScreen)){fail("maximized to fullscreen failed");return;}click("windowMinimize");}
        else if(phase==7){if(!expect(QWindow::Minimized)){fail("native minimize failed");return;}restore();}
        else if(phase==8){if(!expect(QWindow::FullScreen)){fail("tray lost fullscreen");return;}key(Qt::Key_Escape);}
        else if(phase==9){if(!expect(QWindow::Maximized)){fail("Esc lost maximized mode");return;}QMetaObject::invokeMethod(window,"hideToBackground");}
        else if(phase==10){if(window->isVisible()){fail("tray hide failed");return;}restore();}
        else if(phase==11){if(!expect(QWindow::Maximized)||(effects.available()&&!effects.active())){fail("tray lost state/material");return;}
#ifdef Q_OS_WIN
            PostMessageW(reinterpret_cast<HWND>(window->winId()),WM_SYSCOMMAND,SC_RESTORE,0);
#else
            motion.restore();
#endif
        }
        else if(phase==12){if(!expect(QWindow::Windowed)||window->geometry()!=*normal){fail("native restore lost placement");return;}
#ifdef Q_OS_WIN
            PostMessageW(reinterpret_cast<HWND>(window->winId()),WM_SYSCOMMAND,SC_MAXIMIZE,0);
#else
            motion.maximize();
#endif
        }
        else if(phase==13){if(!expect(QWindow::Maximized)){fail("system maximize failed");return;}
#ifdef Q_OS_WIN
            PostMessageW(reinterpret_cast<HWND>(window->winId()),WM_SYSCOMMAND,SC_MINIMIZE,0);
#else
            window->showMinimized();
#endif
        }
        else if(phase==14){if(!expect(QWindow::Minimized)){fail("system minimize failed");return;}
#ifdef Q_OS_WIN
            PostMessageW(reinterpret_cast<HWND>(window->winId()),WM_SYSCOMMAND,SC_RESTORE,0);
#else
            restore();
#endif
        }
        else if(phase==15){if(!expect(QWindow::Maximized)){fail("taskbar restore lost maximize");return;}window->setProperty("animationsEnabled",false);motion.restore();}
        else if(phase==16){if(!expect(QWindow::Windowed)||window->geometry()!=*normal){fail("reduced motion lost placement");return;}passed=true;timer->stop();qInfo("Native states: rapid toggles, F11/Esc, taskbar, minimize, tray, material and placement passed");app.exit(0);}
    });
    QTimer::singleShot(15000,&app,[fail]{fail("timeout");});timer->start();
}
