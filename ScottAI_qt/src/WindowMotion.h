#pragma once

#include <QObject>
#include <QAbstractNativeEventFilter>
#include <QPointer>
#include <QQuickWindow>
#include <QVariantAnimation>

class WindowMotion final : public QObject, public QAbstractNativeEventFilter {
    Q_OBJECT
    Q_PROPERTY(bool running READ running NOTIFY changed)
    Q_PROPERTY(int targetVisibility READ targetVisibility NOTIFY changed)
public:
    explicit WindowMotion(QObject *parent = nullptr);
    ~WindowMotion() override;
    void attach(QQuickWindow *window);
    bool running() const { return m_running; }
    int targetVisibility() const { return m_target; }
    Q_INVOKABLE void toggleMaximized();
    Q_INVOKABLE void maximize();
    Q_INVOKABLE void restore();
    Q_INVOKABLE void toggleFullScreen();
    Q_INVOKABLE void leaveFullScreen();
    Q_INVOKABLE void finish();
    bool nativeEventFilter(const QByteArray &eventType, void *message, qintptr *result) override;
protected:
    bool eventFilter(QObject *watched, QEvent *event) override;
signals:
    void changed();
    void minimizedRestoreRequested();
private slots:
    void motionPreferenceChanged();
private:
    QWindow::Visibility effectiveVisibility() const;
    void transition(QWindow::Visibility target);
    void commit();
    QPointer<QQuickWindow> m_window;
    WId m_windowId = 0;
    QVariantAnimation m_animation;
    QRect m_normal;
    QRect m_destination;
    QWindow::Visibility m_target = QWindow::Windowed;
    QWindow::Visibility m_fullScreenReturn = QWindow::Windowed;
    bool m_running = false;
    bool m_applying = false;
};
