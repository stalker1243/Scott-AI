#pragma once
#include <QApplication>
#include <QQuickItem>
#include <QQuickWindow>
#include <QDir>
#include <QImage>
#include <QTimer>
#include <memory>

inline void runResponsiveChecks(QApplication &app,QQuickWindow *window,QObject *preview,bool &qmlErrors) {
    auto phase=std::make_shared<int>(0);auto savedY=std::make_shared<double>(0);
    auto *timer=new QTimer(&app);timer->setInterval(200);
    auto fail=[&app,timer](const char *message){qWarning("Responsive UI: %s",message);timer->stop();app.exit(24);};
    QObject::connect(timer,&QTimer::timeout,&app,[&,window,preview,phase,savedY,timer,fail]{
        if(qmlErrors){fail("QML warning");return;}
        const int step=(*phase)++;
        auto *pages=window->findChild<QQuickItem *>("pages");
        auto *list=window->findChild<QQuickItem *>("chatList");
        auto centered=[&](QQuickItem *item){
            auto *rail=window->findChild<QQuickItem *>("navigationRail");
            const double left=rail->mapToItem(window->contentItem(),QPointF(rail->width(),0)).x();
            const double middle=item->mapToItem(window->contentItem(),QPointF(item->width()/2,0)).x();
            return qAbs(middle-(left+window->contentItem()->width()-8)/2)<1;
        };
        if(step==0){window->setProperty("animationsEnabled",false);window->resize(1920,1000);}
        else if(step==1){if(!pages||!centered(pages)){fail("wide pages are off center");return;}auto *signal=window->findChild<QQuickItem *>("overviewSignal");if(!signal||!centered(signal)){fail("overview is off center");return;}preview->setProperty("listening",true);preview->setProperty("inputLevel",.8);window->setProperty("animationsEnabled",true);}
        else if(step==2){auto *signal=window->findChild<QObject *>("overviewSignal");if(signal->property("energy").toDouble()<.75){fail("overview does not follow real input level");return;}window->setProperty("animationsEnabled",false);preview->setProperty("listening",false);window->setProperty("selectedTab",1);preview->setProperty("messages",QVariantList{QVariantMap{{"role","assistant"},{"text",QStringLiteral("Readable long response.\n").repeated(180)}}});}
        else if(step==3){if(!list||!centered(pages)||pages->width()>1040||!list->property("atYEnd").toBool()){fail("initial long response not readable at bottom");return;}list->setProperty("followTail",false);list->setProperty("contentY",list->property("originY").toDouble()+80);*savedY=list->property("contentY").toDouble();preview->setProperty("busy",true);preview->setProperty("messages",QVariantList{QVariantMap{{"role","assistant"},{"text",QStringLiteral("Readable long response.\n").repeated(200)}}});}
        else if(step==4){if(qAbs(list->property("contentY").toDouble()-*savedY)>1){fail("streaming stole the reader's position");return;}auto *jump=window->findChild<QObject *>("chatJumpLatest");if(!jump||!jump->property("visible").toBool()){fail("latest-message navigation missing");return;}QMetaObject::invokeMethod(jump,"clicked");}
        else if(step==5){if(!list->property("atYEnd").toBool()){fail("jump to latest failed");return;}window->resize(800,560);}
        else if(step==6){if(!centered(pages)||!list->property("atYEnd").toBool()||list->height()<200){fail("compact chat lost tail or viewport");return;}preview->setProperty("busy",false);window->setProperty("styleId","glass");window->setProperty("glassFrost",0);window->setProperty("selectedTab",4);}
        else if(step==7){if(window->property("glassFrost").toInt()!=1||window->findChild<QObject *>("memoryKind")||window->findChild<QObject *>("actionsPage")||window->findChild<QObject *>("protocolsPage")||window->findChild<QObject *>("navTab8")){fail("retired controls or clear Glass returned");return;}window->setProperty("selectedTab",8);}
        else if(step==8){if(window->property("selectedTab").toInt()!=0){fail("retired deep link did not fall back");return;}window->setProperty("selectedTab",7);}
        else if(step==9){if(window->property("selectedTab").toInt()!=0){fail("retired actions deep link did not fall back");return;}window->resize(1280,800);}
        else if(step==10){if(!centered(pages)){fail("medium pages are off center");return;}QDir().mkpath("screenshots/responsive");window->grabWindow().save("screenshots/responsive/overview.png");timer->stop();qInfo("Responsive UI: centered widths, microphone meter, memory, retired routes and scroll ownership passed");app.exit(0);}
    });
    QTimer::singleShot(10000,&app,[fail]{fail("timeout");});timer->start();
}
