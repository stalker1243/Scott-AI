#pragma once
#include "UpdateRelease.h"
#include <QObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QFile>
#include <QCryptographicHash>
#include <QTimer>

class UpdateTransfer : public QObject {
    Q_OBJECT
public:
    explicit UpdateTransfer(QObject *parent=nullptr);
    ~UpdateTransfer() override;
    void start(const UpdateRelease &release,const QString &directory);
    void cancel();
    bool active() const { return m_active; }
signals:
    void progress(qint64 received,qint64 total);
    void stage(const QString &message);
    void failed(const QString &message);
    void verified(const QString &path,const QString &sha256);
private:
    void getChecksum();
    void download();
    void verify(const QString &path);
    void hashStep();
    void fail(const QString &message);
    QNetworkRequest request(const QUrl &url) const;
    QNetworkAccessManager m_network;
    QNetworkReply *m_reply=nullptr;
    QFile m_file;
    UpdateRelease m_release;
    QString m_directory,m_path;
    QCryptographicHash m_hash{QCryptographicHash::Sha256};
    QTimer m_hashTimer;
    bool m_active=false,m_headers=false,m_cancelled=false;
    qint64 m_offset=0;
};
