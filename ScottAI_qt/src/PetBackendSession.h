#pragma once
#include "BackendClient.h"
#include "PetController.h"
#include <QLocalServer>
#include <QLocalSocket>
#include <QLockFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <functional>
#include <memory>

// Keeps an AppImage-mounted backend alive only while its companion exists.
// Shutdown uses a user-only local socket; no process is found or killed by PID.
class PetBackendSession : public QObject {
public:
    PetBackendSession(BackendClient &client,QString profile,std::function<void()> finish,int interval=3000)
        :m_client(client),m_profile(std::move(profile)),m_finish(std::move(finish)),m_lock(m_profile+"/backend.lock") {
        m_watchdog.setInterval(interval);
        m_control.setSocketOptions(QLocalServer::UserAccessOption);
        connect(&m_control,&QLocalServer::newConnection,this,[this]{
            while(m_control.hasPendingConnections()) {
                auto *socket=m_control.nextPendingConnection();auto bytes=std::make_shared<QByteArray>();
                QTimer::singleShot(2000,socket,&QLocalSocket::abort);
                connect(socket,&QLocalSocket::disconnected,socket,&QObject::deleteLater);
                connect(socket,&QLocalSocket::readyRead,this,[this,socket,bytes]{
                    *bytes+=socket->readAll();if(bytes->size()>4096){socket->abort();return;}
                    if(!bytes->endsWith('\n'))return;
                    if(QJsonDocument::fromJson(*bytes).object()["op"]=="quit") { socket->write("{\"ok\":true}\n");socket->flush();m_watchdog.stop();QTimer::singleShot(0,this,m_finish); }
                    socket->disconnectFromServer();
                });
            }
        });
        connect(&m_probe,&QLocalSocket::connected,this,[this]{m_bytes.clear();m_probe.write("{\"op\":\"state\"}\n");});
        connect(&m_probe,&QLocalSocket::readyRead,this,[this]{
            m_bytes+=m_probe.readAll();if(m_bytes.size()>4096){m_probe.abort();return;}
            if(m_bytes.endsWith('\n')){if(QJsonDocument::fromJson(m_bytes).object()["ready"].toBool())m_misses=0;m_probe.abort();}
        });
        connect(&m_watchdog,&QTimer::timeout,this,[this]{
            if(++m_misses>3){m_watchdog.stop();m_finish();return;}
            m_probe.abort();m_probe.connectToServer(PetController::serverName(m_profile));
            if(!m_client.online()&&!m_client.starting()&&!m_client.ownsBackend())m_client.startBackend();
        });
    }
    bool start() {
        if(!m_lock.tryLock(0))return false;
        // A live owner keeps its socket. Do not remove an active endpoint.
        QLocalSocket probe;probe.connectToServer(PetController::serverName(m_profile)+"-backend");
        if(probe.waitForConnected(100))return false;
        QLocalServer::removeServer(PetController::serverName(m_profile)+"-backend");
        if(!m_control.listen(PetController::serverName(m_profile)+"-backend"))return false;
        m_watchdog.start();m_client.beginPolling();m_client.startBackend();return true;
    }
private:
    BackendClient &m_client;QString m_profile;std::function<void()> m_finish;
    QLockFile m_lock;QLocalServer m_control;QLocalSocket m_probe;QTimer m_watchdog;QByteArray m_bytes;int m_misses=0;
};
