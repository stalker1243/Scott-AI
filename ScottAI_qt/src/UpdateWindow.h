#pragma once
#include "UpdateTransfer.h"
#include <QWidget>
#include <QLabel>
#include <QProgressBar>
#include <QPushButton>
#include <QProcess>
#include <QLockFile>
#include <QLocalSocket>
#include <QTimer>
#include <memory>

class UpdateWindow : public QWidget {
    Q_OBJECT
public:
    explicit UpdateWindow(QJsonObject job,bool preview=false,QWidget *parent=nullptr);
    void begin();
    void previewState(int index);
protected:
    void closeEvent(QCloseEvent *event) override;
private:
    void download();
    void install(const QString &path,const QString &sha256);
    void fail(const QString &message);
    void reopen();
    bool parentExited();
    QJsonObject m_job;
    UpdateRelease m_release;
    UpdateTransfer m_transfer;
    QProcess m_installer;
    QLocalSocket m_socket;
    QTimer m_wait,m_deadline;
    std::unique_ptr<QLockFile> m_lock;
    QLabel *m_title,*m_message,*m_details;
    QProgressBar *m_progress;
    QPushButton *m_retry,*m_return,*m_cancel;
    QString m_directory,m_hash;
    bool m_preview=false,m_installing=false,m_accepted=false,m_success=false,m_reopened=false;
#ifdef Q_OS_WIN
    void *m_parentHandle=nullptr;
#else
    QByteArray m_parentIdentity;
#endif
};
