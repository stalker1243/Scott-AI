#include "PetController.h"
#include "PetChatController.h"
#include "PetBackendSession.h"
#include "DesktopPetService.h"
#include "ProcessSupport.h"
#include <QApplication>
#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLocalSocket>
#include <QProcess>
#include <QSettings>
#include <QTemporaryDir>
#include <QTest>
#include <QSignalSpy>
#include <QScopeGuard>
#include <QQmlApplicationEngine>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQuickItem>
#include <QQuickWindow>
#include <QScreen>
#include <QTcpServer>
#include <QTcpSocket>
#include <QJsonArray>
#include <cmath>
#include <atomic>
#include <QDateTime>
#include <QEnterEvent>
#include <QSaveFile>
#include <QStyleHints>
#ifdef Q_OS_WIN
#include <dwmapi.h>
#endif

static QJsonObject request(const QString &profile,const QJsonObject &value) {
    QLocalSocket socket;socket.connectToServer(PetController::serverName(profile));
    if(!socket.waitForConnected(800))return {};
    socket.write(QJsonDocument(value).toJson(QJsonDocument::Compact)+'\n');socket.waitForBytesWritten(800);
    QByteArray bytes;
    while(!bytes.endsWith('\n')){if(!socket.waitForReadyRead(1000))return {};bytes+=socket.readAll();if(bytes.size()>4096)return {};}
    return QJsonDocument::fromJson(bytes).object();
}
static QJsonObject command(const QString &profile,const QString &op) {
    return request(profile,{{"op",op}});
}

// A disposable backend-shaped process, launched through the real QProcess path.
// Only this test executable understands this fixture, never the shipped launcher.
static int fixtureBackend(QApplication &app,const QString &path) {
    QFile file(path);if(!file.open(QIODevice::ReadOnly))return 61;
    const auto config=QJsonDocument::fromJson(file.readAll()).object();
    if(config["fixture"]!=true)return 62;
    QTcpServer server;if(!server.listen(QHostAddress::LocalHost,config["port"].toInt()))return 63;
    QObject::connect(&server,&QTcpServer::newConnection,&app,[&]{
        auto *socket=server.nextPendingConnection();auto bytes=std::make_shared<QByteArray>();
        QObject::connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
        QObject::connect(socket,&QTcpSocket::readyRead,socket,[&,socket,bytes]{
            *bytes+=socket->readAll();const int split=bytes->indexOf("\r\n\r\n");if(split<0)return;
            int length=0;for(const auto &line:bytes->left(split).split('\n'))if(line.toLower().startsWith("content-length:"))length=line.mid(15).trimmed().toInt();
            if(bytes->size()<split+4+length)return;
            const auto route=bytes->split(' ').value(1);QJsonObject result{{"status","online"}};
            if(route=="/chats"||route.endsWith("/messages")) {
                QJsonArray rows;
                if(route.endsWith("/messages")) {
                    rows={QJsonObject{{"role","user"},{"text","hello"},{"attachments",QJsonArray{}}},QJsonObject{{"role","assistant"},{"text","Cold fixture ready"},{"attachments",QJsonArray{}}}};
                    QFile proof(path+".received");if(proof.open(QIODevice::WriteOnly))proof.write(bytes->mid(split+4,length));
                }
                result={{"success",true},{"chat",QJsonObject{{"id",QString(32,'b')},{"title","Cold fixture"},{"messages",rows}}},{"chats",QJsonArray{}}};
            } else if(route=="/browser")result={{"state","idle"}};
            const auto payload=QJsonDocument(result).toJson(QJsonDocument::Compact);
            socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "+QByteArray::number(payload.size())+"\r\n\r\n"+payload);socket->disconnectFromHost();bytes->clear();
        });
    });
    return app.exec();
}

// Only this test helper accepts fixture paths. The production service has no
// file operations in its local protocol.
static int packagedFixture(const QStringList &args) {
    const auto root=QDir(args.value(2)).absolutePath();
    const auto source=args.value(3),prefix=QDir(args.value(4)).absolutePath();
    if(!prefix.startsWith(root+"/") || !QFileInfo::exists(source))return 10;
    const auto profile=root+"/profile";
    const auto cleanup=qScopeGuard([&]{command(profile,"quit");});
    QProcess parent;backgroundProcess(parent);
    parent.setProgram(QCoreApplication::applicationFilePath());
    parent.setArguments({"--fixture-parent",root,source});parent.start();
    if(!parent.waitForFinished(45000) || parent.exitCode()!=0) {
        qWarning().noquote()<<parent.readAllStandardError();return 11;
    }
    if(!command(profile,"state")["ready"].toBool())return 12;
    if(!QDir().rename(prefix,prefix+"-offline"))return 13;
    command(profile,"quit");
    for(int i=0;i<50 && command(profile,"state")["ready"].toBool();++i)QTest::qWait(100);
    const auto folders=QDir(root+"/cache").entryList(QDir::Dirs|QDir::NoDotAndDotDot);
    if(folders.size()!=1)return 14;
    const auto runtime=root+"/cache/"+folders.first();
#ifdef Q_OS_WIN
    const auto executable=runtime+"/launcher/ScottAIPet.exe";
#else
    const auto executable=runtime+"/launcher/ScottAIPet";
#endif
    auto env=QProcessEnvironment::systemEnvironment();
    const auto platform=env.value("QT_QPA_PLATFORM");
    for(const auto &key:env.keys())if(key.startsWith("QT_") || key.startsWith("QML_") || key=="LD_LIBRARY_PATH" || key=="PYTHONHOME" || key=="PYTHONPATH")env.remove(key);
    if(!platform.isEmpty())env.insert("QT_QPA_PLATFORM",platform);
#ifdef Q_OS_WIN
    env.insert("PATH",env.value("SystemRoot")+"/System32");
#else
    env.insert("PATH","/usr/bin:/bin");env.insert("LD_LIBRARY_PATH",runtime+"/lib");env.insert("QT_PLUGIN_PATH",runtime+"/plugins");env.insert("QML_IMPORT_PATH",runtime+"/qml");
#endif
    env.insert("QT_QUICK_BACKEND","software");env.insert("QSG_RHI_BACKEND","software");
    QProcess cached;backgroundProcess(cached);cached.setProcessEnvironment(env);
    cached.setProgram(executable);cached.setArguments({"--desktop-pet","--pet-state",profile});cached.setWorkingDirectory(runtime);cached.start();
    if(!cached.waitForStarted(4000))return 15;
    QJsonObject state;
    for(int i=0;i<100;++i){state=command(profile,"state");if(state["ready"].toBool())break;QTest::qWait(100);}
    if(!state["ready"].toBool()){qWarning().noquote()<<cached.readAllStandardError();return 16;}
    QProcess duplicate;backgroundProcess(duplicate);duplicate.setProcessEnvironment(env);duplicate.setProgram(executable);duplicate.setArguments(cached.arguments());duplicate.start();
    if(!duplicate.waitForFinished(8000) || duplicate.exitCode()!=0 || command(profile,"state")["pid"]!=state["pid"])return 17;
    const auto configured=request(profile,{{"op","configure"},{"kind","scott"},{"variant","green"},{"motion",false}});
    if(configured["kind"]!="scott" || configured["variant"]!="green" || configured["motion"].toBool(true) || !configured["scottOnly"].toBool())return 18;
    command(profile,"play");command(profile,"quit");
    if(!cached.waitForFinished(5000) || cached.exitCode()!=0)return 19;
    QFile processLog(root+"/cached-stderr.log");
    if(!processLog.open(QIODevice::WriteOnly))return 22;
    processLog.write(cached.readAllStandardError());processLog.close();
    QSettings settings(profile+"/settings.ini",QSettings::IniFormat);settings.sync();
    if(settings.value("enabled").toBool() || settings.value("motion",true).toBool() || settings.value("kind")!="scott")return 20;
    qint64 bytes=0;int count=0;QDirIterator files(runtime,QDir::Files,QDirIterator::Subdirectories);
    while(files.hasNext()){bytes+=QFileInfo(files.next()).size();++count;}
    QFile proof(root+"/packaged-result.json");if(!proof.open(QIODevice::WriteOnly))return 21;
    proof.write(QJsonDocument(QJsonObject{{"parent_exited",true},{"original_prefix_renamed",true},{"cached_restart_clean_environment",true},{"single_instance",true},{"configure_pause_play_stop",true},{"runtime_bytes",bytes},{"runtime_files",count}}).toJson());
    qInfo("Packaged pet survived parent exit and restarted without its original prefix or SDK paths");
    return 0;
}
class PetTests:public QObject {
    Q_OBJECT
private slots:
    void previewNeverStartsOrWrites() {
        QTemporaryDir dir;QVERIFY(dir.isValid());
        PetController pet(true,dir.path()+"/profile",dir.path()+"/cache");
        pet.selectPet("spike");QCOMPARE(pet.kind(),QString("scott"));QCOMPARE(pet.variant(),QString("blue"));
        pet.selectVariant("cyan");QCOMPARE(pet.variant(),QString("blue"));
        pet.selectVariant("black");pet.setEnabled(true);QVERIFY(pet.enabled());QVERIFY(pet.running());
        pet.setSizePercent(900);QCOMPARE(pet.sizePercent(),200);pet.setSizePercent(-3);QCOMPARE(pet.sizePercent(),50);
        pet.setEnabled(false);QVERIFY(!pet.running());QVERIFY(QDir(dir.path()).entryList(QDir::NoDotAndDotDot|QDir::AllEntries).isEmpty());
    }
    void settingsAndValidation() {
        QTemporaryDir dir;QVERIFY(dir.isValid());
        {PetController pet(false,dir.path()+"/profile",dir.path()+"/cache");pet.selectVariant("white");pet.setMotion(false);pet.setSizePercent(155);pet.selectPet("../../bad");pet.selectPet("spike");QCOMPARE(pet.kind(),QString("scott"));}
        PetController restored(false,dir.path()+"/profile",dir.path()+"/cache");QCOMPARE(restored.kind(),QString("scott"));QCOMPARE(restored.variant(),QString("white"));QVERIFY(!restored.motion());QVERIFY(!restored.enabled());
        QCOMPARE(restored.sizePercent(),155);
        QVERIFY(PetController::serverName(dir.path()+"/one")!=PetController::serverName(dir.path()+"/two"));
        QVERIFY(PetController::variants("russell").isEmpty());
        QVERIFY(PetController::variants("spike").isEmpty());
        QSettings old(dir.path()+"/old/settings.ini",QSettings::IniFormat);
        old.setValue("kind","russell");old.setValue("variant","scarlet");old.setValue("sizePercent",175);old.sync();
        PetController migrated(false,dir.path()+"/old",dir.path()+"/old-cache");
        QCOMPARE(migrated.kind(),QString("scott"));QCOMPARE(migrated.variant(),QString("blue"));QCOMPARE(migrated.sizePercent(),175);
    }
    void retiredCompanionKeepsPreferences() {
        QTemporaryDir directory;QVERIFY(directory.isValid());
        for(const QString kind:{"spike","russell"}) {
            const auto profile=directory.path()+"/"+kind;
            QSettings old(profile+"/settings.ini",QSettings::IniFormat);
            old.setValue("kind",kind);old.setValue("variant",kind=="spike"?"cyan":"scarlet");
            old.setValue("enabled",true);old.setValue("motion",false);old.setValue("sizePercent",165);
            old.setValue("position",QPoint(-170,85));old.sync();
            PetController migrated(false,profile,directory.path()+"/cache-"+kind);
            QCOMPARE(migrated.kind(),QString("scott"));QCOMPARE(migrated.variant(),QString("blue"));
            QVERIFY(migrated.enabled());QVERIFY(!migrated.motion());QCOMPARE(migrated.sizePercent(),165);
            DesktopPetService service(profile,false);QVERIFY(service.start());
            QCOMPARE(service.kind(),QString("scott"));QCOMPARE(service.variant(),QString("blue"));
            QVERIFY(!service.motion());QCOMPARE(service.sizePercent(),165);
            old.sync();QCOMPARE(old.value("position").toPoint(),QPoint(-170,85));
            QCOMPARE(old.value("kind").toString(),QString("scott"));
        }
        QQmlEngine engine;QSignalSpy warnings(&engine,&QQmlEngine::warnings);
        QQmlComponent component(&engine,QUrl::fromLocalFile(QStringLiteral(SCOTT_PET_QML_DIR "/PetCharacter.qml")));
        std::unique_ptr<QObject> character(component.create());QVERIFY2(character,qPrintable(component.errorString()));
        character->setProperty("kind","spike");QCOMPARE(character->property("kind").toString(),QString("scott"));
        QVERIFY(!character->findChild<QQuickItem *>("spikeLeftArm")->isVisible());
        QCOMPARE(warnings.count(),0);
    }
    void desktopResizeMenuAndMouseDrag() {
        QTemporaryDir dir;QVERIFY(dir.isValid());
        DesktopPetService service(dir.path());
        QQmlApplicationEngine engine;QSignalSpy warnings(&engine,&QQmlEngine::warnings);
        engine.rootContext()->setContextProperty("petService",&service);
        engine.load(QUrl::fromLocalFile(QStringLiteral(SCOTT_PET_QML_DIR "/DesktopPetWindow.qml")));
        QVERIFY2(!engine.rootObjects().isEmpty(),"Desktop pet QML did not load");
        auto *window=qobject_cast<QQuickWindow *>(engine.rootObjects().first());QVERIFY(window);
        QVERIFY(QTest::qWaitForWindowExposed(window));
        service.setSizePercent(50);QCOMPARE(window->size(),QSize(140,130));
        auto *menu=window->findChild<QObject *>("petContextMenu");QVERIFY(menu);
        QTest::mouseClick(window,Qt::RightButton,Qt::NoModifier,QPoint(70,60));
        QTRY_VERIFY(menu->property("visible").toBool());
        auto *content=menu->property("contentItem").value<QQuickItem *>();QVERIFY(content);
        QTRY_VERIFY(content->window() && content->window()!=window);
        QCOMPARE(menu->property("count").toInt(),2);
        QMetaObject::invokeMethod(menu,"close");QTRY_VERIFY(!menu->property("visible").toBool());
        QTRY_VERIFY(!content->window() || content->window()==window || !content->window()->isVisible());
        service.setSizePercent(200);QCOMPARE(window->size(),QSize(560,520));
        if(service.canReposition()) {
            QVERIFY(window->mask().contains(QPoint(280,200)));
            QVERIFY(!window->mask().contains(QPoint(4,4)));
            service.setSizePercent(100);
            const auto area=window->screen()->geometry();
            window->setPosition(area.center()-QPoint(140,130));
            QTest::qWait(80);
            // Deliver a fresh enter/move after the popup releases its native
            // grab and the resized X11 surface has processed ConfigureNotify.
            QTest::mouseMove(window,QPoint(140,120),30);QTest::qWait(100);
            const auto before=window->position();
            auto *pointer=window->findChild<QObject *>("petPointerArea");QVERIFY(pointer);
            QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,QPoint(140,120));
            QTRY_VERIFY(pointer->property("pressed").toBool());
            QTest::mouseMove(window,QPoint(210,155),20);
            QVERIFY2(service.dragging(),qPrintable(QString("dragging=%1 pressed=%2 delta=(%3,%4)").arg(service.dragging()).arg(pointer->property("pressed").toBool()).arg(window->x()-before.x()).arg(window->y()-before.y())));
            QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,QPoint(140,120));
            QTRY_VERIFY(!service.dragging());
            QCOMPARE(window->position(),before+QPoint(70,35));
            window->setPosition(area.topLeft()+QPoint(2,2));
            QTest::qWait(600);
            QSettings saved(dir.path()+"/settings.ini",QSettings::IniFormat);
            QCOMPARE(saved.value("position").toPoint(),area.topLeft()+QPoint(2,2));
            QRect desktop;for(auto *screen:QGuiApplication::screens())desktop=desktop.united(screen->geometry());
            window->setPosition(desktop.bottomRight()+QPoint(1000,1000));service.resetPosition();
            bool found=false;for(auto *screen:QGuiApplication::screens())found|=screen->geometry().contains(window->geometry());QVERIFY(found);
        }
        QCOMPARE(warnings.count(),0);
    }
    void gazeExpressionsAndReducedMotion() {
        QQmlEngine engine;QQmlComponent component(&engine,QUrl::fromLocalFile(QStringLiteral(SCOTT_PET_QML_DIR "/PetCharacter.qml")));
        std::unique_ptr<QObject> character(component.create());QVERIFY2(character,qPrintable(component.errorString()));
        auto *item=qobject_cast<QQuickItem *>(character.get());QVERIFY(item);
        QQuickWindow window;window.resize(280,260);item->setParentItem(window.contentItem());item->setSize(QSizeF(280,260));window.show();
        QVERIFY(QTest::qWaitForWindowExposed(&window));
        // QTest's QWindow mouseMove sends a move, not a native Enter event.
        // Supply the complete pointer sequence independently of the runner's
        // real cursor position; retain the actual hover and animation checks.
        const QPoint start(60,90);
        QEnterEvent enter(start,start,window.mapToGlobal(start));
        QCoreApplication::sendEvent(&window,&enter);
        QTest::mouseMove(&window,QPoint(60,90));
        QTRY_VERIFY2(character->property("lookX").toReal()<-0.3,
            qPrintable(QString("look=%1 gaze=%2 attention=%3").arg(character->property("lookX").toReal())
                .arg(character->property("gazeX").toReal()).arg(character->property("attention").toBool())));
        QDir().mkpath("screenshots/pets-motion");
        for(const auto &kind:{"scott"}) {
            character->setProperty("kind",kind);
            QTest::mouseMove(&window,QPoint(220,90));
            QTRY_VERIFY(character->property("lookX").toReal()>0.3);
            QTest::mouseClick(&window,Qt::LeftButton,Qt::NoModifier,QPoint(220,90));
            QTest::qWait(220);QVERIFY(character->property("joy").toReal()>0.7);
            QVERIFY(window.grabWindow().save(QString("screenshots/pets-motion/%1-happy.png").arg(kind)));
            QTest::mouseMove(&window,QPoint(60,90));
            QTRY_VERIFY(character->property("lookX").toReal()<-0.3);
        }
        character->setProperty("motion",false);QTest::qWait(250);
        QCOMPARE(character->property("lookX").toReal(),0.0);QCOMPARE(character->property("joy").toReal(),0.0);QCOMPARE(character->property("breath").toReal(),0.0);
        character->setProperty("motion",true);QTRY_VERIFY(character->property("breath").toReal()>0.01);
        character->setProperty("held",true);QVERIFY(!character->property("acting").toBool());
        QVERIFY(window.grabWindow().save("screenshots/pets-motion/carried.png"));
        item->setParentItem(nullptr);
    }
    void connectedLimbsAndExpressiveActions() {
        QQmlEngine engine;
        QSignalSpy warnings(&engine,&QQmlEngine::warnings);
        QQmlComponent component(&engine,QUrl::fromLocalFile(QStringLiteral(SCOTT_PET_QML_DIR "/PetCharacter.qml")));
        std::unique_ptr<QObject> character(component.create());QVERIFY2(character,qPrintable(component.errorString()));
        auto *item=qobject_cast<QQuickItem *>(character.get());QVERIFY(item);
        QQuickWindow window;window.setColor(QColor("#162131"));window.resize(560,520);
        item->setParentItem(window.contentItem());item->setSize(QSizeF(560,520));
        character->setProperty("interactive",false);window.show();QVERIFY(QTest::qWaitForWindowExposed(&window));
        QDir().mkpath("screenshots/pets-expression");
        auto save=[&](const QString &name){QTest::qWait(35);return window.grabWindow().save("screenshots/pets-expression/"+name+".png");};
        auto *animation=character->findChild<QObject *>("petPerformance");QVERIFY(animation);
        for(const QString kind:{"scott"}) {
            character->setProperty("kind",kind);character->setProperty("attention",false);
            character->setProperty("motion",false);QVERIFY(save(kind+"-idle"));
            character->setProperty("motion",true);
            QVERIFY(QMetaObject::invokeMethod(character.get(),"playAction",Q_ARG(QVariant,QString("laptop"))));
            QVERIFY(QMetaObject::invokeMethod(animation,"pause"));
            auto *left=character->findChild<QQuickItem *>(kind+"LeftArm");
            auto *right=character->findChild<QQuickItem *>(kind+"RightArm");QVERIFY(left);QVERIFY(right);
            QPointF previous,rest,previousElbows[2];bool moved=false;
            for(int frame=0;frame<=50;frame++) {
                character->setProperty("actionProgress",frame/50.0);
                int armIndex=0;
                for(auto *arm:{left,right}) {
                    const QPointF elbow(arm->property("elbowX").toReal(),arm->property("elbowY").toReal());
                    const QPointF hand(arm->property("handX").toReal(),arm->property("handY").toReal());
                    QVERIFY(qAbs(QLineF(QPointF(),elbow).length()-arm->property("upperLength").toReal())<0.001);
                    QVERIFY(qAbs(QLineF(elbow,hand).length()-arm->property("lowerLength").toReal())<0.001);
                    QVERIFY(qIsFinite(arm->property("shoulderAngle").toReal()));
                    auto *grip=qvariant_cast<QQuickItem *>(arm->property("grip"));QVERIFY(grip);
                    QVERIFY(QLineF(grip->mapToItem(arm,QPointF()),hand).length()<0.001);
                    if(frame==25 && kind=="scott") {
                        auto *laptop=character->findChild<QQuickItem *>("scottLaptop");QVERIFY(laptop);
                        const auto keys=grip->mapToItem(laptop,QPointF());
                        QVERIFY2(keys.x()>=7 && keys.x()<=101 && qAbs(keys.y()+8)<4,
                                 "Shorter hands must reach the keyboard, not the laptop screen");
                    }
                    if(kind=="scott") {
                        const qreal reach=arm->property("upperLength").toReal()+arm->property("lowerLength").toReal();
                        const qreal requested=std::hypot(arm->property("targetX").toReal(),arm->property("targetY").toReal());
                        QVERIFY2(requested<=reach-0.5,"Typing target is outside the shorter arm's reach");
                        QVERIFY2(QLineF(QPointF(),hand).length()>=reach*0.6,"Scott's elbow folds too tightly");
                        if(frame)QVERIFY2(QLineF(previousElbows[armIndex],elbow).length()<8,"Scott's elbow jumps while typing");
                        previousElbows[armIndex]=elbow;
                    }
                    armIndex++;
                }
                const QPointF hand(right->property("handX").toReal(),right->property("handY").toReal());
                if(frame)QVERIFY2(QLineF(previous,hand).length()<16,qPrintable(kind+" hand jumped"));
                else rest=hand;
                moved|=QLineF(rest,hand).length()>15;
                previous=hand;
            }
            QVERIFY2(moved,qPrintable(kind+" did not move its arm"));
            for(double progress:{0.2,0.4,0.55,0.75}) {
                character->setProperty("actionProgress",progress);
                QVERIFY(save(kind+QString("-action-%1").arg(qRound(progress*100))));
            }
            character->setProperty("held",true);
            QTRY_COMPARE(character->property("emotion").toString(),QString("surprised"));
            QTRY_VERIFY(character->property("surprise").toReal()>0.9);QVERIFY(save(kind+"-surprised"));
            character->setProperty("held",false);QTest::qWait(250);
            QTRY_COMPARE(character->property("emotion").toString(),QString("happy"));QVERIFY(save(kind+"-greeting"));
            character->setProperty("motion",false);QTest::qWait(60);
            QCOMPARE(character->property("emotion").toString(),QString("calm"));
            const auto paused=window.grabWindow();QTest::qWait(280);const auto later=window.grabWindow();
            if(later!=paused) { paused.save("screenshots/pets-expression/paused-before.png");later.save("screenshots/pets-expression/paused-after.png");
                qDebug()<<"Paused properties"<<character->property("joy")<<character->property("breath")<<character->property("smile")<<character->property("headTilt"); }
            QCOMPARE(later,paused);
        }
        character->setProperty("motion",true);character->setProperty("idleSeconds",60);
        QTRY_COMPARE(character->property("emotion").toString(),QString("sleepy"));QVERIFY(save("scott-sleepy"));
        character->setProperty("attention",true);QTRY_COMPARE(character->property("emotion").toString(),QString("curious"));
        QCOMPARE(warnings.count(),0);
        item->setParentItem(nullptr);
    }
    void scottReferenceGesturesAndScale() {
        const QString captures=qEnvironmentVariable("SCOTT_PET_CAPTURE_DIR");
        if(!captures.isEmpty())QVERIFY(QDir().mkpath(captures));
        QQmlEngine engine;QSignalSpy warnings(&engine,&QQmlEngine::warnings);
        QQmlComponent component(&engine,QUrl::fromLocalFile(QStringLiteral(SCOTT_PET_QML_DIR "/PetCharacter.qml")));
        std::unique_ptr<QObject> character(component.create());QVERIFY2(character,qPrintable(component.errorString()));
        auto *item=qobject_cast<QQuickItem *>(character.get());QVERIFY(item);
        QQuickWindow window;window.setColor(Qt::transparent);window.resize(280,260);
        item->setParentItem(window.contentItem());item->setSize(QSizeF(280,260));
        character->setProperty("interactive",false);character->setProperty("attention",false);
        window.show();QVERIFY(QTest::qWaitForWindowExposed(&window));
        const auto save=[&](const QString &name){return captures.isEmpty()||window.grabWindow().save(captures+"/"+name+".png");};
        auto *animation=character->findChild<QObject *>("petGreeting");QVERIFY(animation);
        auto *arm=character->findChild<QQuickItem *>("scottRightArm");QVERIFY(arm);
        auto *left=character->findChild<QQuickItem *>("scottLeftArm");QVERIFY(left);
        QCOMPARE(arm->property("upperLength").toReal()+arm->property("lowerLength").toReal(),35.0);
        QCOMPARE(left->property("upperLength").toReal()+left->property("lowerLength").toReal(),35.0);
        auto *heart=character->findChild<QQuickItem *>("scottHeart");QVERIFY(heart);
        for(const QString gesture:{"wave","think","heart","stretch","wink","nod"}) {
            character->setProperty("motion",false);character->setProperty("motion",true);
            QVERIFY(QMetaObject::invokeMethod(character.get(),"playAction",Q_ARG(QVariant,gesture)));
            QVERIFY(QMetaObject::invokeMethod(animation,"pause"));
            QPointF previous,previousElbows[2];bool moved=false,expressed=false;
            for(int frame=0;frame<=50;frame++) {
                character->setProperty("greetingProgress",frame/50.0);
                QTest::qWait(captures.isEmpty()?5:35);
                const QPointF hand(arm->property("handX").toReal(),arm->property("handY").toReal());
                if(frame){QVERIFY2(QLineF(previous,hand).length()<16,qPrintable(gesture+" hand jumped"));moved|=QLineF(previous,hand).length()>0.1;}
                previous=hand;
                int armIndex=0;
                for(auto *limb:{left,arm}) {
                    const qreal reach=limb->property("upperLength").toReal()+limb->property("lowerLength").toReal();
                    const QPointF wrist(limb->property("handX").toReal(),limb->property("handY").toReal());
                    const QPointF elbow(limb->property("elbowX").toReal(),limb->property("elbowY").toReal());
                    const qreal requested=std::hypot(limb->property("targetX").toReal(),limb->property("targetY").toReal());
                    QVERIFY2(requested<=reach-0.5,qPrintable(gesture+" target is outside the shorter arm's reach"));
                    QVERIFY2(QLineF(QPointF(),wrist).length()>=reach*0.6,qPrintable(gesture+" folds the elbow too tightly"));
                    if(frame)QVERIFY2(QLineF(previousElbows[armIndex],elbow).length()<8,qPrintable(gesture+" elbow jumped"));
                    previousElbows[armIndex++]=elbow;
                }
                QVERIFY(save(gesture+QString("-%1").arg(frame,2,10,QChar('0'))));
                if(gesture=="wink")expressed|=character->property("wink").toReal()>0.9;
                if(gesture=="nod")expressed|=qAbs(character->property("nod").toReal())>0.8;
                if(frame==25){
                    if(gesture=="wave"){
                        QVERIFY2(arm->property("elbowX").toReal()>10,"Raised arm must keep the elbow outside the shoulder");
                        QVERIFY2(arm->property("elbowY").toReal()>-10,"Wave must bend at the elbow rather than tuck the upper arm under the helmet");
                        QVERIFY(arm->property("handY").toReal()<arm->property("elbowY").toReal());
                    }
                    if(gesture=="heart"){QVERIFY(heart->opacity()>0.95);QCOMPARE(character->property("emotion").toString(),QString("happy"));}
                    if(gesture=="think"){QVERIFY(character->property("ponder").toReal()>0.8);QVERIFY(character->findChild<QQuickItem *>("scottQuestion")->opacity()>0.8);}
                }
            }
            if(gesture=="wink"||gesture=="nod")QVERIFY2(expressed,qPrintable(gesture+" has no facial or head movement"));
            else QVERIFY2(moved,qPrintable(gesture+" has no hand movement"));
            character->setProperty("motion",false);QTest::qWait(50);
            const auto paused=window.grabWindow();QTest::qWait(80);QCOMPARE(window.grabWindow(),paused);
        }
        character->setProperty("motion",true);character->setProperty("thinking",true);
        QTRY_VERIFY(character->property("ponder").toReal()>0.95);
        character->setProperty("thinking",false);QTRY_VERIFY(character->property("ponder").toReal()<0.05);
        for(int size:{50,100,200}) {
            character->setProperty("motion",false);window.resize(280*size/100,260*size/100);item->setSize(window.size());QTest::qWait(45);
            const auto frame=window.grabWindow().convertToFormat(QImage::Format_ARGB32);
            QVERIFY(!frame.isNull());int pixels=0;
            for(int y=0;y<frame.height();y++)for(int x=0;x<frame.width();x++) {
                if(qAlpha(frame.pixel(x,y))<32)continue;
                pixels++;QVERIFY2(x>0&&y>0&&x<frame.width()-1&&y<frame.height()-1,"Scott is clipped by its window");
            }
            QVERIFY(pixels>frame.width()*frame.height()/5);
            QVERIFY(save(QString("size-%1").arg(size)));
        }
        if(!captures.isEmpty()) {
            window.resize(560,520);item->setSize(window.size());
            for(const QString color:{"blue","black","white","green"}){
                character->setProperty("variant",color);QTest::qWait(60);QVERIFY(save(color));
            }
            character->setProperty("variant","blue");character->setProperty("motion",true);
            character->setProperty("thinking",true);QTest::qWait(450);QVERIFY(save("thinking"));
            character->setProperty("thinking",false);QTest::qWait(450);
            character->setProperty("idleSeconds",60);QTest::qWait(650);QVERIFY(save("sleepy"));
            character->setProperty("held",true);QTest::qWait(400);QVERIFY(save("surprised"));
            character->setProperty("motion",false);character->setProperty("held",false);
            character->setProperty("motion",true);QVERIFY(QMetaObject::invokeMethod(character.get(),"playAction",Q_ARG(QVariant,QString("laptop"))));
            QTest::qWait(2700);QVERIFY(save("laptop"));
        }
        // A backend reply can start while the pet is waving. The thinking
        // blend must not switch sides as the wave passes the opposite angle.
        character->setProperty("motion",false);character->setProperty("kind","scott");
        character->setProperty("variant","blue");character->setProperty("motion",true);
        QVERIFY(QMetaObject::invokeMethod(character.get(),"playAction",Q_ARG(QVariant,QString("wave"))));
        QVERIFY(QMetaObject::invokeMethod(animation,"pause"));
        character->setProperty("ponderPose",0.5);QTest::qWait(300);
        QPointF priorHand,priorElbow;
        for(int frame=0;frame<=50;frame++) {
            character->setProperty("greetingProgress",frame/50.0);QTest::qWait(5);
            const QPointF hand(arm->property("handX").toReal(),arm->property("handY").toReal());
            const QPointF elbow(arm->property("elbowX").toReal(),arm->property("elbowY").toReal());
            if(frame){QVERIFY2(QLineF(priorHand,hand).length()<8,"Thinking and greeting cause a hand flip");QVERIFY2(QLineF(priorElbow,elbow).length()<8,"Thinking and greeting cause an elbow flip");}
            priorHand=hand;priorElbow=elbow;
        }
        QCOMPARE(warnings.count(),0);item->setParentItem(nullptr);
    }
    void deterministicClicksAndNoIdleActions() {
        QQmlEngine engine;QSignalSpy warnings(&engine,&QQmlEngine::warnings);
        QQmlComponent component(&engine,QUrl::fromLocalFile(QStringLiteral(SCOTT_PET_QML_DIR "/PetCharacter.qml")));
        std::unique_ptr<QObject> character(component.create());QVERIFY2(character,qPrintable(component.errorString()));
        auto *item=qobject_cast<QQuickItem *>(character.get());QQuickWindow window;window.resize(280,260);
        item->setParentItem(window.contentItem());item->setSize(window.size());window.show();QVERIFY(QTest::qWaitForWindowExposed(&window));
        character->setProperty("interactive",false);character->setProperty("attention",false);character->setProperty("demo",true);
        auto *greeting=character->findChild<QObject *>("petGreeting");QVERIFY(greeting);
        // Covers the former 12.4-second desktop demo trigger and idle stretch.
        QTest::qWait(14500);QVERIFY(!character->property("acting").toBool());QVERIFY(!greeting->property("running").toBool());
        QCOMPARE(character->property("actionIndex").toInt(),0);QVERIFY(character->property("idleSeconds").toInt()>=13);
        character->setProperty("attention",true);QTest::qWait(200);QVERIFY(!greeting->property("running").toBool());
        for(const QString expected:{"wave","wink","heart","nod","wave"}){
            QVERIFY(QMetaObject::invokeMethod(character.get(),"interact"));QCOMPARE(character->property("gesture").toString(),expected);
            QVERIFY(!character->property("acting").toBool());QVERIFY(QMetaObject::invokeMethod(greeting,"complete"));
        }
        character->setProperty("held",true);QVERIFY(QMetaObject::invokeMethod(character.get(),"applicationOpened"));QVERIFY(character->property("pendingApplication").toBool());
        character->setProperty("held",false);QTRY_VERIFY(character->property("acting").toBool());
        character->setProperty("actionProgress",0.4);QVERIFY(QMetaObject::invokeMethod(character.get(),"applicationOpened"));
        QVERIFY(!character->property("pendingApplication").toBool());QVERIFY(character->property("actionProgress").toReal()>=0.39);
        character->setProperty("motion",false);QVERIFY(QMetaObject::invokeMethod(character.get(),"applicationOpened"));
        QVERIFY(!character->property("pendingApplication").toBool());QVERIFY(!character->property("acting").toBool());
        QCOMPARE(warnings.count(),0);item->setParentItem(nullptr);
    }
    void activityMailboxAndSingleDoubleClick() {
        QTemporaryDir directory;const auto path=directory.path()+"/activity.json";
        auto write=[&](QString id,qint64 timestamp,QString event="application_opened"){
            QSaveFile file(path);if(!file.open(QIODevice::WriteOnly))return false;
            file.write(QJsonDocument(QJsonObject{{"version",1},{"event",event},{"id",id},{"created_ms",double(timestamp)}}).toJson());return file.commit();
        };
        QVERIFY(write(QString(32,'a'),QDateTime::currentMSecsSinceEpoch()));
        DesktopPetService service(directory.path(),false);QVERIFY(service.start());QSignalSpy events(&service,&DesktopPetService::applicationOpened);
        QQmlApplicationEngine engine;QSignalSpy warnings(&engine,&QQmlEngine::warnings);engine.rootContext()->setContextProperty("petService",&service);
        engine.load(QUrl::fromLocalFile(QStringLiteral(SCOTT_PET_QML_DIR "/DesktopPetWindow.qml")));QVERIFY(!engine.rootObjects().isEmpty());
        auto *window=qobject_cast<QQuickWindow *>(engine.rootObjects().first());QVERIFY(QTest::qWaitForWindowExposed(window));
        auto *character=window->findChild<QObject *>("desktopPetCharacter");QVERIFY(character);
        QTest::qWait(120);QCOMPARE(events.count(),0);QVERIFY(!character->property("acting").toBool());
        QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,QPoint(140,120));
        QTRY_COMPARE(character->property("actionIndex").toInt(),1);QCOMPARE(character->property("gesture").toString(),QString("wave"));
        auto *greeting=character->findChild<QObject *>("petGreeting");QVERIFY(QMetaObject::invokeMethod(greeting,"complete"));
        QTest::mouseDClick(window,Qt::LeftButton,Qt::NoModifier,QPoint(140,120));
        QTest::qWait(QGuiApplication::styleHints()->mouseDoubleClickInterval()+100);
        QCOMPARE(character->property("actionIndex").toInt(),1);QCOMPARE(character->property("gesture").toString(),QString("heart"));
        QVERIFY(write(QString(32,'b'),QDateTime::currentMSecsSinceEpoch()));QTRY_COMPARE(events.count(),1);
        QVERIFY(character->property("pendingApplication").toBool());QVERIFY(QMetaObject::invokeMethod(greeting,"complete"));
        QTRY_VERIFY(character->property("acting").toBool());
        QVERIFY(write(QString(32,'b'),QDateTime::currentMSecsSinceEpoch()));QTest::qWait(150);QCOMPARE(events.count(),1);
        QVERIFY(write(QString(32,'c'),QDateTime::currentMSecsSinceEpoch()-11000));QTest::qWait(150);QCOMPARE(events.count(),1);
        QVERIFY(write(QString(32,'d'),QDateTime::currentMSecsSinceEpoch(),"unknown"));QTest::qWait(150);QCOMPARE(events.count(),1);
        service.toggleMotion();QVERIFY(write(QString(32,'e'),QDateTime::currentMSecsSinceEpoch()));QTest::qWait(150);QCOMPARE(events.count(),1);
        service.toggleMotion();QTest::qWait(150);QCOMPARE(events.count(),1);QVERIFY(!character->property("acting").toBool());
        QVERIFY(write(QString(32,'f'),QDateTime::currentMSecsSinceEpoch()));QTRY_COMPARE(events.count(),2);QTRY_VERIFY(character->property("acting").toBool());
        QCOMPARE(warnings.count(),0);
    }
    void desktopActivityBaselineAndPause() {
        std::atomic<int> phase{0},calls{0};
        DesktopActivity activity(nullptr,[&]{calls++;const int state=phase.load();return state==0?DesktopActivity::Snapshot{1}:state==1?DesktopActivity::Snapshot{1,2}:state==2?DesktopActivity::Snapshot{1,2,3}:DesktopActivity::Snapshot{90};},30);
        QSignalSpy opened(&activity,&DesktopActivity::applicationOpened);activity.setEnabled(true);QTRY_VERIFY(activity.initialized());QCOMPARE(opened.count(),0);
        phase=1;QTRY_COMPARE(opened.count(),1);phase=2;const int count=calls;QTRY_VERIFY(calls>count+2);QCOMPARE(opened.count(),1);
        activity.setEnabled(false);phase=3;activity.setEnabled(true);QTRY_VERIFY(activity.initialized());QCOMPARE(opened.count(),1);
        phase=0;QTRY_COMPARE(opened.count(),2);
    }
    void manualApplicationWindowIsDetected() {
        QTemporaryDir directory;DesktopPetService service(directory.path());QVERIFY(service.start());
        QQmlApplicationEngine engine;engine.rootContext()->setContextProperty("petService",&service);
        engine.load(QUrl::fromLocalFile(QStringLiteral(SCOTT_PET_QML_DIR "/DesktopPetWindow.qml")));QVERIFY(!engine.rootObjects().isEmpty());
        auto *window=qobject_cast<QQuickWindow *>(engine.rootObjects().first());QVERIFY(QTest::qWaitForWindowExposed(window));
        auto *activity=service.findChild<DesktopActivity *>();QVERIFY(activity);
        if(!activity->supported())QSKIP("Desktop compositor does not expose other application windows");
        QSignalSpy opened(&service,&DesktopPetService::applicationOpened);QTRY_VERIFY(activity->initialized());
        auto *character=window->findChild<QObject *>("desktopPetCharacter");QVERIFY(character);
        QVERIFY(!character->property("acting").toBool());const auto proof=directory.path()+"/visible.json";
        QProcess application;backgroundProcess(application);application.setProgram(QCoreApplication::applicationFilePath());application.setArguments({"--fixture-application-window",proof});application.start();
        QVERIFY(application.waitForStarted(3000));QTRY_VERIFY(QFileInfo::exists(proof));
        QFile visible(proof);QVERIFY(visible.open(QIODevice::ReadOnly));const auto state=QJsonDocument::fromJson(visible.readAll()).object();
        QVERIFY2(state["visible"].toBool(),qPrintable(QString::fromUtf8(QJsonDocument(state).toJson())));
        QTRY_VERIFY_WITH_TIMEOUT(opened.count()>=1,5000);
        QTRY_VERIFY(character->property("acting").toBool());
        QVERIFY(application.waitForFinished(6000));QCOMPARE(application.exitCode(),0);
    }
    void miniChatInputFailureAndReopen() {
        QTcpServer server;QVERIFY(server.listen(QHostAddress::LocalHost,0));
        int requests=0,uploads=0;bool fail=true;QByteArray body;const QString id(32,'a');
        QJsonArray rows;
        auto chat=[&]{return QJsonObject{{"id",id},{"title","Mini chat"},{"messages",rows}};};
        connect(&server,&QTcpServer::newConnection,this,[&]{
            auto *socket=server.nextPendingConnection();auto bytes=std::make_shared<QByteArray>();
            connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
            connect(socket,&QTcpSocket::readyRead,socket,[&,socket,bytes]{
                *bytes+=socket->readAll();const int split=bytes->indexOf("\r\n\r\n");if(split<0)return;
                int length=0;for(const auto &line:bytes->left(split).split('\n'))if(line.toLower().startsWith("content-length:"))length=line.mid(15).trimmed().toInt();
                if(bytes->size()<split+4+length)return;
                requests++;int code=200;const auto path=bytes->split(' ').value(1),method=bytes->split(' ').value(0);QJsonObject response;
                if(path=="/health")response={{"status","online"}};
                else if(path=="/chats"&&method=="POST")response={{"success",true},{"chat",chat()}};
                else if(path.endsWith("/messages")&&method=="POST") {
                    uploads++;body=bytes->mid(split+4,length);
                    if(fail){code=503;response={{"detail","Fixture unavailable"}};}
                    else {rows=QJsonArray{QJsonObject{{"role","user"},{"text","hello"},{"attachments",QJsonArray{}}},QJsonObject{{"role","assistant"},{"text","Fixture response"},{"attachments",QJsonArray{}}}};response={{"success",true},{"chat",chat()}};}
                } else if(path=="/chats")response={{"success",true},{"chats",QJsonArray{QJsonObject{{"id",id},{"title","Mini chat"}}}}};
                else if(path=="/browser")response={{"state","idle"}};
                const auto payload=QJsonDocument(response).toJson(QJsonDocument::Compact);
                socket->write("HTTP/1.1 "+QByteArray::number(code)+" Result\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "+QByteArray::number(payload.size())+"\r\n\r\n"+payload);socket->disconnectFromHost();bytes->clear();
            });
        });
        QTemporaryDir directory;DesktopPetService service(directory.path());
        PetChatController controller(directory.path(),QUrl(QString("http://127.0.0.1:%1").arg(server.serverPort())));
        QQmlApplicationEngine engine;QSignalSpy warnings(&engine,&QQmlEngine::warnings);
        engine.rootContext()->setContextProperty("petService",&service);engine.rootContext()->setContextProperty("petChat",&controller);
        engine.load(QUrl::fromLocalFile(QStringLiteral(SCOTT_PET_QML_DIR "/DesktopPetWindow.qml")));
        QVERIFY(!engine.rootObjects().isEmpty());auto *window=qobject_cast<QQuickWindow *>(engine.rootObjects().first());QVERIFY(window);
        QVERIFY(QTest::qWaitForWindowExposed(window));QTest::qWait(100);QCOMPARE(requests,0);
        auto *menu=window->findChild<QObject *>("petContextMenu");auto *entry=window->findChild<QObject *>("petOpenChat");
        auto *popup=window->findChild<QObject *>("petMiniChat");auto *input=window->findChild<QQuickItem *>("petChatInput");QVERIFY(menu);QVERIFY(entry);QVERIFY(popup);QVERIFY(input);
        QTest::mouseClick(window,Qt::RightButton,Qt::NoModifier,QPoint(140,120));QTRY_VERIFY(menu->property("visible").toBool());QCOMPARE(menu->property("count").toInt(),2);
        QVERIFY(QMetaObject::invokeMethod(entry,"triggered"));QMetaObject::invokeMethod(menu,"close");
        QTRY_VERIFY(popup->property("opened").toBool());QTRY_VERIFY(controller.backend()->online());QTRY_VERIFY(!controller.busy());
        QVERIFY(!controller.backend()->ownsBackend());QTRY_VERIFY(input->hasActiveFocus());
        auto *chatWindow=input->window();QVERIFY(chatWindow);QVERIFY(chatWindow!=window);
        QCOMPARE(chatWindow->transientParent(),window);
        QSignalSpy lastWindowClosed(qGuiApp,&QGuiApplication::lastWindowClosed);
        auto *messageView=window->findChild<QQuickItem *>("petChatMessages");QVERIFY(messageView);
        QVERIFY2(messageView->height()>=200,qPrintable(QString("message height=%1 popup=%2 window=%3").arg(messageView->height()).arg(popup->property("height").toReal()).arg(chatWindow->height())));
        for(const auto key:{Qt::Key_H,Qt::Key_E,Qt::Key_L,Qt::Key_L,Qt::Key_O})QTest::keyClick(chatWindow,key);
        QCOMPARE(input->property("text").toString(),QString("hello"));QTest::keyClick(chatWindow,Qt::Key_Return);
        QTRY_COMPARE(uploads,1);QTRY_VERIFY(!controller.busy());QVERIFY(!controller.error().isEmpty());
        QCOMPARE(input->property("text").toString(),QString("hello"));QTest::qWait(300);QCOMPARE(uploads,1);
        QVERIFY(body.contains("name=\"mode\"\r\n\r\nchat"));QVERIFY(body.contains("hello"));
        QDir().mkpath("screenshots/pet-mini-chat");QVERIFY(chatWindow->grabWindow().save("screenshots/pet-mini-chat/failure-draft.png"));
        fail=false;input->forceActiveFocus();QTest::keyClick(chatWindow,Qt::Key_Return);
        QTRY_COMPARE(uploads,2);QTRY_VERIFY(!controller.busy());QTRY_COMPARE(controller.backend()->messages().size(),2);
        QTRY_COMPARE(input->property("text").toString(),QString());QTest::qWait(250);
        QVERIFY(messageView->height()>=200);QCOMPARE(chatWindow->height(),qRound(popup->property("height").toReal()));
        QVERIFY(chatWindow->grabWindow().save("screenshots/pet-mini-chat/response.png"));
        QMetaObject::invokeMethod(popup,"close");QTRY_VERIFY(!popup->property("visible").toBool());QVERIFY(window->isVisible());
        QCOMPARE(lastWindowClosed.count(),0);
        QMetaObject::invokeMethod(entry,"triggered");QTRY_VERIFY(popup->property("opened").toBool());QCOMPARE(controller.backend()->messages().size(),2);QCOMPARE(uploads,2);
        if(service.canReposition())QVERIFY(window->screen()->availableGeometry().contains(chatWindow->geometry()));
        QCOMPARE(warnings.count(),0);
    }
    void coldMiniChatOwnsOnlyItsBackendAndSessionFollowsPet() {
        QTemporaryDir dir;QVERIFY(dir.isValid());
        QTcpServer reservation;QVERIFY(reservation.listen(QHostAddress::LocalHost,0));const int port=reservation.serverPort();reservation.close();
        QFile source(dir.path()+"/main.py");QVERIFY(source.open(QIODevice::WriteOnly));
        source.write(QJsonDocument(QJsonObject{{"fixture",true},{"port",port}}).toJson());source.close();
        QFile context(dir.path()+"/backend.json");QVERIFY(context.open(QIODevice::WriteOnly));
        context.write(QJsonDocument(QJsonObject{{"directory",dir.path()},{"python",QCoreApplication::applicationFilePath()}}).toJson());context.close();
        const QUrl base(QString("http://127.0.0.1:%1").arg(port));
        {
            PetChatController controller(dir.path(),base);QSignalSpy sent(&controller,&PetChatController::sent);
            QVERIFY(!controller.backend()->ownsBackend());controller.send("hello");
            QTRY_VERIFY_WITH_TIMEOUT(controller.backend()->ownsBackend(),5000);
            QTRY_COMPARE_WITH_TIMEOUT(sent.count(),1,12000);QVERIFY(controller.error().isEmpty());
            QFile received(dir.path()+"/main.py.received");QVERIFY(received.open(QIODevice::ReadOnly));QVERIFY(received.readAll().contains("hello"));
            auto service=std::make_unique<DesktopPetService>(dir.path());QVERIFY(service->start());
            QQuickWindow window;window.resize(280,260);service->attach(&window);
            BackendClient observer(base);bool lost=false;
            PetBackendSession session(observer,dir.path(),[&]{lost=true;},60);QVERIFY(session.start());
            QTRY_VERIFY(observer.online());QTest::qWait(320);QVERIFY(!lost);QVERIFY(!observer.ownsBackend());
            service.reset();QTRY_VERIFY_WITH_TIMEOUT(lost,1500);
            // The session lost its pet, but it did not terminate another owner's backend.
            controller.backend()->refresh();QTRY_VERIFY(controller.backend()->online());
        }
        QTcpSocket gone;gone.connectToHost(QHostAddress::LocalHost,port);QVERIFY(!gone.waitForConnected(500));
    }
    void survivesParentAndOriginalExecutableReplacement() {
        QTemporaryDir dir;QVERIFY(dir.isValid());
        const auto profile=dir.path()+"/profile";
        const auto cleanup=qScopeGuard([&]{command(profile,"quit");});
#ifdef Q_OS_WIN
        const QString name="ScottAIQt.exe",cached="ScottAIPet.exe";
#else
        const QString name="ScottAIQt",cached="ScottAIPet";
#endif
        QVERIFY(QDir().mkpath(dir.path()+"/source"));
        const auto source=dir.path()+"/source/"+name;
        QVERIFY(QFile::copy(QCoreApplication::applicationDirPath()+"/"+name,source));
        QProcess parent;backgroundProcess(parent);parent.setProgram(QCoreApplication::applicationFilePath());
        parent.setArguments({"--fixture-parent",dir.path(),source});parent.start();
        QVERIFY(parent.waitForStarted(3000));QVERIFY2(parent.waitForFinished(25000),qPrintable(QString::fromUtf8(parent.readAllStandardError())));
        QCOMPARE(parent.exitCode(),0);QVERIFY(QFileInfo::exists(dir.path()+"/parent-ready"));
        const auto first=command(profile,"state");QVERIFY(first["ready"].toBool());QVERIFY(!first["pid"].toString().isEmpty());
        QVERIFY(QFile::rename(source,dir.path()+"/source/old-launcher"));
        auto folders=QDir(dir.path()+"/cache").entryList(QDir::Dirs|QDir::NoDotAndDotDot);QCOMPARE(folders.size(),1);
        const auto executable=dir.path()+"/cache/"+folders.first()+"/launcher/"+cached;
        QProcess duplicate;backgroundProcess(duplicate);duplicate.setProgram(executable);duplicate.setArguments({"--desktop-pet","--pet-state",profile});duplicate.start();
        QVERIFY(duplicate.waitForFinished(8000));QCOMPARE(duplicate.exitCode(),0);
        QCOMPARE(command(profile,"state")["pid"].toString(),first["pid"].toString());
        PetController observer(false,profile,dir.path()+"/cache",source);
        QTRY_VERIFY_WITH_TIMEOUT(observer.running(),5000);QCOMPARE(observer.kind(),QString("scott"));QVERIFY(observer.enabled());
        observer.selectVariant("black");
        QTRY_COMPARE_WITH_TIMEOUT(command(profile,"state")["variant"].toString(),QString("black"),5000);
        for(int size:{55,90,160,200,165})observer.setSizePercent(size);
        QTRY_COMPARE_WITH_TIMEOUT(command(profile,"state")["sizePercent"].toInt(),165,5000);
        QTRY_COMPARE_WITH_TIMEOUT(observer.sizePercent(),165,5000);
        const auto legacy=request(profile,{{"op","configure"},{"kind","scott"},{"variant","blue"},{"motion",true}});
        QCOMPARE(legacy["sizePercent"].toInt(),165);
        const auto malformed=request(profile,{{"op","configure"},{"kind","scott"},{"variant","green"},{"motion",true},{"sizePercent",900}});
        QCOMPARE(malformed["kind"].toString(),QString("scott"));QCOMPARE(malformed["sizePercent"].toInt(),165);
        observer.setEnabled(false);QTRY_VERIFY_WITH_TIMEOUT(!observer.running(),5000);
        QSettings settings(profile+"/settings.ini",QSettings::IniFormat);QCOMPARE(settings.value("enabled").toBool(),false);
        QProcess restarted;backgroundProcess(restarted);restarted.setProgram(executable);restarted.setArguments({"--desktop-pet","--pet-state",profile});restarted.start();
        QVERIFY(restarted.waitForStarted(3000));QTRY_VERIFY_WITH_TIMEOUT(command(profile,"state")["ready"].toBool(),5000);
        QCOMPARE(command(profile,"state")["sizePercent"].toInt(),165);
        command(profile,"quit");QVERIFY(restarted.waitForFinished(5000));QCOMPARE(restarted.exitCode(),0);
    }
};
int main(int argc,char **argv) {
    qputenv("QT_QUICK_CONTROLS_STYLE","Basic");
    QApplication app(argc,argv);
    app.setQuitOnLastWindowClosed(false);
    if(app.arguments().value(1)=="--fixture-state-path"){
        QFile file(app.arguments().value(2));if(!file.open(QIODevice::WriteOnly))return 1;
        file.write(QJsonDocument(QJsonObject{{"root",PetController::defaultStateRoot()}}).toJson());return 0;
    }
    if(app.arguments().value(1)=="--fixture-application-window"){
        QQuickWindow window;window.setTitle("Scott application activity fixture");window.resize(240,160);window.show();
        // CREATE_NO_WINDOW suppresses consoles; STARTF_USESHOWWINDOW/SW_HIDE
        // also hides the first native show. Re-show the deliberate GUI fixture.
        QTimer::singleShot(100,&window,&QWindow::hide);QTimer::singleShot(200,&window,&QWindow::show);
        QTimer::singleShot(350,&window,[&]{
            QJsonObject state{{"visible",window.isVisible()},{"flags",double(window.flags().toInt())}};
#ifdef Q_OS_WIN
            const auto handle=reinterpret_cast<HWND>(window.winId());DWORD cloaked=0;DwmGetWindowAttribute(handle,DWMWA_CLOAKED,&cloaked,sizeof(cloaked));
            state["visible"]=bool(IsWindowVisible(handle));state["cloaked"]=int(cloaked);state["owner"]=QString::number(quintptr(GetWindow(handle,GW_OWNER)));state["extended_style"]=double(GetWindowLongPtrW(handle,GWL_EXSTYLE));
#endif
            QFile proof(app.arguments().value(2));if(proof.open(QIODevice::WriteOnly))proof.write(QJsonDocument(state).toJson());
        });
        QTimer::singleShot(5500,&app,&QCoreApplication::quit);return app.exec();
    }
    if(app.arguments().value(1)=="-u")return fixtureBackend(app,app.arguments().value(2));
    if(app.arguments().value(1)=="--fixture-packaged")return packagedFixture(app.arguments());
    if(app.arguments().value(1)=="--fixture-parent") {
        const auto root=app.arguments().value(2);
        PetController pet(false,root+"/profile",root+"/cache",app.arguments().value(3));
        pet.selectPet("scott");pet.setEnabled(true);
        QTimer timer;timer.setInterval(80);
        QObject::connect(&timer,&QTimer::timeout,&app,[&]{
            if(!pet.error().isEmpty()){qWarning().noquote()<<pet.error();app.exit(3);}
            if(pet.running()){QFile proof(root+"/parent-ready");if(!proof.open(QIODevice::WriteOnly)){app.exit(4);return;}proof.write("independent service ready\n");proof.close();app.exit(0);}
        });timer.start();QTimer::singleShot(40000,&app,[]{qApp->exit(5);});
        return app.exec();
    }
    PetTests tests;return QTest::qExec(&tests,argc,argv);
}
#include "PetTests.moc"
