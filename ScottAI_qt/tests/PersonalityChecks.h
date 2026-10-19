#pragma once
#include "ChatPageChecks.h"
#include "PetController.h"

inline void startPersonalityChecks(QApplication &app,QQuickWindow *window,PetController &pets,QObject *preview,bool &qmlErrors) {
    auto phase=std::make_shared<int>(0);auto *timer=new QTimer(&app);timer->setInterval(700);
    QObject::connect(timer,&QTimer::timeout,&app,[&,window,timer,phase,preview]{
        const auto fail=[&](const char *reason){qWarning("Personality UI: %s, phase %d",reason,*phase);timer->stop();app.exit(53);};
        const auto shot=[&](const QString &name){QDir().mkpath("screenshots/companions");return window->grabWindow().save("screenshots/companions/"+name+".png");};
        const auto click=[&](const QString &name){auto *item=chatVisual(window->contentItem(),name);return item&&QMetaObject::invokeMethod(item,"clicked");};
        auto *popup=window->findChild<QObject *>("appearancePopup");
        auto *voice=chatVisual(window->contentItem(),"overviewVoiceButton");
        auto *hint=window->findChild<QObject *>("overviewVoiceHint");
        if(window->opacity()!=1)return;
        if(qmlErrors||!popup||!preview||!voice||!hint){fail("QML or overview controls missing");return;}
        if(*phase==0){
            if(window->findChild<QObject *>("assistantFace")||!window->findChild<QObject *>("overviewSignal")){fail("overview must use the visual signal instead of the desktop pet");return;}
            if(window->property("selectedTab").toInt()!=0||preview->property("listeningWrites").toInt()){fail("overview default or automatic mic start");return;}
            window->resize(1000,720);window->setProperty("navigationExpanded",true);
        } else if(*phase==1){
            if(!voice->isEnabled()||voice->property("text").toString()!=QStringLiteral("Запустить Скотта")||!shot("overview")){fail("voice start control");return;}
            if(!click("overviewVoiceButton")||!preview->property("listening").toBool()||preview->property("listeningWrites").toInt()!=1){fail("mic start");return;}
        } else if(*phase==2){
            if(voice->property("text").toString()!=QStringLiteral("Остановить микрофон")||!hint->property("text").toString().contains(QStringLiteral("включён"))||!shot("overview-listening")){fail("active microphone state");return;}
            click("overviewVoiceButton");if(preview->property("listening").toBool()||preview->property("listeningWrites").toInt()!=2){fail("mic stop");return;}
            preview->setProperty("listeningBusy",true);click("overviewVoiceButton");
            if(voice->isEnabled()||preview->property("listeningWrites").toInt()!=2){fail("pending guard");return;}
            preview->setProperty("listeningBusy",false);preview->setProperty("listeningAvailable",false);
        } else if(*phase==3){
            if(voice->isEnabled()||!hint->property("text").toString().contains(QStringLiteral("недоступен"))||!shot("overview-no-microphone")){fail("unavailable microphone");return;}
            click("overviewVoiceButton");if(preview->property("listeningWrites").toInt()!=2){fail("unavailable click wrote");return;}
            preview->setProperty("listeningAvailable",true);preview->setProperty("listeningReady",false);
        } else if(*phase==4){
            if(voice->isEnabled()){fail("unknown microphone state enabled");return;}
            preview->setProperty("listeningReady",true);preview->setProperty("online",false);
        } else if(*phase==5){
            if(voice->isEnabled()||!shot("overview-offline")){fail("offline microphone");return;}
            preview->setProperty("online",true);preview->setProperty("listeningError",QStringLiteral("Не удалось открыть микрофон. Проверьте устройство."));
        } else if(*phase==6){
            auto *notice=window->findChild<QObject *>("overviewError");
            if(!notice||!notice->property("text").toString().contains(QStringLiteral("устройство"))||!shot("overview-voice-error")){fail("voice error hidden");return;}
            preview->setProperty("listeningError","");click("navigationMore");
        } else if(*phase==7){
            auto *menu=window->findChild<QObject *>("navigationMoreMenu");auto *entry=chatVisual(window->contentItem(),"navTab11");auto *background=menu?menu->property("background").value<QObject *>():nullptr;auto *theme=menu?menu->property("theme").value<QObject *>():nullptr;
            if(!menu||!entry||!entry->isVisible()||!background||!theme||background->property("color")!=theme->property("popup")||!shot("themed-menu")){fail("menu palette");return;}
            QMetaObject::invokeMethod(entry,"triggered");QMetaObject::invokeMethod(menu,"close");
        } else if(*phase==8){
            auto *about=window->findChild<QObject *>("aboutPage");auto *version=window->findChild<QObject *>("aboutVersion");
            if(window->property("selectedTab").toInt()!=11||!about||about->property("repository").toUrl().toString()!="https://github.com/stalker1243/Scott-AI"||!version||!version->property("text").toString().contains(app.applicationVersion())||!shot("about")){fail("about metadata");return;}
            window->setProperty("selectedTab",0);
        } else if(*phase==9){
            if(!click("overviewPetsButton")){fail("overview pet entry");return;}
        } else if(*phase==10){
            if(!popup->property("visible").toBool()||popup->property("section").toInt()!=1||!click("petChoice0")||chatVisual(window->contentItem(),"petChoice1")||!click("petColor_green")){fail("Scott-only picker");return;}
            auto *character=window->findChild<QObject *>("petLargePreview");if(!character){fail("preview");return;}QMetaObject::invokeMethod(character,"interact");
        } else if(*phase==12){
            if(pets.kind()!="scott"||pets.variant()!="green"||!shot("scott-junior")){fail("Scott preview");return;}
            auto *slider=chatVisual(window->contentItem(),"petSizeSlider");if(!slider){fail("size control");return;}
            slider->setProperty("value",150);QMetaObject::invokeMethod(slider,"moved");if(pets.sizePercent()!=150){fail("size slider");return;}
            auto *toggle=chatVisual(window->contentItem(),"desktopPetToggle");if(!toggle){fail("desktop toggle");return;}toggle->setProperty("checked",true);QMetaObject::invokeMethod(toggle,"toggled");
        } else if(*phase==13){
            if(!pets.enabled()||!pets.running()){fail("preview control must be inert but interactive");return;}
            pets.setEnabled(false);QMetaObject::invokeMethod(popup,"close");window->setProperty("darkMode",false);click("navigationMore");
        } else if(*phase==14){
            if(!shot("menu-light")){fail("light menu");return;}QMetaObject::invokeMethod(window->findChild<QObject *>("navigationMoreMenu"),"close");window->setProperty("darkMode",true);window->resize(800,560);preview->setProperty("listening",true);
        } else if(*phase==15){
            auto *page=qobject_cast<QQuickItem *>(window->findChild<QObject *>("overviewPage"));
            for(const QString name:{"overviewVoiceButton","overviewChatButton","overviewPetsButton","overviewVoiceHint"}){
                auto *item=chatVisual(window->contentItem(),name);if(!page||!item||!item->isVisible()){fail("compact overview missing control");return;}
                const auto position=item->mapToItem(page,QPointF());
                if(position.x()<-1||position.y()<-1||position.x()+item->width()>page->width()+1||position.y()+item->height()>page->height()+1){fail("compact overview clipping");return;}
            }
            if(!shot("overview-compact-listening")){fail("compact overview capture");return;}click("appearanceButton");
        } else if(*phase==16){
            const bool captured=shot("picker-compact");if(popup->property("width").toInt()>window->width()-32||popup->property("height").toInt()>window->height()-64||!captured||qmlErrors){fail("compact personalization");return;}
            timer->stop();qInfo("Overview microphone states, themed menus, about and Scott-only picker passed");app.exit(0);return;
        }
        ++*phase;
    });timer->start();
}
