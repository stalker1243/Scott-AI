#pragma once
#include <QObject>
#include <QProcess>
#include <QElapsedTimer>
#include <QTimer>
#include <QJsonObject>

class SetupController : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool visible READ visible NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(bool checking READ checking NOTIFY changed)
    Q_PROPERTY(bool prepared READ prepared NOTIFY changed)
    Q_PROPERTY(double progress READ progress NOTIFY changed)
    Q_PROPERTY(QString message READ message NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(bool compact READ compact WRITE setCompact NOTIFY changed)
    Q_PROPERTY(QString runtimeMode READ runtimeMode WRITE setRuntimeMode NOTIFY changed)
    Q_PROPERTY(int elapsed READ elapsed NOTIFY changed)
    Q_PROPERTY(QString sizeHint READ sizeHint NOTIFY changed)
public:
    explicit SetupController(QObject *parent = nullptr);
    ~SetupController() override;
    bool visible() const { return m_visible; }
    bool busy() const { return m_busy; }
    bool checking() const { return m_launching || (m_check && m_busy); }
    bool prepared() const { return m_prepared; }
    bool launching() const { return m_launching; }
    void backendReady();
    void backendFailed(const QString &error);
    double progress() const { return m_progress; }
    QString message() const { return m_message; }
    QString error() const { return m_error; }
    bool compact() const { return m_runtimeMode == "cpu"; } // Legacy CPU option, not the torchless profile.
    QString runtimeMode() const { return m_runtimeMode; }
    int elapsed() const { return m_elapsed.isValid() ? int(m_elapsed.elapsed() / 1000) : 0; }
    QString sizeHint() const;
    void setCompact(bool value) { setRuntimeMode(value ? "cpu" : "auto"); }
    void setRuntimeMode(const QString &value);
    void check(const QString &python, const QString &backend);
    Q_INVOKABLE void prepare();
    Q_INVOKABLE void cancel();
signals:
    void changed();
    void ready();
private:
    void run(bool check);
    QProcess m_process;
    QElapsedTimer m_elapsed;
    QTimer m_tick;
    QByteArray m_buffer, m_errorBuffer;
    QString m_python, m_backend, m_message, m_error;
    QString m_runtimeMode = "auto";
    bool m_modeSelected = false;
    bool m_visible = false, m_busy = false, m_check = false, m_cancelled = false;
    bool m_prepared = false, m_launching = false;
    double m_progress = 0;
    QJsonObject m_space;
};
