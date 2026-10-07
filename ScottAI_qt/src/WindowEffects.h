#pragma once

#include <QAbstractNativeEventFilter>
#include <QObject>
#include <QPointer>
#include <QQuickWindow>

// The compositor blurs only the desktop backdrop; the Qt scene stays sharp.
class WindowEffects final : public QObject, public QAbstractNativeEventFilter {
    Q_OBJECT
    Q_PROPERTY(bool available READ available NOTIFY changed)
    Q_PROPERTY(bool active READ active NOTIFY changed)
    Q_PROPERTY(bool interacting READ interacting NOTIFY interactingChanged)
    Q_PROPERTY(QRect workArea READ workArea NOTIFY workAreaChanged)
public:
    explicit WindowEffects(QObject *parent = nullptr);
    ~WindowEffects() override;
    void attach(QQuickWindow *window);
    bool available() const { return m_available; }
    bool active() const { return m_active; }
    bool interacting() const { return m_interacting; }
    QRect workArea() const;
    bool nativeEventFilter(const QByteArray &, void *message, qintptr *) override;
protected:
    bool eventFilter(QObject *, QEvent *) override;
private slots:
    void refresh();
signals:
    void changed();
    void interactingChanged();
    void workAreaChanged();
    void moveFinished();
private:
    QPointer<QQuickWindow> m_window;
    WId m_windowId = 0;
    WId m_appliedWindowId = 0;
    bool m_lastFrosted = false;
    bool m_lastDark = false;
    bool m_available = false;
    bool m_active = false;
    bool m_interacting = false;
    bool m_moveDetected = false;
};
