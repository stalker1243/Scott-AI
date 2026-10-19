#pragma once
#include <QObject>
#include <QTimer>
#include <QString>
#include <functional>

class DesktopSupport final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool trayAvailable READ trayAvailable NOTIFY trayAvailableChanged)
    Q_PROPERTY(bool windowPositioning READ windowPositioning CONSTANT)
public:
    using TrayProbe = std::function<bool()>;
    explicit DesktopSupport(QString platform, TrayProbe probe = {}, QObject *parent = nullptr);
    bool trayAvailable() const { return m_available; }
    bool windowPositioning() const { return supportsWindowPositioning(m_platform); }
    static bool supportsWindowPositioning(const QString &platform) { return !platform.startsWith("wayland", Qt::CaseInsensitive); }
public slots:
    void refresh();
signals:
    void trayAvailableChanged(bool available);
private:
    QString m_platform;
    TrayProbe m_probe;
    bool m_available = false;
    QTimer m_timer;
};
