#pragma once
#include <QObject>
#include <QMenu>
#include <QQuickWindow>
#include <QSystemTrayIcon>
#include "BackendClient.h"

class TrayController final : public QObject {
    Q_OBJECT
public:
    TrayController(QSystemTrayIcon *tray, BackendClient *client, QQuickWindow *window, bool testMode = false);
    ~TrayController() override;
    QMenu *menu() { return &m_menu; }
public slots:
    void restoreWindow();
signals:
    void notificationRequested(const QString &title, const QString &text);
private slots:
    void sync();
private:
    QAction *action(const char *name, const QString &text, bool checkable = false);
    void showWindow(int tab = -1);
    void persist();
    void notify(const QString &title, const QString &text);
    QSystemTrayIcon *m_tray;
    BackendClient *m_client;
    QQuickWindow *m_window;
    bool m_testMode;
    QWindow::Visibility m_restoreVisibility = QWindow::Windowed;
    qsizetype m_messageCount;
    QMenu m_menu;
    QAction *m_status, *m_toggle, *m_pause, *m_quiet, *m_top, *m_notifications, *m_start, *m_stop;
};
