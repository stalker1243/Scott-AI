#pragma once
#include <QObject>
#include <QProcess>

class SetupController : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool visible READ visible NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(double progress READ progress NOTIFY changed)
    Q_PROPERTY(QString message READ message NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
public:
    explicit SetupController(QObject *parent = nullptr);
    ~SetupController() override;
    bool visible() const { return m_visible; }
    bool busy() const { return m_busy; }
    double progress() const { return m_progress; }
    QString message() const { return m_message; }
    QString error() const { return m_error; }
    void check(const QString &python, const QString &backend);
    Q_INVOKABLE void prepare();
    Q_INVOKABLE void cancel();
signals:
    void changed();
    void ready();
private:
    void run(bool check);
    QProcess m_process;
    QByteArray m_buffer;
    QString m_python, m_backend, m_message, m_error;
    bool m_visible = false, m_busy = false, m_check = false;
    double m_progress = 0;
};
