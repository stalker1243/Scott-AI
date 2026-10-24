#pragma once
#include "BackendClient.h"
#include <QObject>
#include <QProcess>

// A lazy session with the same chat and command endpoint as the launcher.
// Merely displaying a companion does not contact or start the backend.
class PetChatController : public QObject {
    Q_OBJECT
    Q_PROPERTY(BackendClient *backend READ backend CONSTANT)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QString status READ status NOTIFY changed)
public:
    explicit PetChatController(QString profile,QUrl base=QUrl("http://127.0.0.1:8000"),QObject *parent=nullptr);
    ~PetChatController() override;
    BackendClient *backend() { return &m_client; }
    bool busy() const { return !m_pending.isEmpty() || m_client.busy() || m_client.chatsBusy() || m_client.starting() || (!m_client.online() && m_imageHelper.state()!=QProcess::NotRunning); }
    QString error() const { return m_error; }
    QString status() const;
    Q_INVOKABLE void open();
    Q_INVOKABLE void toggleVoice();
    Q_INVOKABLE void send(const QString &text);
signals:
    void changed();
    void sent();
    void voiceFailed(const QString &message);
private:
    void advance();
    void ensureBackend();
    QString m_profile,m_pending,m_error;
    bool m_opened=false,m_submitted=false,m_voicePending=false;
    BackendClient m_client;
    QProcess m_imageHelper;
    QByteArray m_helperLog;
};
