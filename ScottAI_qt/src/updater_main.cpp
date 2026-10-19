#include "UpdateWindow.h"
#include "AppLog.h"
#include <QApplication>
#include "AppLanguage.h"
#include <QCommandLineParser>
#include <QJsonDocument>
#include <QTimer>
#include <QDir>
#include <QStyleHints>

int main(int argc,char **argv) {
    QApplication app(argc,argv);app.setApplicationName("ScottAIUpdater");app.setOrganizationName("ScottAI");
    app.styleHints()->setColorScheme(Qt::ColorScheme::Dark);
#ifdef Q_OS_LINUX
    app.setDesktopFileName("com.scottai.launcher");
#endif
    QCommandLineParser parser;parser.addHelpOption();parser.addOption({"job","Update handoff file","path"});
    parser.addOption({"smoke-test","Preview the updater with synthetic progress; no network, installation or restart."});parser.process(app);
    const bool preview=parser.isSet("smoke-test");AppLanguage language(preview);QJsonObject job;
    if(preview)job={{"release",QJsonObject{{"version","9.0.0"}}}};
    else {
        QFile file(parser.value("job"));
        if(!file.open(QIODevice::ReadOnly) || file.size()>32768)return 2;
        QJsonParseError error;auto document=QJsonDocument::fromJson(file.readAll(),&error);
        if(error.error!=QJsonParseError::NoError || !document.isObject())return 2;
        job=document.object();
        job["_directory"]=QFileInfo(parser.value("job")).absolutePath();
    }
    AppLog::directory=preview?QDir::currentPath()+"/test-logs":AppLog::defaultDirectory();
    UpdateWindow window(job,preview);window.show();
    if(preview) {
        auto phase=std::make_shared<int>(0);auto *timer=new QTimer(&app);timer->setInterval(450);
        QObject::connect(timer,&QTimer::timeout,&app,[&,phase]{
            if(*phase==3){app.exit(0);return;}
            window.previewState(*phase);QDir().mkpath("screenshots/updater");
            QTimer::singleShot(100,&app,[&,phase]{
                if(!window.grab().save(QString("screenshots/updater/%1.png").arg(*phase)))app.exit(4);++*phase;
            });
        });timer->start();
    } else QTimer::singleShot(0,&window,&UpdateWindow::begin);
    return app.exec();
}
