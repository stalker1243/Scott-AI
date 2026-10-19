#pragma once
#include <QObject>
#include <QFutureWatcher>
#include <QLocalSocket>
#include <QPointer>
#include <QTimer>
#include <QVariantMap>

class QApplication;
class PetController : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString kind READ kind NOTIFY changed)
    Q_PROPERTY(QString variant READ variant NOTIFY changed)
    Q_PROPERTY(bool enabled READ enabled NOTIFY changed)
    Q_PROPERTY(bool running READ running NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(bool motion READ motion NOTIFY changed)
    Q_PROPERTY(int sizePercent READ sizePercent NOTIFY changed)
    Q_PROPERTY(bool canReposition READ canReposition CONSTANT)
    Q_PROPERTY(QString error READ error NOTIFY changed)
public:
    explicit PetController(bool preview=false, QString stateRoot={}, QString cacheRoot={}, QString executable={}, QObject *parent=nullptr);
    ~PetController() override;
    QString kind() const {return m_kind;}
    QString variant() const {return m_variant;}
    bool enabled() const {return m_enabled;}
    bool running() const {return m_running;}
    bool busy() const {return m_busy;}
    bool motion() const {return m_motion;}
    int sizePercent() const {return m_sizePercent;}
    bool canReposition() const;
    QString error() const {return m_error;}
    QString stateRoot() const {return m_stateRoot;}
    static QString defaultStateRoot();
    static QString serverName(const QString &root);
    static QStringList variants(const QString &kind);
    void configureChat(const QString &directory,const QString &python);
    Q_INVOKABLE void selectPet(const QString &kind);
    Q_INVOKABLE void selectVariant(const QString &variant);
    Q_INVOKABLE void setEnabled(bool enabled);
    Q_INVOKABLE void setMotion(bool enabled);
    Q_INVOKABLE void setSizePercent(int value);
    Q_INVOKABLE void resetPosition();
    Q_INVOKABLE void restore();
    Q_INVOKABLE void interact();
signals:
    void changed();
private:
    void save();
    void read();
    void poll();
    void finishRequest(QLocalSocket *socket,bool replied);
    void finishLaunch();
    void saveChatContext();
    bool m_preview=false,m_enabled=false,m_running=false,m_busy=false,m_motion=true;
    bool m_configPending=false,m_stopPending=false,m_playPending=false,m_recenterPending=false,m_launchHandled=true;
    int m_sizePercent=100;
    quint64 m_revision=0;
    QString m_kind="scott",m_variant="blue",m_error,m_stateRoot,m_cacheRoot,m_executable;
    QString m_backendDirectory,m_python;
    QTimer m_poll,m_startup;
    QPointer<QLocalSocket> m_socket;
    QFutureWatcher<QVariantMap> m_prepare;
};

int runDesktopPet(QApplication &app,const QString &stateRoot);
