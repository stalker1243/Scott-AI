#pragma once
#include <QObject>
#include <QElapsedTimer>
#include <QFutureWatcher>
#include <QSet>
#include <QTimer>
#include <functional>

// Only visible application identities, kept in memory. No titles, images,
// executable paths, keyboard input or application history are collected.
class DesktopActivity : public QObject {
    Q_OBJECT
public:
    using Snapshot=QSet<quint64>;
    using Sampler=std::function<Snapshot()>;
    explicit DesktopActivity(QObject *parent=nullptr,Sampler sampler={},int interval=1000);
    ~DesktopActivity() override;
    void setEnabled(bool enabled);
    bool supported() const;
    bool initialized() const { return !m_seed; }
signals:
    void applicationOpened();
private:
    void scan();
    static Snapshot visibleApplications();
    Sampler m_sampler;
    bool m_custom=false,m_enabled=false,m_seed=true;
    quint64 m_generation=0,m_scanGeneration=0;
    Snapshot m_known;
    QElapsedTimer m_cooldown;
    QTimer m_timer;
    QFutureWatcher<Snapshot> m_scan;
};
