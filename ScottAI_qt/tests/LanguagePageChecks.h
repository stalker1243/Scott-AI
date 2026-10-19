#pragma once
#include "AppLanguage.h"
#include <QApplication>
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QQuickItem>
#include <QQuickWindow>
#include <QTimer>
#include <QJSValue>
#include <memory>
#include <functional>
#include <QDebug>

inline QQuickItem *languageItem(QQuickItem *parent,const QString &name){
    if(parent->objectName()==name)return parent;
    for(auto *child:parent->childItems())if(auto *found=languageItem(child,name))return found;
    return nullptr;
}
inline void startLanguageChecks(QApplication &app,QQuickWindow *window,QObject *fixture,AppLanguage &language,bool &qmlErrors){
    struct Page {int tab;int section;bool offline=false;};
    const QList<Page> pages{{0,0},{1,0},{2,0},{4,0},{5,0},{5,1},{5,2},{6,0},{7,0},{8,0},{9,0},{10,0},{11,0},{5,2,true}};
    const QStringList codes{"ru","en","de","es"};
    auto phase=std::make_shared<int>(0);auto results=std::make_shared<QJsonArray>();
    auto *timer=new QTimer(&app);timer->setInterval(130);
    window->setProperty("animationsEnabled",false);window->setProperty("navigationExpanded",true);
    auto *profile=window->findChild<QObject *>("profilePage");auto *protocol=window->findChild<QObject *>("protocolsPage");
    auto *model=window->findChild<QObject *>("modelsPage");
    if(!profile||!protocol||!model){qWarning("Localization: missing pages");app.exit(61);return;}
    profile->setProperty("nameDraft","Unchanged profile draft");protocol->setProperty("nameDraft","Unchanged protocol draft");
    model->setProperty("apiToken","opaque-fixture-token");
    const auto saveReports=[results]{QFile f("screenshots/localization/results.json");if(f.open(QIODevice::WriteOnly))f.write(QJsonDocument(*results).toJson());};
    QDir().mkpath("screenshots/localization");
    QObject::connect(timer,&QTimer::timeout,&app,[&app,&language,&qmlErrors,window,fixture,timer,phase,results,pages,codes,profile,protocol,model,saveReports]{
        const int current=(*phase)++,sample=current/2;
        if(sample>=pages.size()*codes.size()*2){
            timer->stop();saveReports();
            if(qmlErrors||fixture->property("settingsWrites").toInt()!=0||fixture->property("profileWrites").toInt()!=0||fixture->property("messagesSent").toInt()!=0){qWarning("Localization performed an operation or emitted QML errors");app.exit(61);return;}
            qInfo("Localization: four languages, compact/wide pages and preserved drafts passed");app.exit(0);return;
        }
        const auto page=pages[sample%pages.size()];const auto code=codes[(sample/pages.size())%4];const bool compact=sample<pages.size()*codes.size();
        if(current%2==0){
            fixture->setProperty("online",!page.offline);
            if(!language.setLanguage(code)){app.exit(61);return;}
            window->resize(compact?800:1200,compact?560:800);window->setProperty("selectedTab",page.tab);
            if(page.tab==5)window->findChild<QObject *>("settingsPage")->setProperty("section",page.section);
            return;
        }
        if(qmlErrors||profile->property("nameDraft").toString()!="Unchanged profile draft"||protocol->property("nameDraft").toString()!="Unchanged protocol draft"||model->property("apiToken").toString()!="opaque-fixture-token"){
            qWarning("Localization changed user drafts or caused QML errors");saveReports();app.exit(61);return;
        }
        if(page.tab==5&&page.section==2){
            auto *picker=languageItem(window->contentItem(),"interfaceLanguage");
            if(!picker||!picker->isEnabled()||picker->property("count").toInt()!=4||picker->property("currentIndex").toInt()!=codes.indexOf(code)){qWarning("Language picker is not synchronized");app.exit(61);return;}
        }
        QJsonArray texts;
        std::function<void(QQuickItem *)> collect=[&](QQuickItem *item){
            if(!item->isVisible())return;
            const auto text=item->property("text");
            if(text.isValid()&&!text.toString().isEmpty()) {
                const auto position=item->mapToItem(window->contentItem(),QPointF{});
                texts.append(QJsonObject{{"object",item->objectName()},{"class",item->metaObject()->className()},{"text",text.toString()},
                                         {"x",position.x()},{"y",position.y()},{"width",item->width()},{"height",item->height()}});
            }
            for(auto *child:item->childItems())collect(child);
        };collect(window->contentItem());
        for(const auto &name:QStringList{"chatWorkspace","memoryDraftCard","memorySearch","settingsTabs","newProtocol","applyModel","saveProfile"}){
            auto *item=languageItem(window->contentItem(),name);if(!item||!item->isVisible())continue;
            const auto position=item->mapToItem(window->contentItem(),QPointF{});
            if(item->width()<10||position.x()<-1||position.x()+item->width()>window->width()+1||position.y()<-1||position.y()+item->height()>window->height()+1){
                qWarning()<<"Localization: control outside window"<<code<<page.tab<<name<<position<<item->size();saveReports();app.exit(61);return;
            }
        }
        const auto image=QString("screenshots/localization/%1-%2-%3-%4%5.png").arg(code).arg(page.tab).arg(page.section).arg(compact?800:1200).arg(page.offline?"-offline":"");
        if(!window->grabWindow().save(image)){qWarning("Localization screenshot failed");app.exit(61);return;}
        results->append(QJsonObject{{"language",code},{"tab",page.tab},{"section",page.section},{"compact",compact},{"image",image},{"texts",texts}});
    });timer->start();
}
