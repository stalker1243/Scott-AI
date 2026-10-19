#include "PetController.h"
#include "DesktopPetService.h"
#include "PetChatController.h"
#include "ProcessSupport.h"
#include <QApplication>
#include <QCryptographicHash>
#include <QDirIterator>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLibraryInfo>
#include <QLocalServer>
#include <QLockFile>
#include <QQmlApplicationEngine>
#include "AppLanguage.h"
#include <QQmlContext>
#include <QQuickWindow>
#include <QRegularExpression>
#include <QPointer>
#include <QSaveFile>
#include <QScreen>
#include <QSettings>
#include <QStandardPaths>
#include <QStorageInfo>
#include <QTemporaryDir>
#include <QtConcurrent/QtConcurrentRun>
#include <memory>

namespace {
QString digest(const QString &path) {
    QFile file(path);if(!file.open(QIODevice::ReadOnly))return {};
    QCryptographicHash hash(QCryptographicHash::Sha256);
    return hash.addData(&file)?QString::fromLatin1(hash.result().toHex()):QString();
}
bool privateDirectory(const QString &path) {
    if(QFileInfo(path).isSymLink())return false;
    const bool exists=QDir(path).exists();
    return QDir().mkpath(path) && (exists || QFile::setPermissions(path,QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner));
}
bool tree(const QString &source,const QString &target) {
    if(!QDir(source).exists() || !privateDirectory(target))return false;
    const auto canonical=QFileInfo(source).canonicalFilePath()+"/";
    QDirIterator it(source,QDir::Files|QDir::NoDotAndDotDot,QDirIterator::Subdirectories);
    while(it.hasNext()) {
        const auto file=it.next();
        if(!QFileInfo(file).canonicalFilePath().startsWith(canonical))return false;
        const auto destination=target+"/"+QDir(source).relativeFilePath(file);
        if(!QDir().mkpath(QFileInfo(destination).absolutePath()) || !QFile::copy(file,destination))return false;
    }
    return true;
}
QVariantMap prepareRuntime(const QString &source,const QString &cache) {
    const auto fail=[](const QString &error){return QVariantMap{{"error",error}};};
    if(!privateDirectory(cache))return fail(QStringLiteral("Не удалось создать кеш питомца."));
    QLockFile lock(cache+"/prepare.lock");if(!lock.tryLock(5000))return fail(QStringLiteral("Подготовка питомца уже выполняется. Повторите позже."));
    const auto executableHash=digest(source);
    if(executableHash.isEmpty())return fail(QStringLiteral("Не найден файл лаунчера для питомца."));
    const auto launcher=QFileInfo(source).absolutePath();
#ifdef Q_OS_WIN
    const bool deployed=QFileInfo::exists(launcher+"/Qt6Core.dll");
    const auto core=deployed?launcher+"/Qt6Core.dll":QLibraryInfo::path(QLibraryInfo::BinariesPath)+"/Qt6Core.dll";
    const QString name="ScottAIPet.exe";
#else
    const auto root=QDir(launcher).absoluteFilePath("..");
    const bool deployed=QDir(root+"/lib").exists() && QDir(root+"/qml").exists();
    const auto core=deployed?root+"/lib/libQt6Core.so.6":QLibraryInfo::path(QLibraryInfo::LibrariesPath)+"/libQt6Core.so.6";
    const QString name="ScottAIPet";
#endif
    const auto coreHash=digest(core);
    if(coreHash.isEmpty())return fail(QStringLiteral("Не удалось проверить Qt для питомца."));
    const auto key=QString::fromLatin1(QCryptographicHash::hash((executableHash+coreHash).toUtf8(),QCryptographicHash::Sha256).toHex());
    const auto final=cache+"/"+key;
    const auto ready=[&](const QString &folder){
        QFile manifest(folder+"/runtime.json");
        if(!manifest.open(QIODevice::ReadOnly) || manifest.size()>1024*1024)return false;
        const auto value=QJsonDocument::fromJson(manifest.readAll()).object();
        if(value["source_sha256"].toString()!=executableHash || !value["files"].isObject())return false;
        const auto files=value["files"].toObject();if(files.isEmpty())return false;
        for(auto it=files.begin();it!=files.end();++it) {
            if(it.key().contains("..") || QDir::isAbsolutePath(it.key()) || QFileInfo(folder+"/"+it.key()).isSymLink() || digest(folder+"/"+it.key())!=it.value().toString())return false;
        }
        return digest(folder+"/launcher/"+name)==executableHash;
    };
    if(ready(final))return {{"executable",final+"/launcher/"+name},{"deployed",deployed},{"root",final}};
    if(QFileInfo::exists(final))return fail(QStringLiteral("Кеш питомца повреждён. Файлы сохранены; используйте другую папку кеша или восстановите установку."));
    if(QStorageInfo(cache).bytesAvailable()<350*1024*1024)return fail(QStringLiteral("Для подготовки питомца нужно 350 МиБ свободного места в кеше."));
    QTemporaryDir stage(cache+"/pending-XXXXXX");
    if(!stage.isValid() || !privateDirectory(stage.path()+"/launcher") || !QFile::copy(source,stage.path()+"/launcher/"+name))return fail(QStringLiteral("Не удалось скопировать питомца."));
    bool copied=true;
    if(deployed) {
#ifdef Q_OS_WIN
        for(const auto &file:QDir(launcher).entryList({"*.dll"},QDir::Files))copied=QFile::copy(launcher+"/"+file,stage.path()+"/launcher/"+file)&&copied;
        for(const auto &folder:{"platforms","imageformats","styles","iconengines","networkinformation","tls","qml"})
            if(QDir(launcher+"/"+folder).exists())copied=tree(launcher+"/"+folder,stage.path()+"/launcher/"+folder)&&copied;
        QFile conf(stage.path()+"/launcher/qt.conf");copied=conf.open(QIODevice::WriteOnly)&&copied;
        if(conf.isOpen())conf.write("[Paths]\nPrefix=.\nPlugins=.\nQmlImports=qml\n");
#else
        for(const auto &folder:{"lib","plugins","qml"})copied=tree(root+"/"+folder,stage.path()+"/"+folder)&&copied;
        copied=QFile::copy(launcher+"/qt.conf",stage.path()+"/launcher/qt.conf")&&copied;
#endif
    }
    if(!copied || digest(stage.path()+"/launcher/"+name)!=executableHash)return fail(QStringLiteral("Не удалось подготовить Qt для питомца. Проверьте место и права."));
    QJsonObject files;
    QDirIterator it(stage.path(),QDir::Files,QDirIterator::Subdirectories);
    while(it.hasNext()){const auto file=it.next();files[QDir(stage.path()).relativeFilePath(file)]=digest(file);}
    QSaveFile receipt(stage.path()+"/runtime.json");
    if(!receipt.open(QIODevice::WriteOnly))return fail(QStringLiteral("Не удалось сохранить сведения о питомце."));
    receipt.setPermissions(QFile::ReadOwner|QFile::WriteOwner);
    receipt.write(QJsonDocument(QJsonObject{{"source_sha256",executableHash},{"files",files}}).toJson());
    if(!receipt.commit() || !QDir().rename(stage.path(),final))return fail(QStringLiteral("Не удалось завершить подготовку питомца."));
    stage.setAutoRemove(false);
    return {{"executable",final+"/launcher/"+name},{"deployed",deployed},{"root",final}};
}
}

QString PetController::defaultStateRoot(){return QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation)+"/ScottAI/desktop-pet";}
bool PetController::canReposition()const{return !QGuiApplication::platformName().startsWith("wayland");}
QString PetController::serverName(const QString &root){return "scott-pet-"+QString::fromLatin1(QCryptographicHash::hash(QDir(root).absolutePath().toUtf8(),QCryptographicHash::Sha256).toHex().left(32));}
QStringList PetController::variants(const QString &kind) {
    if(kind=="scott")return {"blue","black","white","green"};
    return {};
}
PetController::PetController(bool preview,QString stateRoot,QString cacheRoot,QString executable,QObject *parent)
    :QObject(parent),m_preview(preview),m_stateRoot(stateRoot.isEmpty()?defaultStateRoot():QDir(stateRoot).absolutePath()),
     m_cacheRoot(cacheRoot.isEmpty()?QStandardPaths::writableLocation(QStandardPaths::GenericCacheLocation)+"/ScottAI/pet-runtimes":cacheRoot),
     m_executable(executable.isEmpty()?QCoreApplication::applicationFilePath():executable) {
    if(!preview)read();
    connect(&m_prepare,&QFutureWatcher<QVariantMap>::finished,this,&PetController::finishLaunch);
    m_poll.setInterval(1500);connect(&m_poll,&QTimer::timeout,this,&PetController::poll);
    m_startup.setSingleShot(true);m_startup.setInterval(12000);
    connect(&m_startup,&QTimer::timeout,this,[this]{
        if(m_enabled && !m_running) {
            m_error=QStringLiteral("Питомец не ответил при запуске. Выключите его и попробуйте снова; журнал находится в настройках desktop-pet/logs.");
            emit changed();
        }
    });
    if(!preview)m_poll.start();
}
PetController::~PetController(){if(!m_launchHandled){m_prepare.waitForFinished();finishLaunch();}}
void PetController::read(){QSettings s(m_stateRoot+"/settings.ini",QSettings::IniFormat);s.sync();m_kind=s.value("kind","scott").toString();if(variants(m_kind).isEmpty())m_kind="scott";m_variant=s.value("variant",variants(m_kind).first()).toString();if(!variants(m_kind).contains(m_variant))m_variant=variants(m_kind).first();m_enabled=s.value("enabled",false).toBool();m_motion=s.value("motion",true).toBool();m_sizePercent=qBound(50,s.value("sizePercent",100).toInt(),200);}
void PetController::save(){if(m_preview)return;if(!privateDirectory(m_stateRoot)){m_error=QStringLiteral("Не удалось сохранить настройки питомца.");return;}QSettings s(m_stateRoot+"/settings.ini",QSettings::IniFormat);s.setValue("kind",m_kind);s.setValue("variant",m_variant);s.setValue("enabled",m_enabled);s.setValue("motion",m_motion);s.setValue("sizePercent",m_sizePercent);s.sync();QFile::setPermissions(s.fileName(),QFile::ReadOwner|QFile::WriteOwner);if(s.status()!=QSettings::NoError)m_error=QStringLiteral("Не удалось сохранить настройки питомца.");}
void PetController::selectPet(const QString &kind){if(variants(kind).isEmpty() || kind==m_kind)return;++m_revision;m_kind=kind;m_variant=variants(kind).first();m_configPending=true;save();emit changed();poll();}
void PetController::selectVariant(const QString &variant){if(!variants(m_kind).contains(variant))return;++m_revision;m_variant=variant;m_configPending=true;save();emit changed();poll();}
void PetController::setMotion(bool value){++m_revision;m_motion=value;m_configPending=true;save();emit changed();poll();}
void PetController::setSizePercent(int value){value=qBound(50,value,200);if(value==m_sizePercent)return;++m_revision;m_sizePercent=value;m_configPending=true;save();emit changed();poll();}
void PetController::resetPosition(){m_recenterPending=true;poll();}
void PetController::interact(){m_playPending=true;poll();}
void PetController::finishRequest(QLocalSocket *socket,bool replied) {
    if(m_socket!=socket)return;
    m_socket=nullptr;
    socket->abort();socket->deleteLater();
    if(replied && (m_stopPending||m_configPending||m_recenterPending||m_playPending))
        QTimer::singleShot(0,this,&PetController::poll);
}
void PetController::poll() {
    if(m_preview || m_socket)return;
    auto *socket=new QLocalSocket(this);m_socket=socket;
    const quint64 revision=m_revision;
    const QString op=m_stopPending?"quit":m_configPending?"configure":m_recenterPending?"recenter":m_playPending?"play":"state";
    const QJsonObject request{{"op",op},{"kind",m_kind},{"variant",m_variant},{"motion",m_motion},{"sizePercent",m_sizePercent}};
    auto bytes=std::make_shared<QByteArray>();
    auto replied=std::make_shared<bool>(false);
    connect(socket,&QLocalSocket::connected,this,[this,socket,request,revision,op]{
        if(m_socket!=socket)return;
        if(m_revision==revision) {
            if(op=="quit")m_stopPending=false;
            else if(op=="configure")m_configPending=false;
            else if(op=="recenter")m_recenterPending=false;
            else if(op=="play")m_playPending=false;
        }
        socket->write(QJsonDocument(request).toJson(QJsonDocument::Compact)+'\n');
    });
    connect(socket,&QLocalSocket::readyRead,this,[this,socket,revision,bytes,replied]{
        if(m_socket!=socket || *replied)return;
        *bytes+=socket->readAll();
        if(bytes->size()>4096){finishRequest(socket,false);return;}
        if(!bytes->endsWith('\n'))return;
        const auto state=QJsonDocument::fromJson(*bytes).object();
        if(state["ready"].isBool()) {
            *replied=true;m_running=state["ready"].toBool();
            if(m_running)m_startup.stop();
            const auto *language=qobject_cast<AppLanguage *>(qApp->property("appLanguage").value<QObject *>());
            const bool needsLanguage=language&&language->language()!="ru"&&state["localization"].toInt()!=1;
            if(m_running && m_enabled && (needsLanguage || !state["miniChat"].toBool() || state["activityEvents"].toInt()!=1 || !state["scottOnly"].toBool()))m_error=QStringLiteral("Выключите и снова включите питомца, чтобы запустить обновлённого Скотта Младшего.");
            if(!m_busy && !m_configPending && !m_stopPending && revision==m_revision) {
                const auto kind=state["kind"].toString(),variant=state["variant"].toString();
                if(variants(kind).contains(variant)){m_kind=kind;m_variant=variant;}
                if(state["motion"].isBool())m_motion=state["motion"].toBool();
                if(state["sizePercent"].isDouble())m_sizePercent=qBound(50,state["sizePercent"].toInt(),200);
            }
            emit changed();
        }
        finishRequest(socket,*replied);
    });
    connect(socket,&QLocalSocket::errorOccurred,this,[this,socket,replied](QLocalSocket::LocalSocketError){
        if(m_socket!=socket)return;
        if(!*replied) {
            m_running=false;
            if(!m_busy&&!m_configPending&&!m_stopPending&&!m_startup.isActive())read();
            emit changed();
        }
        finishRequest(socket,*replied);
    });
    connect(socket,&QLocalSocket::disconnected,this,[this,socket,replied]{finishRequest(socket,*replied);});
    QTimer::singleShot(1000,socket,[this,socket]{
        if(m_socket!=socket)return;
        m_running=false;emit changed();finishRequest(socket,false);
    });
    socket->connectToServer(serverName(m_stateRoot));
}
void PetController::restore(){if(m_enabled)setEnabled(true);else poll();}
void PetController::configureChat(const QString &directory,const QString &python) {
    m_backendDirectory=directory;m_python=python.isEmpty()?QString():QFileInfo(python).absoluteFilePath();
    if(m_enabled&&!m_preview)saveChatContext();
}
void PetController::saveChatContext() {
    if(m_preview || m_backendDirectory.isEmpty() || !privateDirectory(m_stateRoot))return;
    const auto path=m_stateRoot+"/backend.json";
    if(QFileInfo(path).isSymLink())return;
    QSaveFile file(path);if(!file.open(QIODevice::WriteOnly))return;
    file.setPermissions(QFile::ReadOwner|QFile::WriteOwner);
    const QJsonObject context{{"directory",QFileInfo(m_backendDirectory).absoluteFilePath()},
                              {"python",m_python},{"appimage",qEnvironmentVariable("APPIMAGE")},
                              {"extract",qEnvironmentVariableIsSet("APPIMAGE_EXTRACT_AND_RUN")}};
    file.write(QJsonDocument(context).toJson(QJsonDocument::Compact));file.commit();
}
void PetController::setEnabled(bool enabled) {
    ++m_revision;m_enabled=enabled;m_error.clear();m_configPending=enabled;save();emit changed();
    if(m_preview){m_running=enabled;emit changed();return;}
    if(!m_error.isEmpty())return;
    if(enabled)saveChatContext();
    if(!enabled){m_startup.stop();m_stopPending=true;poll();return;}
    m_stopPending=false;
    if(m_running){poll();return;}
    if(m_busy)return;
    m_busy=true;m_launchHandled=false;emit changed();
    const auto exe=m_executable,cache=m_cacheRoot;
    m_prepare.setFuture(QtConcurrent::run([exe,cache]{return prepareRuntime(exe,cache);}));
}
void PetController::finishLaunch() {
    if(m_launchHandled)return;m_launchHandled=true;m_busy=false;
    const auto result=m_prepare.result();
    if(!result.value("error").toString().isEmpty()){m_error=result["error"].toString();emit changed();return;}
    if(!m_enabled){emit changed();return;}
    QProcess process;backgroundProcess(process);auto env=QProcessEnvironment::systemEnvironment();
    // Provider keys stay in memory for an on-demand backend; never serialize
    // them into backend.json, arguments, IPC or the runtime manifest.
    const QRegularExpression provider("^(GROQ|DEEPSEEK|OPENAI|ANTHROPIC|CLAUDE|OPENROUTER)_API_KEY(?:_[0-9]+)?$");
    for(const auto &key:env.keys())if(((key.endsWith("_API_KEY",Qt::CaseInsensitive)||key.endsWith("_TOKEN",Qt::CaseInsensitive))&&!provider.match(key).hasMatch())
        ||key.startsWith("AWS_")||key=="PYTHONHOME"||key=="PYTHONPATH"||key=="APPDIR"||key=="APPIMAGE"||key=="ARGV0"||key=="TARGET_APPIMAGE"||key=="APPIMAGE_EXTRACT_AND_RUN"||key.startsWith("QML_"))env.remove(key);
    const auto root=result["root"].toString();
    if(result["deployed"].toBool()) {
#ifndef Q_OS_WIN
        env.insert("LD_LIBRARY_PATH",root+"/lib");env.insert("QT_PLUGIN_PATH",root+"/plugins");env.insert("QML_IMPORT_PATH",root+"/qml");
#else
        env.remove("QT_PLUGIN_PATH");env.remove("QT_QPA_PLATFORM_PLUGIN_PATH");env.insert("QML_IMPORT_PATH",root+"/launcher/qml");
#endif
    } else {
        env.insert("QT_PLUGIN_PATH",QLibraryInfo::path(QLibraryInfo::PluginsPath));
        env.insert("QML_IMPORT_PATH",QLibraryInfo::path(QLibraryInfo::QmlImportsPath));
#ifdef Q_OS_WIN
        env.insert("PATH",QLibraryInfo::path(QLibraryInfo::BinariesPath)+";"+env.value("PATH"));
#else
        env.insert("LD_LIBRARY_PATH",QLibraryInfo::path(QLibraryInfo::LibrariesPath));
#endif
    }
    process.setProcessEnvironment(env);process.setProgram(result["executable"].toString());process.setArguments({"--desktop-pet","--pet-state",m_stateRoot});process.setWorkingDirectory(root);
    if(!process.startDetached())m_error=QStringLiteral("Не удалось открыть питомца.");
    else m_startup.start();
    emit changed();poll();
}

int runDesktopPet(QApplication &app,const QString &stateRoot) {
    app.setQuitOnLastWindowClosed(true);
    const auto root=stateRoot.isEmpty()?PetController::defaultStateRoot():QDir(stateRoot).absolutePath();
    if(!privateDirectory(root))return 51;
    DesktopPetService service(root);if(!service.start())return 0;
    PetChatController chat(root);
    QQmlApplicationEngine engine;bool error=false;
    if(auto *language=qobject_cast<AppLanguage *>(app.property("appLanguage").value<QObject *>())) {
        engine.rootContext()->setContextProperty("appLanguage",language);
        QObject::connect(language,&AppLanguage::languageChanged,&engine,&QQmlEngine::retranslate);
    }
    QObject::connect(&engine,&QQmlApplicationEngine::warnings,&app,[&]{error=true;QTimer::singleShot(0,&app,[]{qApp->exit(52);});});
    engine.rootContext()->setContextProperty("petService",&service);
    engine.rootContext()->setContextProperty("petChat",&chat);
    engine.loadFromModule("Scott.Prototype","DesktopPetWindow");
    if(engine.rootObjects().isEmpty()||error)return 52;
    return app.exec();
}

