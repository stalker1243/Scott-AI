#include "UpdateController.h"
#include <QtTest>
#include <QTemporaryDir>
#include <QSignalSpy>
#include <QLibraryInfo>
#include <QFile>
#include <QDir>
#include <QJsonDocument>
#include <QCryptographicHash>
#include <QScopeGuard>
class UpdateControllerTests:public QObject {
    Q_OBJECT
public:
    static int scenario(QCoreApplication &app) {
        const auto root=QDir::cleanPath(QDir(QCoreApplication::applicationDirPath()).absoluteFilePath(".."));
        if(!QFileInfo::exists(root+"/.updater-fixture") && !QFileInfo::exists(root+"/launcher/.updater-fixture"))return 20;
        if(!app.arguments().contains("--fixture-update")) {
#ifdef Q_OS_LINUX
            QFile proof(qEnvironmentVariable("SCOTT_FIXTURE_PROOF"));if(!proof.open(QIODevice::WriteOnly))return 21;
            QFile metadata(root+"/VERSION.json");if(!metadata.open(QIODevice::ReadOnly))return 21;
            const QJsonObject value{{"restarted",true},{"provider_environment_preserved",qEnvironmentVariable("SCOTT_FIXTURE_API_KEY")=="fixture-environment-only"},
                {"image",qEnvironmentVariable("APPIMAGE")},{"root",root},
                {"version",QJsonDocument::fromJson(metadata.readAll()).object()["version"]}};
            proof.write(QJsonDocument(value).toJson());return 0;
#else
            QFile proof(root+"/restart-proof");if(!proof.open(QIODevice::WriteOnly))return 21;
            proof.write(qEnvironmentVariable("SCOTT_FIXTURE_API_KEY")=="fixture-environment-only" ? "restarted; provider environment preserved" : "restarted; provider environment missing");return 0;
#endif
        }
#ifdef Q_OS_LINUX
        const auto cache=qEnvironmentVariable("SCOTT_FIXTURE_CACHE");
        const auto args=app.arguments();const auto index=args.indexOf("--python");
        if(index<0 || index+1>=args.size())return 25;
        UpdateController controller(root,args[index+1],false,nullptr,cache);
        if(controller.m_image.isEmpty())return 26;
        auto &r=controller.m_release;r.version="9.0.0";r.available=true;r.repo="test/scott";
        r.name="ScottAI-9.0.0-Qt-linux-x86_64.AppImage";r.download=QUrl("https://github.com/test/scott/releases/download/v9/"+r.name);
        QFile installer(qEnvironmentVariable("SCOTT_FIXTURE_IMAGE"));if(!installer.open(QIODevice::ReadOnly))return 22;
#else
        const auto cache=root+"/fixture-cache";
        UpdateController controller(root,root+"/runtime/python.exe",false,nullptr,cache);
        auto &r=controller.m_release;r.version="9.0.0";r.available=true;r.repo="test/scott";
        r.name="ScottAI-9.0.0-Qt-setup.exe";r.download=QUrl("https://github.com/test/scott/releases/download/v9/"+r.name);
        QFile installer(root+"/installer-probe.exe");if(!installer.open(QIODevice::ReadOnly))return 22;
#endif
        const auto bytes=installer.readAll();r.sha256=QString::fromLatin1(QCryptographicHash::hash(bytes,QCryptographicHash::Sha256).toHex());r.size=bytes.size();
        const auto identity=controller.m_image.isEmpty()?root:controller.m_image["path"].toString();
        const auto key=QString::fromLatin1(QCryptographicHash::hash((identity+"/"+r.download.toString()).toUtf8(),QCryptographicHash::Sha256).toHex());
        QDir().mkpath(cache+"/downloads/"+key);
        if(!qEnvironmentVariableIsSet("SCOTT_FIXTURE_NO_DOWNLOAD_CACHE")
            && !QFile::copy(installer.fileName(),cache+"/downloads/"+key+"/"+r.name))return 23;
        QObject::connect(&controller,&UpdateController::handoffReady,&app,&QCoreApplication::quit);
        QTimer::singleShot(40000,&app,[&]{app.exit(24);});controller.install();return app.exec();
    }
private slots:
    void appImageContextAndHandoff() {
#ifndef Q_OS_LINUX
        QSKIP("AppImage inode and runtime context are Linux-only");
#else
        QTemporaryDir dir;const auto root=dir.path()+"/payload",path=dir.path()+"/Scott AI.AppImage";
        for(const auto &name:{"launcher","lib","plugins","backend"})QDir().mkpath(root+"/"+name);
        QVERIFY(QFile::copy(QCoreApplication::applicationDirPath()+"/update_probe",root+"/launcher/ScottAIUpdater"));
        for(const auto &name:{"launcher/qt.conf","backend/update_package.py","backend/update_appimage.py"}) {
            QFile file(root+"/"+name);QVERIFY(file.open(QIODevice::WriteOnly));file.write("fixture");
        }
        {QFile file(root+"/.scott-linux-install.json");QVERIFY(file.open(QIODevice::WriteOnly));file.write("{\"image_layout\":1}");}
        QByteArray header(64,'\0');header.replace(0,6,QByteArray::fromHex("7f454c460201"));
        header.replace(8,3,QByteArray("AI\2",3));header.replace(18,2,QByteArray::fromHex("3e00"));
        {QFile file(path);QVERIFY(file.open(QIODevice::WriteOnly));file.write(header);}
        const auto previousImage=qgetenv("APPIMAGE"),previousDir=qgetenv("APPDIR");
        const bool hadImage=qEnvironmentVariableIsSet("APPIMAGE"),hadDir=qEnvironmentVariableIsSet("APPDIR");
        const auto restore=qScopeGuard([=]{if(hadImage)qputenv("APPIMAGE",previousImage);else qunsetenv("APPIMAGE");
            if(hadDir)qputenv("APPDIR",previousDir);else qunsetenv("APPDIR");});
        qputenv("APPIMAGE",path.toUtf8());qputenv("APPDIR",root.toUtf8());
        UpdateController controller(root,QCoreApplication::applicationFilePath(),false,nullptr,dir.path()+"/cache");
        auto &release=controller.m_release;release.available=true;release.repo="test/scott";release.version="9.0.0";
        release.sha256=QString(64,'a');release.size=128;release.name="ScottAI-9.0.0-Qt-linux-x86_64.AppImage";
        release.download=QUrl("https://github.com/test/scott/releases/download/v9/"+release.name);
        QCOMPARE(controller.m_image["path"].toString(),path);QVERIFY(controller.canInstall());
        QSignalSpy ready(&controller,&UpdateController::handoffReady);controller.install();
        QTRY_COMPARE_WITH_TIMEOUT(ready.count(),1,10000);
        QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(root+"/handoff-proof"),3000);
        const auto jobs=QDir(dir.path()+"/cache").entryList(QDir::Dirs|QDir::NoDotAndDotDot);QCOMPARE(jobs.size(),1);
        QFile job(dir.path()+"/cache/"+jobs[0]+"/job.json");QVERIFY(job.open(QIODevice::ReadOnly));
        QCOMPARE(QJsonDocument::fromJson(job.readAll()).object()["image"].toObject()["path"].toString(),path);
        {QFile file(path);QVERIFY(file.open(QIODevice::Append));file.write("manual change");}
        QVERIFY(!controller.canInstall());
#endif
    }
    void noHandoffWithoutVerifiedRelease() {
        QTemporaryDir dir;UpdateController controller(dir.path(),"fixture",true,nullptr,dir.path()+"/cache");
        QSignalSpy handoff(&controller,&UpdateController::handoffReady);
        controller.check();controller.install();QVERIFY(!controller.busy());QVERIFY(!controller.canInstall());QCOMPARE(handoff.count(),0);
    }
    void actualSeparateProcessHandshake() {
        QTemporaryDir dir;auto root=dir.path()+"/Scott AI fixture";QDir().mkpath(root+"/launcher");QDir().mkpath(root+"/runtime");
#ifdef Q_OS_WIN
        QVERIFY(QFile::copy(QCoreApplication::applicationDirPath()+"/update_probe.exe",root+"/launcher/ScottAIUpdater.exe"));
        QFile python(root+"/runtime/python.exe");QVERIFY(python.open(QIODevice::WriteOnly));python.write("not executed");python.close();
        for(const auto &name:{"Qt6Core.dll","Qt6Network.dll"})QVERIFY(QFile::copy(QLibraryInfo::path(QLibraryInfo::BinariesPath)+"/"+name,root+"/launcher/"+name));
        for(const auto &name:{"libgcc_s_seh-1.dll","libstdc++-6.dll","libwinpthread-1.dll"}) {
            QString path;
            for(const auto &entry:qEnvironmentVariable("PATH").split(QDir::listSeparator()))
                if(QFileInfo::exists(entry+"/"+name)){path=entry+"/"+name;break;}
            QVERIFY2(!path.isEmpty(),name);QVERIFY(QFile::copy(path,root+"/launcher/"+name));
        }
#else
        QVERIFY(QFile::copy(QCoreApplication::applicationDirPath()+"/update_probe",root+"/launcher/ScottAIUpdater"));
        for(const auto &name:{"lib","plugins","backend"})QDir().mkpath(root+"/"+name);
        for(const auto &name:{"launcher/qt.conf","backend/update_package.py"}){QFile file(root+"/"+name);QVERIFY(file.open(QIODevice::WriteOnly));file.write("fixture");}
        {QFile file(root+"/.scott-linux-install.json");QVERIFY(file.open(QIODevice::WriteOnly));file.write("{\"image_layout\":1}");}
#endif
        UpdateController controller(root,QCoreApplication::applicationFilePath(),false,nullptr,dir.path()+"/cache");
        controller.m_release.version="9.0.0";controller.m_release.available=true;controller.m_release.repo="test/scott";controller.m_release.sha256=QString(64,'a');controller.m_release.size=16;
#ifdef Q_OS_WIN
        controller.m_release.name="ScottAI-9.0.0-Qt-setup.exe";
#else
        controller.m_release.name="ScottAI-9.0.0-Qt-linux-x86_64.tar.gz";
#endif
        controller.m_release.download=QUrl("https://github.com/test/scott/releases/download/v9/"+controller.m_release.name);
#ifndef Q_OS_WIN
        QVERIFY(!controller.canInstall());
        {QFile file(root+"/.scott-linux-install.json");QVERIFY(file.open(QIODevice::WriteOnly));file.write("{}");}
#endif
        QVERIFY(controller.canInstall());QSignalSpy ready(&controller,&UpdateController::handoffReady);
        controller.install();QTRY_COMPARE_WITH_TIMEOUT(ready.count(),1,10000);
        QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(root+"/handoff-proof"),3000);
        QVERIFY(controller.busy());
    }
};
int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);
    const auto marker=QDir(QCoreApplication::applicationDirPath()).absoluteFilePath("../.updater-fixture");
    if(QFileInfo::exists(marker) || QFileInfo::exists(QCoreApplication::applicationDirPath()+"/.updater-fixture"))return UpdateControllerTests::scenario(app);
    UpdateControllerTests tests;return QTest::qExec(&tests,argc,argv);
}
#include "UpdateControllerTests.moc"
