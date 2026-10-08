#include "TrayController.h"
#include <QApplication>
#include <QAction>
#include <QMetaProperty>
#include <QSignalBlocker>

static bool invokeIfPresent(QObject *object, const char *method) {
    const QByteArray signature = QByteArray(method) + "()";
    if (object->metaObject()->indexOfMethod(signature.constData()) < 0) return false;
    return QMetaObject::invokeMethod(object, method);
}

QAction *TrayController::action(const char *name, const QString &text, bool checkable) {
    auto *item = m_menu.addAction(text);
    item->setObjectName(name); item->setCheckable(checkable);
    return item;
}

TrayController::TrayController(QSystemTrayIcon *tray, BackendClient *client, QQuickWindow *window, bool testMode)
    : m_tray(tray), m_client(client), m_window(window), m_testMode(testMode), m_messageCount(client->messages().size()) {
    tray->setContextMenu(&m_menu);
    if (window->windowState() == Qt::WindowMaximized) m_restoreVisibility = QWindow::Maximized;
    else if (window->windowState() == Qt::WindowFullScreen) m_restoreVisibility = QWindow::FullScreen;
    m_status = action("trayStatus", "ScottAI"); m_status->setEnabled(false);
    m_toggle = action("trayToggle", "Открыть окно");
    connect(m_toggle, &QAction::triggered, this, [this] {
        if (m_window->isVisible() && m_window->windowState() != Qt::WindowMinimized) {
            if (!invokeIfPresent(m_window, "hideToBackground")) m_window->hide();
        } else showWindow();
    });
    connect(action("trayChat", "Диалог"), &QAction::triggered, this, [this] { showWindow(1); });
    connect(action("traySettings", "Настройки"), &QAction::triggered, this, [this] { showWindow(5); });
    m_menu.addSeparator();
    m_pause = action("trayPauseVoice", "Пауза голосового ассистента", true);
    connect(m_pause, &QAction::triggered, this, [this](bool paused) { m_client->setListening(!paused); sync(); });
    m_quiet = action("trayQuiet", "Тихий режим", true);
    connect(m_quiet, &QAction::triggered, this, [this](bool quiet) {
        if (m_quiet->isEnabled()) m_client->applySetting("quiet", {{"quiet", quiet}});
        sync();
    });
    m_top = action("trayAlwaysOnTop", "Поверх остальных окон", true);
    connect(m_top, &QAction::triggered, this, [this](bool top) {
        const bool wasVisible = m_window->isVisible();
        m_window->setProperty("alwaysOnTop", top); persist();
        if (wasVisible) showWindow();
        sync();
    });
    m_notifications = action("trayNotifications", "Уведомлять о готовом ответе", true);
    connect(m_notifications, &QAction::triggered, this, [this](bool enabled) {
        m_window->setProperty("trayNotifications", enabled); persist(); sync();
    });
    connect(action("trayCenter", "Окно в центр экрана"), &QAction::triggered, this, [this] {
        showWindow(); invokeIfPresent(m_window, "centerOnScreen");
    });
    m_menu.addSeparator();
    m_start = action("trayStart", "Запустить Scott");
    connect(m_start, &QAction::triggered, client, &BackendClient::startBackend);
    m_stop = action("trayStop", "Остановить Scott");
    connect(m_stop, &QAction::triggered, client, &BackendClient::stopBackend);
    m_menu.addSeparator();
    connect(action("trayQuit", "Выйти"), &QAction::triggered, this, [this] {
        if (!invokeIfPresent(m_window, "requestQuit")) QApplication::quit();
    });
    connect(&m_menu, &QMenu::aboutToShow, this, [this] {
        sync();
        if (m_client->online()) { m_client->refreshSettings(); m_client->refreshListening(); }
    });
    connect(tray, &QSystemTrayIcon::activated, this, [this](QSystemTrayIcon::ActivationReason reason) {
        if (reason == QSystemTrayIcon::Trigger || reason == QSystemTrayIcon::DoubleClick) showWindow();
        else if (reason == QSystemTrayIcon::MiddleClick) showWindow(1);
    });
    connect(tray, &QSystemTrayIcon::messageClicked, this, [this] { showWindow(1); });
    connect(client, &BackendClient::stateChanged, this, &TrayController::sync);
    connect(client, &BackendClient::metricsChanged, this, &TrayController::sync);
    connect(client, &BackendClient::settingsChanged, this, &TrayController::sync);
    connect(client, &BackendClient::settingsStateChanged, this, &TrayController::sync);
    connect(client, &BackendClient::listeningChanged, this, &TrayController::sync);
    connect(client, &BackendClient::listeningFailed, this, [this](const QString &error) {
        notify(QStringLiteral("Микрофон"), error);
    });
    connect(client, &BackendClient::messagesChanged, this, [this] {
        const auto messages = m_client->messages();
        bool answered = false;
        for (qsizetype i = m_messageCount; i < messages.size(); ++i)
            answered |= messages[i].toMap().value("role").toString() == "assistant";
        m_messageCount = messages.size();
        if (answered && (!m_window->isVisible() || m_window->windowState() == Qt::WindowMinimized))
            notify(QStringLiteral("ScottAI"), QStringLiteral("Ответ готов. Нажмите, чтобы открыть диалог."));
    });
    connect(window, &QWindow::visibleChanged, this, &TrayController::sync);
    connect(window, &QWindow::windowStateChanged, this, [this](Qt::WindowState state) {
        Q_UNUSED(state);
        sync();
    });
    connect(window, &QWindow::visibilityChanged, this, [this](QWindow::Visibility visibility) {
        if (visibility == QWindow::Windowed || visibility == QWindow::Maximized || visibility == QWindow::FullScreen)
            m_restoreVisibility = visibility;
        sync();
    });
    for (const char *name : {"alwaysOnTop", "trayNotifications"}) {
        const int index = window->metaObject()->indexOfProperty(name);
        if (index >= 0 && window->metaObject()->property(index).hasNotifySignal())
            QObject::connect(window, window->metaObject()->property(index).notifySignal(), this,
                metaObject()->method(metaObject()->indexOfSlot("sync()")));
    }
    sync();
}

TrayController::~TrayController() { m_tray->setContextMenu(nullptr); }
void TrayController::persist() { invokeIfPresent(m_window, "persistWorkspace"); }
void TrayController::restoreWindow() { showWindow(); }
void TrayController::showWindow(int tab) {
    if (m_window->property("pendingQuit").toBool()) return;
    if (m_window->property("setupActive").toBool()) { invokeIfPresent(m_window, "raiseSetup"); return; }
    if (tab >= 0) m_window->setProperty("selectedTab", tab);
    // QQuickWindow::show() can retain its previous Minimized visibility even
    // after setWindowState(). Restore through the explicit show methods.
    const auto restoreVisibility = m_restoreVisibility;
    const bool wasMinimized = m_window->visibility() == QWindow::Minimized;
    if (!invokeIfPresent(m_window, "restoreFromTray")) {
        m_window->show();
    }
    if (restoreVisibility == QWindow::FullScreen) m_window->showFullScreen();
    else if (restoreVisibility == QWindow::Maximized) m_window->showMaximized();
    else if (wasMinimized) m_window->showNormal();
    m_window->raise(); m_window->requestActivate();
    sync();
}
void TrayController::notify(const QString &title, const QString &text) {
    if (!m_window->property("trayNotifications").toBool()) return;
    emit notificationRequested(title, text);
    if (!m_testMode && m_tray->isVisible() && QSystemTrayIcon::supportsMessages())
        m_tray->showMessage(title, text, QSystemTrayIcon::Information, 4000);
}
void TrayController::sync() {
    m_status->setText(QStringLiteral("ScottAI · ") + m_client->status());
    m_toggle->setText(m_window->isVisible() && m_window->windowState() != Qt::WindowMinimized
                     ? QStringLiteral("Скрыть окно") : QStringLiteral("Открыть окно"));
    const auto audio = m_client->settings().value("audio").toMap();
    m_quiet->setEnabled(m_client->online() && !m_client->settingsBusy() && m_client->settingsReady().contains("audio") && audio.value("available").toBool());
    m_pause->setEnabled(m_client->online() && m_client->listeningReady() && m_client->listeningAvailable() && !m_client->listeningBusy());
    const QSignalBlocker quiet(m_quiet), pause(m_pause), top(m_top), notifications(m_notifications);
    m_quiet->setChecked(audio.value("settings").toMap().value("quiet").toBool());
    m_pause->setChecked(m_client->listeningReady() && !m_client->listening());
    m_top->setChecked(m_window->property("alwaysOnTop").toBool());
    m_notifications->setChecked(m_window->property("trayNotifications").toBool());
    m_start->setEnabled(!m_window->property("setupActive").toBool() && !m_client->online() && !m_client->starting() && !m_client->ownsBackend());
    m_stop->setEnabled(m_client->ownsBackend() && !m_client->busy() && !m_client->settingsBusy() && !m_client->listeningBusy());
    QString tooltip = QStringLiteral("ScottAI · ") + m_client->status();
    if (m_client->online()) {
        const auto metrics = m_client->metrics();
        if (metrics.contains("cpu") && metrics.contains("ram"))
            tooltip += QStringLiteral("\nCPU %1% · RAM %2%").arg(qRound(metrics.value("cpu").toDouble())).arg(qRound(metrics.value("ram").toDouble()));
        if (m_client->listeningReady()) tooltip += m_client->listening() ? QStringLiteral("\nМикрофон включён") : QStringLiteral("\nГолосовой ассистент на паузе");
    }
    m_tray->setToolTip(tooltip);
}
