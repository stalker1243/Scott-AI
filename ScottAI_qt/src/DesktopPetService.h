#pragma once
#include <QObject>
#include <QPointF>
#include <QPointer>
#include <QSettings>
#include <QLockFile>
#include <QLocalServer>
#include <QTimer>
#include <QFileSystemWatcher>
#include "DesktopActivity.h"

class QQuickWindow;
class DesktopPetService : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString kind READ kind NOTIFY changed)
    Q_PROPERTY(QString variant READ variant NOTIFY changed)
    Q_PROPERTY(bool motion READ motion NOTIFY changed)
    Q_PROPERTY(int sizePercent READ sizePercent NOTIFY changed)
    Q_PROPERTY(qreal gazeX READ gazeX NOTIFY gazeChanged)
    Q_PROPERTY(qreal gazeY READ gazeY NOTIFY gazeChanged)
    Q_PROPERTY(bool dragging READ dragging NOTIFY dragChanged)
    Q_PROPERTY(bool canReposition READ canReposition CONSTANT)
public:
    explicit DesktopPetService(QString root,bool trackDesktop=true);
    bool start();
    QString kind() const { return m_kind; }
    QString variant() const { return m_variant; }
    bool motion() const { return m_motion; }
    int sizePercent() const { return m_sizePercent; }
    qreal gazeX() const { return m_gaze.x(); }
    qreal gazeY() const { return m_gaze.y(); }
    bool dragging() const { return m_dragging; }
    bool canReposition() const;
    Q_INVOKABLE void attach(QQuickWindow *window);
    Q_INVOKABLE void stop();
    Q_INVOKABLE void toggleMotion();
    Q_INVOKABLE void setSizePercent(int value);
    Q_INVOKABLE void resetPosition();
    Q_INVOKABLE void menuOpen(bool open);
    Q_INVOKABLE void beginDrag(QPointF local);
    Q_INVOKABLE void updateDrag(QPointF local);
    Q_INVOKABLE bool endDrag();
    Q_INVOKABLE void pointerMoved(QPointF local);
    Q_INVOKABLE QPointF chatPosition(qreal width,qreal height) const;
signals:
    void changed();
    void play();
    void gazeChanged();
    void dragChanged();
    void applicationOpened();
private:
    void readActivity(bool seed=false);
    void save();
    void savePosition();
    void resizeWindow();
    void updateMask();
    void recoverLostWindow();
    QString m_root,m_kind,m_variant;
    bool m_motion=true,m_ready=false,m_pointerDown=false,m_dragging=false,m_menuOpen=false;
    int m_sizePercent=100;
    QPointF m_gaze;
    QPoint m_pressGlobal,m_pressPosition;
    QSettings m_settings;
    QLockFile m_lock;
    QLocalServer m_server;
    QPointer<QQuickWindow> m_window;
    QTimer m_position,m_cursor;
    QTimer m_activityPoll;
    QFileSystemWatcher m_activityWatcher;
    QString m_lastActivity;
    DesktopActivity m_desktopActivity;
    bool m_trackDesktop=true;
};
