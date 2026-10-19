#include "UpdateController.h"
#include "AppLog.h"
#include "AppImageSupport.h"
#include "ProcessSupport.h"
#include "ScottVersion.h"
#include <QCoreApplication>
#include <QDesktopServices>
#include <QDirIterator>
#include <QJsonDocument>
#include <QLocalSocket>
#include <QNetworkReply>
#include <QProcess>
#include <QSaveFile>
#include <QUuid>
#include <QStandardPaths>

namespace {
QString platform() {
#ifdef Q_OS_WIN
    return "windows";
#else
    return "linux";
#endif
}
bool copyTree(const QString &source,const QString &destination) {
    if (!QFileInfo::exists(source)) return false;
    QDirIterator it(source,QDir::Files|QDir::NoDotAndDotDot,QDirIterator::Subdirectories);
    while (it.hasNext()) {
        const auto file=it.next();const auto relative=QDir(source).relativeFilePath(file);
        const auto target=destination+"/"+relative;
        if (!QDir().mkpath(QFileInfo(target).absolutePath()) || !QFile::copy(file,target)) return false;
    }
    return true;
}
}
UpdateController::UpdateController(QString root,QString python,bool preview,QObject *parent,QString cacheRoot)
    :QObject(parent),m_root(QDir(root).absolutePath()),m_python(python),
     m_cacheRoot(cacheRoot.isEmpty()?QStandardPaths::writableLocation(QStandardPaths::GenericCacheLocation)+"/ScottAI/updates":cacheRoot),m_preview(preview) {
    m_image=AppImageSupport::context(m_root);
    m_deadline.setSingleShot(true);
    m_server.setSocketOptions(QLocalServer::UserAccessOption);
    connect(&m_deadline,&QTimer::timeout,this,[this] {fail(QStringLiteral("Окно обновления не запустилось. Scott остаётся открыт."));});
    connect(&m_server,&QLocalServer::newConnection,this,[this] {
        auto *socket=m_server.nextPendingConnection();
        auto buffer=std::make_shared<QByteArray>();
        connect(socket,&QLocalSocket::disconnected,socket,&QObject::deleteLater);
        connect(socket,&QLocalSocket::readyRead,this,[this,socket,buffer] {
            *buffer+=socket->readAll();
            if (buffer->size()>128) {socket->disconnectFromServer();return;}
            if (!buffer->endsWith('\n')) return;
            if (QString::fromUtf8(buffer->trimmed())!=m_cookie || !m_busy) {socket->disconnectFromServer();return;}
            m_deadline.stop();m_server.close();
            socket->write("accepted\n");socket->flush();socket->disconnectFromServer();
            m_message=QStringLiteral("Передаём управление окну обновления…");emit changed();emit handoffReady();
        });
    });
}
UpdateController::~UpdateController() {
    m_deadline.stop();m_server.close();
    for(auto *reply:m_network.findChildren<QNetworkReply*>()){disconnect(reply,nullptr,this,nullptr);reply->abort();}
}
bool UpdateController::canInstall() const {
    if (m_preview || !m_release.verifiedSource()) return false;
#ifdef Q_OS_WIN
    return m_release.name.endsWith("-setup.exe") && QFileInfo::exists(m_root+"/launcher/ScottAIUpdater.exe")
        && QFileInfo::exists(m_root+"/runtime/python.exe");
#else
    if(!m_image.isEmpty())return m_release.name.endsWith("-linux-x86_64.AppImage")
        && AppImageSupport::unchanged(m_image) && QFileInfo::exists(m_root+"/launcher/ScottAIUpdater")
        && QFileInfo::exists(m_root+"/backend/update_appimage.py") && QFileInfo::exists(m_python);
    // Extract-and-run AppImages can have writable temporary payloads. They
    // still require image replacement, never the tar installer in that mount.
    QFile marker(m_root+"/.scott-linux-install.json");
    if (!marker.open(QIODevice::ReadOnly)) return false;
    const auto installation=QJsonDocument::fromJson(marker.readAll());
    if (!installation.isObject() || installation.object().contains("image_layout")) return false;
    return m_release.name.endsWith("-linux-x86_64.tar.gz") && QFileInfo(m_root).isWritable()
        && QFileInfo::exists(m_root+"/.scott-linux-install.json") && QFileInfo::exists(m_root+"/launcher/ScottAIUpdater")
        && QFileInfo::exists(m_python);
#endif
}
void UpdateController::check() {
    if (m_busy || m_preview) return;
    auto repo=qEnvironmentVariable("SCOTT_UPDATE_REPO","stalker1243/Scott-AI");
    if (!QRegularExpression("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$").match(repo).hasMatch()) {fail(QStringLiteral("Некорректный репозиторий обновлений."));return;}
    m_busy=true;m_message=QStringLiteral("Проверяем обновления…");emit changed();
    QNetworkRequest request(QUrl("https://api.github.com/repos/"+repo+"/releases/latest"));
    request.setTransferTimeout(10000);request.setRawHeader("User-Agent","ScottAI");
    request.setRawHeader("Accept","application/vnd.github+json");
    auto *reply=m_network.get(request);auto bytes=std::make_shared<QByteArray>();
    connect(reply,&QNetworkReply::readyRead,this,[reply,bytes] {*bytes+=reply->readAll();if(bytes->size()>1024*1024)reply->abort();});
    connect(reply,&QNetworkReply::finished,this,[this,reply,repo,bytes] {
        reply->deleteLater();m_busy=false;
        if(reply->error()!=QNetworkReply::NoError) {fail(QStringLiteral("Не удалось проверить обновления. Попробуйте позже."));return;}
        *bytes+=reply->readAll();QJsonParseError error;const auto document=QJsonDocument::fromJson(*bytes,&error);
        if(error.error!=QJsonParseError::NoError || !document.isObject()) {fail(QStringLiteral("Сервис вернул некорректные сведения о выпуске."));return;}
        m_release=releaseFromGitHub(document.object(),SCOTT_APP_VERSION,repo,m_image.isEmpty()?platform():QStringLiteral("appimage"));
        m_message=m_release.available ? QStringLiteral("Доступна версия %1").arg(m_release.version) : QStringLiteral("Установлена последняя версия");emit changed();
    });
}
void UpdateController::openRelease() {
    const auto url=m_release.page.isEmpty() ? QUrl("https://github.com/stalker1243/Scott-AI/releases") : m_release.page;
    QDesktopServices::openUrl(url);
}
void UpdateController::install() {
    if(m_busy || !canInstall()) return;
    m_busy=true;m_message=QStringLiteral("Подготавливаем окно обновления…");emit changed();
    QTimer::singleShot(0,this,&UpdateController::prepare);
}
void UpdateController::fail(const QString &message) {m_busy=false;m_deadline.stop();m_server.close();m_message=message;AppLog::append("updater.log",message);emit changed();}
void UpdateController::prepare() {
    if(!canInstall()){fail(QStringLiteral("Файл приложения изменился или недоступен для обновления. Откройте страницу выпуска."));return;}
    auto cache=m_cacheRoot+"/"+QUuid::createUuid().toString(QUuid::Id128);
    AppLog::ensureDirectory(cache+"/launcher");
    const auto launcher=m_root+"/launcher";
#ifdef Q_OS_WIN
    const auto executable=cache+"/launcher/ScottAIUpdater.exe";
    bool copied=QFile::copy(launcher+"/ScottAIUpdater.exe",executable);
    for (const auto &name:QDir(launcher).entryList({"*.dll"},QDir::Files)) copied=QFile::copy(launcher+"/"+name,cache+"/launcher/"+name) && copied;
    for (const auto &name:{"platforms","imageformats","tls","networkinformation","styles","iconengines"})
        if(QDir(launcher+"/"+name).exists()) copied=copyTree(launcher+"/"+name,cache+"/launcher/"+name) && copied;
    QFile configuration(cache+"/launcher/qt.conf");
    copied=configuration.open(QIODevice::WriteOnly) && copied;
    if(configuration.isOpen())configuration.write("[Paths]\nPrefix=.\nPlugins=.\n");
#else
    const auto executable=cache+"/launcher/ScottAIUpdater";
    bool copied=QFile::copy(launcher+"/ScottAIUpdater",executable)
        && copyTree(m_root+"/lib",cache+"/lib") && copyTree(m_root+"/plugins",cache+"/plugins")
        && QFile::copy(launcher+"/qt.conf",cache+"/launcher/qt.conf")
        && QFile::copy(m_root+"/backend/update_package.py",cache+"/update_package.py");
    if(!m_image.isEmpty())copied=QFile::copy(m_root+"/backend/update_appimage.py",cache+"/update_appimage.py") && copied;
#endif
    if(!copied) {fail(QStringLiteral("Не удалось подготовить файлы обновления. Проверьте место и права."));return;}
    m_cookie=QUuid::createUuid().toString(QUuid::Id128);m_serverName="scott-update-"+m_cookie;
    if(!m_server.listen(m_serverName)) {fail(QStringLiteral("Не удалось связаться с окном обновления."));return;}
    QJsonObject job{{"root",m_root},{"python",m_python},{"parent",QString::number(QCoreApplication::applicationPid())},
                    {"cookie",m_cookie},{"server",m_serverName},{"release",m_release.json()}};
    if(!m_image.isEmpty())job["image"]=m_image;
    QSaveFile file(cache+"/job.json");
    if(!file.open(QIODevice::WriteOnly)) {fail(QStringLiteral("Не удалось сохранить параметры обновления."));return;}
    file.setPermissions(QFile::ReadOwner|QFile::WriteOwner);file.write(QJsonDocument(job).toJson());
    if(!file.commit()) {fail(QStringLiteral("Не удалось сохранить параметры обновления."));return;}
    QProcess process;backgroundProcess(process);auto env=QProcessEnvironment::systemEnvironment();
    // Keep the caller's provider environment for the restarted application.
    // Credentials never enter job.json or public GitHub request headers.
    for(const auto &key:env.keys()) if((key.startsWith("QT_") && key!="QT_QPA_PLATFORM")
        || key.startsWith("QML_") || key=="PYTHONHOME" || key=="PYTHONPATH")env.remove(key);
#ifndef Q_OS_WIN
    env.insert("LD_LIBRARY_PATH",cache+"/lib");env.insert("QT_PLUGIN_PATH",cache+"/plugins");
    env.insert("SSL_CERT_FILE",qEnvironmentVariable("SSL_CERT_FILE","/etc/ssl/certs/ca-certificates.crt"));
#endif
    process.setProcessEnvironment(env);process.setProgram(executable);process.setArguments({"--job",cache+"/job.json"});process.setWorkingDirectory(cache);
    if(!process.startDetached()) {fail(QStringLiteral("Не удалось открыть окно обновления. Scott остаётся открыт."));return;}
    m_deadline.start(15000);
}
