#include "PetChatController.h"
#include "AppLog.h"
#include "ProcessSupport.h"
#include "PetController.h"
#include <QLocalSocket>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QTimer>

PetChatController::PetChatController(QString profile,QUrl base,QObject *parent)
    :QObject(parent),m_profile(std::move(profile)),m_client(base) {
    backgroundProcess(m_imageHelper);
    connect(&m_client,&BackendClient::stateChanged,this,[this]{
        if (!m_client.error().isEmpty() && !m_client.busy() && !m_client.chatsBusy()) {
            m_error=m_client.error();m_pending.clear();m_submitted=false;
        }
        emit changed();QTimer::singleShot(0,this,&PetChatController::advance);
    });
    connect(&m_client,&BackendClient::chatsChanged,this,[this]{emit changed();});
    connect(&m_client,&BackendClient::chatSent,this,[this]{
        m_pending.clear();m_submitted=false;m_error.clear();emit changed();emit sent();
    });
    connect(&m_imageHelper,&QProcess::readyReadStandardOutput,this,[this]{AppLog::appendChunk("pet-backend.log",m_helperLog,m_imageHelper.readAllStandardOutput());});
    connect(&m_imageHelper,&QProcess::readyReadStandardError,this,[this]{AppLog::appendChunk("pet-backend.log",m_helperLog,m_imageHelper.readAllStandardError());});
    connect(&m_imageHelper,&QProcess::errorOccurred,this,[this]{m_error=QStringLiteral("Не удалось запустить фоновую службу Scott.");m_pending.clear();emit changed();});
    connect(&m_imageHelper,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),this,[this](int code){
        if(code && !m_client.online()){m_error=QStringLiteral("Фоновая служба завершилась. Откройте установленный Scott и проверьте подготовку.");m_pending.clear();emit changed();}
    });
}
PetChatController::~PetChatController() {
    // This handle belongs to our own helper, never to an existing launcher.
    if(m_imageHelper.state()!=QProcess::NotRunning){
        QLocalSocket control;control.connectToServer(PetController::serverName(m_profile)+"-backend");
        if(control.waitForConnected(500)){control.write("{\"op\":\"quit\"}\n");control.waitForBytesWritten(500);}
        if(!m_imageHelper.waitForFinished(3000)){m_imageHelper.terminate();if(!m_imageHelper.waitForFinished(1000)){m_imageHelper.kill();m_imageHelper.waitForFinished(1000);}}
    }
}
QString PetChatController::status() const {
    if(m_client.busy()||m_submitted)return QStringLiteral("Scott отвечает…");
    if(m_client.starting()||!m_pending.isEmpty()||m_imageHelper.state()!=QProcess::NotRunning&&!m_client.online())return QStringLiteral("Подключаю Scott…");
    return m_client.online()?QStringLiteral("На связи"):QStringLiteral("Нет подключения");
}
void PetChatController::open() {
    m_error.clear();
    if(!m_opened){m_opened=true;m_client.beginPolling();}
    if(!m_client.online())ensureBackend();else m_client.refresh();
    emit changed();
}
void PetChatController::send(const QString &text) {
    const auto value=text.trimmed();if(value.isEmpty()||busy())return;
    if(value.size()>16000){m_error=QStringLiteral("Сократите сообщение до 16 000 символов.");emit changed();return;}
    m_error.clear();m_pending=value;
    if(!m_opened)open();else if(!m_client.online())ensureBackend();
    advance();emit changed();
}
void PetChatController::advance() {
    if(m_pending.isEmpty()||m_submitted||!m_client.online()||m_client.busy()||m_client.chatsBusy())return;
    m_submitted=true;m_error.clear();m_client.sendChatMessage(m_pending);emit changed();
}
void PetChatController::ensureBackend() {
    if(m_client.starting()||m_client.ownsBackend()||m_imageHelper.state()!=QProcess::NotRunning)return;
    QFile context(m_profile+"/backend.json");QJsonObject data;
    if(!QFileInfo(context).isSymLink() && context.size()<=16384 && context.open(QIODevice::ReadOnly))data=QJsonDocument::fromJson(context.readAll()).object();
    const auto directory=data["directory"].toString(),python=data["python"].toString(),image=data["appimage"].toString();
    if(!QFileInfo::exists(directory+"/main.py") && QFileInfo(image).isFile() && QFileInfo(image).isAbsolute()) {
        auto environment=QProcessEnvironment::systemEnvironment();
        if(data["extract"].toBool())environment.insert("APPIMAGE_EXTRACT_AND_RUN","1");
        m_imageHelper.setProcessEnvironment(environment);
        m_imageHelper.setProgram(image);m_imageHelper.setArguments({"--pet-backend","--pet-state",m_profile});
        m_imageHelper.start();return;
    }
    m_client.configureProcess(directory,python);
    // startBackend probes health first and only owns processes it starts.
    m_client.startBackend();
}
