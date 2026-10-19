#pragma once
#include "UpdateRelease.h"
#include <QObject>
#include <QNetworkAccessManager>
#include <QLocalServer>
#include <QTimer>

class UpdateController : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(bool available READ available NOTIFY changed)
    Q_PROPERTY(bool canInstall READ canInstall NOTIFY changed)
    Q_PROPERTY(QString version READ version NOTIFY changed)
    Q_PROPERTY(QString message READ message NOTIFY changed)
public:
    UpdateController(QString root,QString python,bool preview=false,QObject *parent=nullptr,QString cacheRoot={});
    ~UpdateController() override;
    bool busy() const {return m_busy;}
    bool available() const {return m_release.available;}
    bool canInstall() const;
    QString version() const {return m_release.version;}
    QString message() const {return m_message;}
    Q_INVOKABLE void check();
    Q_INVOKABLE void install();
    Q_INVOKABLE void openRelease();
signals:
    void changed();
    void handoffReady();
private:
    friend class UpdateControllerTests;
    void prepare();
    void fail(const QString &message);
    QString m_root,m_python,m_message,m_cookie,m_serverName;
    QString m_cacheRoot;
    UpdateRelease m_release;
    QJsonObject m_image;
    bool m_busy=false,m_preview=false;
    QNetworkAccessManager m_network;
    QLocalServer m_server;
    QTimer m_deadline;
};
