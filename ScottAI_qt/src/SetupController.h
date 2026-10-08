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
    Q_PROPERTY(bool compact READ compact WRITE setCompact NOTIFY changed)
public:
    explicit SetupController(QObject *parent = nullptr);
    ~SetupController() override;
    bool visible() const { return m_visible; }
    bool busy() const { return m_busy; }
    double progress() const { return m_progress; }
    QString message() const { return m_message; }
    QString error() const { return m_error; }
    bool compact() const { return m_compact; }
    void setCompact(bool value) { if (!m_busy && m_compact != value) { m_compact = value; emit changed(); } }
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
    bool m_visible = false, m_busy = false, m_check = false, m_compact = false, m_cancelled = false;
    double m_progress = 0;
};
