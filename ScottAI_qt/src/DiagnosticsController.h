#pragma once
#include <QObject>
#include <QProcess>
#include <QTimer>
#include <QVariantList>

class DiagnosticsController : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QVariantList logs READ logs NOTIFY changed)
    Q_PROPERTY(QString text READ text NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QString notice READ notice NOTIFY changed)
    Q_PROPERTY(QString archivePath READ archivePath NOTIFY changed)
    Q_PROPERTY(QString selectedName READ selectedName NOTIFY changed)
public:
    explicit DiagnosticsController(QObject *parent = nullptr);
    ~DiagnosticsController() override;
    void configure(const QString &python, const QString &backend);
    bool busy() const { return m_busy; }
    QVariantList logs() const { return m_logs; }
    QString text() const { return m_text; }
    QString error() const { return m_error; }
    QString notice() const { return m_notice; }
    QString archivePath() const { return m_archive; }
    QString selectedName() const { return m_selected; }
    Q_INVOKABLE void refresh(const QString &name = "backend-process.log");
    Q_INVOKABLE void exportArchive();
    Q_INVOKABLE void exportTo(const QString &path);
    Q_INVOKABLE void openFolder();
signals:
    void changed();
private:
    void run(const QStringList &arguments, bool exporting);
    void finish(int code);
    QProcess m_process;
    QTimer m_timeout;
    QByteArray m_output;
    QString m_python, m_backend, m_text, m_error, m_notice, m_archive;
    QString m_selected = "backend-process.log";
    QVariantList m_logs;
    bool m_busy = false, m_exporting = false;
};
