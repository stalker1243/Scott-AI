#include "UpdateWindow.h"
#include "AppImageSupport.h"
#include "AppLog.h"
#include "ProcessSupport.h"
#include <QCloseEvent>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QFileInfo>
#include <QCryptographicHash>
#include <QStandardPaths>
#include <QJsonDocument>
#include <QCoreApplication>
#include <QApplication>
#include <QIcon>
#include <QScreen>
#ifdef Q_OS_WIN
#include <qt_windows.h>
#endif

UpdateWindow::UpdateWindow(QJsonObject job,bool preview,QWidget *parent)
    :QWidget(parent),m_job(job),m_release(UpdateRelease::fromJson(job["release"].toObject())),m_preview(preview) {
    setWindowTitle(QCoreApplication::translate("Launcher", "Обновление Scott AI"));setFixedSize(480,260);
    if(!QGuiApplication::platformName().startsWith("wayland"))
        if(auto *screen=QGuiApplication::primaryScreen())move(screen->availableGeometry().center()-rect().center());
    setWindowIcon(QIcon(":/brand/scott.ico"));
    setWindowFlags(Qt::Window|Qt::WindowTitleHint|Qt::CustomizeWindowHint|Qt::WindowCloseButtonHint|Qt::WindowMinimizeButtonHint);
    setStyleSheet("QWidget {background:#172235;color:#edf3ff;font-family:'Segoe UI';font-size:13px;}"
        "QLabel#title {font-size:21px;font-weight:600;} QLabel#muted {color:#9fb1ce;}"
        "QProgressBar {border:0;background:#273752;border-radius:5px;height:8px;}"
        "QProgressBar::chunk {background:#7ca9ff;border-radius:5px;}"
        "QPushButton {background:#293c5d;border:0;border-radius:7px;padding:8px 14px;}"
        "QPushButton:hover {background:#375583;} QPushButton:disabled {color:#637491;}"
        "QPushButton#primary {background:#4478d3;} QPushButton#primary:hover {background:#548bea;}");
    auto *layout=new QVBoxLayout(this);layout->setContentsMargins(26,22,26,22);layout->setSpacing(12);
    m_title=new QLabel(QCoreApplication::translate("Launcher", "Обновляем Scott AI"));m_title->setObjectName("title");layout->addWidget(m_title);
    m_message=new QLabel(QCoreApplication::translate("Launcher", "Завершаем работу лаунчера…"));m_message->setWordWrap(true);m_message->setMinimumHeight(44);layout->addWidget(m_message);
    m_progress=new QProgressBar;m_progress->setTextVisible(false);m_progress->setRange(0,0);layout->addWidget(m_progress);
    m_details=new QLabel(m_release.version.isEmpty()?QString():QCoreApplication::translate("Launcher", "Версия %1").arg(m_release.version));m_details->setObjectName("muted");layout->addWidget(m_details);
    auto *row=new QHBoxLayout;row->addStretch();
    m_retry=new QPushButton(QCoreApplication::translate("Launcher", "Повторить"));m_retry->setObjectName("primary");m_retry->hide();row->addWidget(m_retry);
    m_return=new QPushButton(QCoreApplication::translate("Launcher", "Открыть Scott"));m_return->hide();row->addWidget(m_return);
    m_cancel=new QPushButton(QCoreApplication::translate("Launcher", "Отмена"));row->addWidget(m_cancel);layout->addLayout(row);
    connect(m_retry,&QPushButton::clicked,this,&UpdateWindow::download);
    connect(m_return,&QPushButton::clicked,this,&UpdateWindow::reopen);
    connect(m_cancel,&QPushButton::clicked,this,[this]{m_transfer.cancel();if(!m_transfer.active())reopen();});
    connect(&m_transfer,&UpdateTransfer::stage,this,[this](const QString &message){m_message->setText(QCoreApplication::translate("Launcher",message.toUtf8().constData()));});
    connect(&m_transfer,&UpdateTransfer::stage,this,[](const QString &message){AppLog::append("updater.log",message);});
    connect(&m_transfer,&UpdateTransfer::progress,this,[this](qint64 done,qint64 total){
        m_progress->setRange(0,1000);m_progress->setValue(int(done*1000/total));
        m_details->setText(QCoreApplication::translate("Launcher", "%1% · %2 / %3 МиБ").arg(done*100/total).arg(done/1048576.,0,'f',1).arg(total/1048576.,0,'f',1));
    });
    connect(&m_transfer,&UpdateTransfer::failed,this,&UpdateWindow::fail);
    connect(&m_transfer,&UpdateTransfer::verified,this,&UpdateWindow::install);
    backgroundProcess(m_installer);
    connect(&m_installer,&QProcess::readyReadStandardOutput,this,[this]{AppLog::append("updater.log",QString::fromUtf8(m_installer.readAllStandardOutput()));});
    connect(&m_installer,&QProcess::readyReadStandardError,this,[this]{AppLog::append("updater.log",QString::fromUtf8(m_installer.readAllStandardError()));});
    connect(&m_installer,&QProcess::errorOccurred,this,[this](QProcess::ProcessError error){if(error==QProcess::FailedToStart)fail(QCoreApplication::translate("Launcher", "Установщик не запустился. Можно открыть Scott и повторить обновление."));});
    connect(&m_installer,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),this,[this](int code,QProcess::ExitStatus status){
        m_installing=false;
        if(code!=0 || status!=QProcess::NormalExit) {
            QFile log(m_directory+"/install.log");
            if(log.open(QIODevice::ReadOnly)){log.seek(qMax<qint64>(0,log.size()-32768));AppLog::append("updater.log",QString::fromUtf8(log.readAll()));}
            fail(QCoreApplication::translate("Launcher", "Обновление не завершено (код %1). Журнал сохранён; можно повторить установку.").arg(code));return;
        }
        m_success=true;m_progress->setRange(0,100);m_progress->setValue(100);m_title->setText(QCoreApplication::translate("Launcher", "Scott AI обновлён"));
        m_message->setText(QCoreApplication::translate("Launcher", "Открываем приложение…"));AppLog::append("updater.log","Installation completed");QTimer::singleShot(900,this,&UpdateWindow::reopen);
    });
}
bool UpdateWindow::parentExited() {
#ifdef Q_OS_WIN
    return m_parentHandle && WaitForSingleObject(HANDLE(m_parentHandle),0)==WAIT_OBJECT_0;
#else
    const auto current=AppImageSupport::processIdentity(m_job["parent"].toString());
    const bool exited=current.isEmpty() || current!=m_parentIdentity;
    if(!exited)return false;
    const auto image=m_job["image"].toObject();
    return !image["extract"].toBool() || AppImageSupport::processIdentity(image["runtime_parent"].toString())
        !=image["runtime_identity"].toString().toLatin1();
#endif
}
void UpdateWindow::begin() {
    if(m_preview)return;
    m_directory=m_job["_directory"].toString();
    if(!m_release.verifiedSource() || m_job["cookie"].toString().size()!=32 || m_job["server"].toString()!="scott-update-"+m_job["cookie"].toString()) {
        fail(QCoreApplication::translate("Launcher", "Параметры обновления не прошли проверку."));return;
    }
    const auto image=m_job["image"].toObject();
    const auto root=image.isEmpty()?m_job["root"].toString():image["path"].toString();
    const auto key=QString::fromLatin1(QCryptographicHash::hash(root.toUtf8(),QCryptographicHash::Sha256).toHex());
    const auto lockDir=QDir(m_directory).absoluteFilePath("..");AppLog::ensureDirectory(lockDir);
    m_lock=std::make_unique<QLockFile>(lockDir+"/"+key+".lock");
    if(!m_lock->tryLock()) {QCoreApplication::exit(3);return;}
#ifdef Q_OS_WIN
    m_parentHandle=OpenProcess(SYNCHRONIZE,FALSE,m_job["parent"].toString().toULongLong());
    if(!m_parentHandle){QCoreApplication::exit(3);return;}
    connect(qApp,&QCoreApplication::aboutToQuit,this,[this]{CloseHandle(HANDLE(m_parentHandle));m_parentHandle=nullptr;});
#else
    QFile identity("/proc/"+m_job["parent"].toString()+"/stat");
    if(!identity.open(QIODevice::ReadOnly)){QCoreApplication::exit(3);return;}
    auto bytes=identity.readAll();auto fields=bytes.mid(bytes.lastIndexOf(')')+2).split(' ');
    if(fields.size()<20){QCoreApplication::exit(3);return;}m_parentIdentity=fields[19];
#endif
    m_deadline.setSingleShot(true);connect(&m_deadline,&QTimer::timeout,this,[]{QCoreApplication::exit(3);});m_deadline.start(10000);
    connect(&m_socket,&QLocalSocket::connected,this,[this]{m_socket.write(m_job["cookie"].toString().toUtf8()+"\n");m_socket.flush();});
    auto accepted=std::make_shared<QByteArray>();
    connect(&m_socket,&QLocalSocket::readyRead,this,[this,accepted]{
        *accepted+=m_socket.readAll();if(*accepted!="accepted\n")return;
        m_accepted=true;m_deadline.stop();m_wait.setInterval(80);
        auto elapsed=std::make_shared<int>(0);
        connect(&m_wait,&QTimer::timeout,this,[this,elapsed]{
            if(parentExited()){m_wait.stop();download();}
            else if(++*elapsed>190){m_wait.stop();fail(QCoreApplication::translate("Launcher", "Scott ещё работает. Закройте его и повторите обновление."));}
        });m_wait.start();
    });
    m_socket.connectToServer(m_job["server"].toString());
}
void UpdateWindow::download() {
    if(m_preview || !m_accepted || m_installing)return;
    if(!parentExited()){fail(QCoreApplication::translate("Launcher", "Закройте Scott перед обновлением."));return;}
    m_retry->hide();m_return->hide();m_cancel->show();m_progress->setRange(0,0);
    const auto image=m_job["image"].toObject();
    const auto identity=image.isEmpty()?m_job["root"].toString():image["path"].toString();
    const auto key=QString::fromLatin1(QCryptographicHash::hash((identity+"/"+m_release.download.toString()).toUtf8(),QCryptographicHash::Sha256).toHex());
    const auto downloads=QDir(m_directory).absoluteFilePath("../downloads/")+key;
    AppLog::ensureDirectory(downloads);
    m_transfer.start(m_release,downloads);
}
void UpdateWindow::install(const QString &path,const QString &sha256) {
    m_release.sha256=sha256;
    m_installing=true;m_retry->hide();m_return->hide();m_cancel->hide();m_progress->setRange(0,0);
    m_message->setText(QCoreApplication::translate("Launcher", "Устанавливаем обновление…"));m_details->setText(QCoreApplication::translate("Launcher", "История, настройки и модели сохраняются"));
    const auto root=m_job["root"].toString();
#ifdef Q_OS_WIN
    m_installer.setProgram(path);m_installer.setArguments({"/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/SP-","/DIR="+root,"/LOG="+m_directory+"/install.log"});
#else
    m_installer.setProgram(m_job["python"].toString());
    if(m_job["image"].isObject())m_installer.setArguments({"-I",m_directory+"/update_appimage.py","--archive",path,"--sha256",sha256,"--version",m_release.version,"--job",m_directory+"/job.json"});
    else m_installer.setArguments({"-I",m_directory+"/update_package.py","--archive",path,"--sha256",sha256,"--version",m_release.version,"--prefix",root});
#endif
    m_installer.start();
}
void UpdateWindow::fail(const QString &message) {
    m_installing=false;m_wait.stop();m_progress->setRange(0,100);m_progress->setValue(0);
    m_message->setText(QCoreApplication::translate("Launcher",message.toUtf8().constData()));m_details->setText(QCoreApplication::translate("Launcher", "Версия %1 · журнал updater.log").arg(m_release.version));
    m_retry->setVisible(m_accepted);m_return->setVisible(m_accepted);m_cancel->hide();AppLog::append("updater.log",message);
}
void UpdateWindow::reopen() {
    if(m_preview){close();return;}
    if(!m_accepted || m_reopened || m_installing)return;
    if(!parentExited()){
        m_wait.stop();m_message->setText(QCoreApplication::translate("Launcher", "Возвращаемся в Scott…"));
        QTimer::singleShot(100,this,&UpdateWindow::reopen);return;
    }
    m_transfer.cancel();m_reopened=true;
    QProcess process;backgroundProcess(process);const auto root=m_job["root"].toString();
#ifdef Q_OS_WIN
    process.setProgram(root+"/launcher/ScottAIQt.exe");process.setArguments({"--start-backend"});
#else
    const auto image=m_job["image"].toObject();
    if(!image.isEmpty()) {
        process.setProgram(image["path"].toString());
        if(image["extract"].toBool())process.setArguments({"--appimage-extract-and-run"});
    } else {process.setProgram("/bin/bash");process.setArguments({root+"/run.sh"});}
#endif
    auto env=QProcessEnvironment::systemEnvironment();
    for(const auto &key:env.keys())if((key.startsWith("QT_") && key!="QT_QPA_PLATFORM") || key.startsWith("QML_")
        || key=="LD_LIBRARY_PATH" || key=="APPDIR" || key=="APPIMAGE" || key=="ARGV0"
        || key=="TARGET_APPIMAGE" || key=="APPIMAGE_EXTRACT_AND_RUN")env.remove(key);
    process.setProcessEnvironment(env);process.setWorkingDirectory(QDir::homePath());
    if(!process.startDetached()){m_reopened=false;fail(QCoreApplication::translate("Launcher", "Не удалось открыть Scott. Запустите его ярлыком."));return;}
    QCoreApplication::quit();
}
void UpdateWindow::closeEvent(QCloseEvent *event) {
    if(m_preview || m_reopened || !m_accepted){event->accept();return;}
    event->ignore();if(!m_installing)reopen();
}
void UpdateWindow::previewState(int index) {
    if(!m_preview)return;
    if(index==0){m_progress->setRange(0,100);m_progress->setValue(43);m_message->setText(QCoreApplication::translate("Launcher", "Скачиваем обновление…"));m_details->setText(QCoreApplication::translate("Launcher", "43% · 52,1 / 121,0 МиБ"));}
    else if(index==1){m_message->setText(QCoreApplication::translate("Launcher", "Устанавливаем обновление…"));m_progress->setRange(0,0);m_details->setText(QCoreApplication::translate("Launcher", "История, настройки и модели сохраняются"));m_cancel->hide();}
    else{fail(QCoreApplication::translate("Launcher", "Загрузка прервалась. Скачанная часть сохранена; можно повторить."));m_retry->show();m_return->show();}
}
