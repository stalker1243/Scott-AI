#pragma once
#include <QObject>
#include <QAbstractNativeEventFilter>
#include <QPointer>
#include <QQuickWindow>

// Geometry and transitions belong to the native window manager.
class WindowMotion final : public QObject, public QAbstractNativeEventFilter {
    Q_OBJECT
    Q_PROPERTY(bool running READ running NOTIFY changed)
    Q_PROPERTY(int targetVisibility READ targetVisibility NOTIFY changed)
public:
    explicit WindowMotion(QObject *parent = nullptr);
    ~WindowMotion() override;
    void attach(QQuickWindow *window);
    bool running() const { return false; }
    int targetVisibility() const { return m_window ? int(m_window->visibility()) : int(QWindow::Hidden); }
    Q_INVOKABLE void toggleMaximized();
    Q_INVOKABLE void maximize();
    Q_INVOKABLE void restore();
    Q_INVOKABLE void toggleFullScreen();
    Q_INVOKABLE void leaveFullScreen();
    Q_INVOKABLE void finish() {}
    bool nativeEventFilter(const QByteArray &, void *, qintptr *) override;
protected:
    bool eventFilter(QObject *, QEvent *) override;
signals:
    void changed();
    void minimizedRestoreRequested();
private:
    QPointer<QQuickWindow> m_window;
    WId m_windowId = 0;
    QWindow::Visibility m_fullScreenReturn = QWindow::Windowed;
};
