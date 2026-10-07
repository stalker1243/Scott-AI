#include "BackendClient.h"
#include "ScottVersion.h"
#include "SetupController.h"
#include "WindowEffects.h"
#include "WindowMotion.h"
#include "../tests/ModelPageChecks.h"
#include "../tests/ChatPageChecks.h"
#include "../tests/VoicePageChecks.h"
#include "TrayController.h"
#include "ProfileAvatar.h"
#include "ProtocolFiles.h"
#include "../tests/BackdropFixture.h"
#include "../tests/WindowLifecycleChecks.h"
#include "../tests/WindowStateChecks.h"
#include <QApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQmlComponent>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QQuickItem>
#include <QSystemTrayIcon>
#include <QMenu>
#include <QSettings>
#include <QStandardPaths>
#include <QCommandLineParser>
#include <QDir>
#include <QElapsedTimer>
#include <QImage>
#include <QTemporaryDir>
#include <QColor>
#include <QFile>
#include <QPointer>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QScreen>
#include <QWidget>
#include <QPalette>
#include <QPainter>
#include <QJSValue>
#include <cstdio>
#include <memory>
#include <cmath>

// ListView delegates belong to the visual tree, not necessarily the QObject tree.
static QQuickItem *visualItem(QQuickItem *parent, const QString &name) {
    if (!parent) return nullptr;
    if (parent->objectName() == name) return parent;
    for (auto *child : parent->childItems())
        if (auto *found = visualItem(child, name)) return found;
    return nullptr;
}
static QVariantMap fixtureMap(const QVariant &value) {
    return value.metaType() == QMetaType::fromType<QJSValue>() ? value.value<QJSValue>().toVariant().toMap() : value.toMap();
}
static QVariantList fixtureList(const QVariant &value) {
    return value.metaType() == QMetaType::fromType<QJSValue>() ? value.value<QJSValue>().toVariant().toList() : value.toList();
}

class Preferences : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantMap initial READ initial CONSTANT)
public:
    explicit Preferences(bool temporary) : m_temporary(temporary), m_settings("ScottAI", "QtPrototype") {}
    QVariantMap initial() const {
        const QStringList legacyStyles{"classic", "glass", "terminal-pro"};
        const QString oldAccent = m_settings.value("accent", "#5588ff").toString();
        return {{"dark", m_temporary ? true : m_settings.value("dark", true)},
                {"accentOverride", m_temporary ? "" : m_settings.value("accentOverride", oldAccent == "#5588ff" ? "" : oldAccent)},
                {"lightIcon", m_temporary ? false : m_settings.value("lightIcon", false)},
                {"hideToTray", m_temporary ? false : m_settings.value("hideToTray", false)},
                {"animations", m_temporary ? true : m_settings.value("animations", true)},
                {"styleId", m_temporary ? "classic" : m_settings.value("styleId", legacyStyles[qBound(0, m_settings.value("surfaceStyle", 0).toInt(), 2)])},
                {"transparencyByStyle", m_temporary ? QVariantMap{} : m_settings.value("transparencyByStyle", QVariantMap{})},
                {"glassFrost", m_temporary ? 40 : qBound(0, m_settings.value("glassFrost", m_settings.value("glassTransparency", 40)).toInt(), 100)},
                {"navigationExpanded", m_temporary ? false : m_settings.value("navigationExpanded", false)},
                {"alwaysOnTop", m_temporary ? false : m_settings.value("alwaysOnTop", false)},
                {"trayNotifications", m_temporary ? true : m_settings.value("trayNotifications", true)}};
    }
    Q_INVOKABLE void save(bool dark, const QString &accentOverride, bool lightIcon, bool hideToTray, bool animations, const QString &styleId, const QVariantMap &transparency, int glassFrost) {
        if (m_temporary) return;
        m_settings.setValue("dark", dark);
        m_settings.setValue("accentOverride", QColor::isValidColorName(accentOverride) ? accentOverride : QString());
        m_settings.setValue("lightIcon", lightIcon);
        m_settings.setValue("hideToTray", hideToTray);
        m_settings.setValue("animations", animations);
        m_settings.setValue("styleId", styleId);
        QVariantMap safeTransparency;
        for (auto it = transparency.begin(); it != transparency.end(); ++it) safeTransparency.insert(it.key(), qBound(0, it.value().toInt(), 100));
        m_settings.setValue("transparencyByStyle", safeTransparency);
        m_settings.setValue("glassFrost", qBound(0, glassFrost, 100));
        emit iconChanged(lightIcon);
    }
    Q_INVOKABLE void saveWorkspace(bool navigationExpanded, bool alwaysOnTop, bool trayNotifications) {
        if (m_temporary) return;
        m_settings.setValue("navigationExpanded", navigationExpanded);
        m_settings.setValue("alwaysOnTop", alwaysOnTop);
        m_settings.setValue("trayNotifications", trayNotifications);
    }
signals:
    void iconChanged(bool light);
private:
    bool m_temporary;
    QSettings m_settings;
};

int main(int argc, char **argv) {
    qInstallMessageHandler([](QtMsgType, const QMessageLogContext &, const QString &message) {
        const auto bytes = message.toUtf8();
        std::fprintf(stderr, "%s\n", bytes.constData());
        QFile log("qt-launcher.log");
        if (log.open(QIODevice::WriteOnly | QIODevice::Append)) { log.write(bytes); log.write("\n"); }
    });
    QElapsedTimer startup; startup.start();
    QApplication app(argc, argv);
    QQuickWindow::setDefaultAlphaBuffer(true);
    // Keep the existing data-directory identity so profile photos survive the release.
    app.setApplicationName("Scott AI · Qt Preview");
    app.setApplicationDisplayName("Scott AI");
    app.setApplicationVersion(SCOTT_APP_VERSION);
    app.setOrganizationName("ScottAI");
    QQuickStyle::setStyle("Basic");
    QCommandLineParser parser;
    parser.addHelpOption();
    parser.addOption({"smoke-test", "Render all pages, save screenshots, then exit. No backend requests or settings writes."});
    parser.addOption({"smoke-glass", "Run only the Glass compositor part of the visual test. No backend requests or settings writes."});
    parser.addOption({"smoke-profile", "Run only the profile visual checks using synthetic data and a temporary photo."});
    parser.addOption({"smoke-actions", "Run only the actions visual checks using synthetic data. No commands are sent."});
    parser.addOption({"smoke-protocols", "Check the protocol editor and results using synthetic data. No commands or schedules are created."});
    parser.addOption({"smoke-window", "Check window opening, closing and interrupted animations using synthetic data."});
    parser.addOption({"smoke-states", "Check animated maximize, full screen, minimize and restore using synthetic data."});
    parser.addOption({"smoke-models", "Check model settings with synthetic providers and tokens."});
    parser.addOption({"smoke-chat", "Check chat history, attachments and generation UI with synthetic data."});
    parser.addOption({"smoke-setup", "Check first-launch preparation UI with synthetic progress."});
    parser.addOption({"smoke-voice", "Check optional voice settings with synthetic data. No synthesis or playback."});
    parser.addOption({"check-backend", "Check real backend health, metrics and a harmless memory question; save the chat screenshot and exit."});
    parser.addOption({"start-backend", "Start the backend if it is not already running."});
    parser.addOption({"tab", "Initial page: home, chat, system, appearance, memory, settings, profile, actions, protocols or models.", "name", "home"});
    parser.addOption({"surface-style", "Preview a style: classic, glass or terminal-pro. Saved selection is used when omitted.", "name"});
    parser.addOption({"python", "Python 3.13 executable for the backend.", "path"});
    parser.addOption({"backend-dir", "Directory containing main.py.", "path", SCOTT_BACKEND_DIR});
    parser.process(app);
    const bool glassOnly = parser.isSet("smoke-glass");
    const bool profileOnly = parser.isSet("smoke-profile");
    const bool actionsOnly = parser.isSet("smoke-actions");
    const bool protocolsOnly = parser.isSet("smoke-protocols");
    const bool windowOnly = parser.isSet("smoke-window");
    const bool statesOnly = parser.isSet("smoke-states");
    const bool modelsOnly = parser.isSet("smoke-models");
    const bool chatOnly = parser.isSet("smoke-chat");
    const bool setupOnly = parser.isSet("smoke-setup");
    const bool voiceOnly = parser.isSet("smoke-voice");
    const bool smoke = parser.isSet("smoke-test") || glassOnly || profileOnly || actionsOnly || protocolsOnly || windowOnly || statesOnly || modelsOnly || chatOnly || setupOnly || voiceOnly;
    const bool integration = parser.isSet("check-backend");
    BackendClient client;
    const auto installedRoot = QDir(QCoreApplication::applicationDirPath()).absoluteFilePath("..");
    const bool installed = !smoke && !integration && QFileInfo::exists(installedRoot + "/runtime/python.exe") && QFileInfo::exists(installedRoot + "/backend/main.py");
    const auto backendDirectory = installed && !parser.isSet("backend-dir") ? installedRoot + "/backend" : parser.value("backend-dir");
    const auto pythonExecutable = installed && !parser.isSet("python") ? installedRoot + "/runtime/python.exe" : parser.value("python");
    client.configureProcess(backendDirectory, pythonExecutable);
    SetupController setup;
    QObject::connect(&setup, &SetupController::ready, &client, &BackendClient::startBackend);
    Preferences prefs(smoke || integration);
    ProtocolFiles protocolFiles;
    ProfileAvatar avatar(QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation) + "/profile", smoke || integration,
                         qEnvironmentVariable("APPDATA") + "/ScottAI");
    WindowEffects windowEffects;
    WindowMotion windowMotion;
    QSystemTrayIcon tray;
    tray.setToolTip("Scott AI " + app.applicationVersion());
    const auto setIcon = [&](bool light) {
        const QIcon icon(light ? ":/brand/scott-light.ico" : ":/brand/scott.ico");
        app.setWindowIcon(icon); tray.setIcon(icon);
    };
    setIcon(prefs.initial().value("lightIcon").toBool());
    QObject::connect(&prefs, &Preferences::iconChanged, &app, setIcon);
    std::unique_ptr<QObject> previewData;
    bool qmlErrors = false;
    QQmlApplicationEngine engine;
    engine.addImageProvider("avatar", new AvatarProvider(&avatar));
    QObject::connect(&engine, &QQmlApplicationEngine::warnings, &app,
                     [&](const QList<QQmlError> &) { qmlErrors = true; });
    if (smoke) {
        QQmlComponent component(&engine, QUrl("qrc:/test/tests/PreviewData.qml"));
        previewData.reset(component.create());
        if (!previewData) {
            for (const auto &error : component.errors()) qWarning().noquote() << error.toString();
            return 7;
        }
    }
    engine.rootContext()->setContextProperty("backend", smoke ? previewData.get() : &client);
    engine.rootContext()->setContextProperty("setupController", setupOnly ? previewData->property("setupPreview").value<QObject *>() : &setup);
    engine.rootContext()->setContextProperty("preferences", &prefs);
    engine.rootContext()->setContextProperty("profileAvatar", &avatar);
    engine.rootContext()->setContextProperty("protocolFiles", &protocolFiles);
    engine.rootContext()->setContextProperty("windowEffects", &windowEffects);
    engine.rootContext()->setContextProperty("windowMotion", &windowMotion);
    engine.rootContext()->setContextProperty("trayAvailable", windowOnly || statesOnly || (!smoke && !integration && QSystemTrayIcon::isSystemTrayAvailable()));
    engine.rootContext()->setContextProperty("qtVersion", qVersion());
    engine.rootContext()->setContextProperty("smokeMode", smoke);
    engine.loadFromModule("Scott.Prototype", "Main");
    if (engine.rootObjects().isEmpty()) return 1;
    auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
    if (!window) return 2;
    windowEffects.attach(window);
    windowMotion.attach(window);
    if (!smoke && !integration) {
        const QStringList tabs{"home", "chat", "system", "appearance", "memory", "settings", "profile", "actions", "protocols", "models"};
        const int tab = tabs.indexOf(parser.value("tab"));
        window->setProperty("selectedTab", tab < 0 ? 0 : tab);
        const QString requestedStyle = parser.value("surface-style");
        if (QStringList{"classic", "glass", "terminal-pro"}.contains(requestedStyle)) window->setProperty("styleId", requestedStyle);
    }
    TrayController trayController(&tray, &client, window, smoke || integration);
    QObject::connect(&windowMotion, &WindowMotion::minimizedRestoreRequested, &trayController, &TrayController::restoreWindow);
    if (modelsOnly) window->setProperty("selectedTab", 9);
    if (chatOnly) { window->setProperty("selectedTab", 1); startChatPageChecks(app, window, previewData.get(), qmlErrors); }
    if (setupOnly) {
        auto *fixture = previewData->property("setupPreview").value<QObject *>();
        auto phase = std::make_shared<int>(0); auto *timer = new QTimer(&app); timer->setInterval(350);
        QObject::connect(timer, &QTimer::timeout, &app, [&, fixture, timer, phase] {
            if (window->opacity() != 1) return;
            auto *button = window->findChild<QObject *>("prepareScottButton");
            if (!fixture || !button || qmlErrors) { qWarning("Setup UI warning or missing controls"); app.exit(43); return; }
            QDir().mkpath("screenshots"); window->grabWindow().save(QString("screenshots/setup-%1.png").arg(*phase));
            if (*phase == 0) { fixture->setProperty("busy", true); fixture->setProperty("progress", 0.65); fixture->setProperty("message", QStringLiteral("Загружаем модели речи…")); }
            else if (*phase == 1) { if (button->property("enabled").toBool()) { app.exit(43); return; } fixture->setProperty("busy", false); fixture->setProperty("error", QStringLiteral("Нет подключения к интернету. Проверьте сеть и повторите попытку.")); }
            else { if (!button->property("enabled").toBool()) { app.exit(43); return; } timer->stop(); qInfo("Setup UI: initial state, progress and retry passed"); app.exit(0); return; }
            ++*phase;
        });
        timer->start();
    }
    QMetaObject::invokeMethod(window, "restoreFromTray");
    if (!smoke) {
        if (!integration) tray.show();
        client.beginPolling();
        if (installed) setup.check(pythonExecutable, backendDirectory);
        else if (parser.isSet("start-backend")) client.startBackend();
    }
    qInfo("Qt window created in %lld ms (backend readiness measured separately)", startup.elapsed());
    bool windowChecksPassed = false;
    bool stateChecksPassed = false;
    bool modelChecksPassed = false;
    bool voiceChecksPassed = false;
    if (windowOnly) runWindowLifecycleChecks(app, window, trayController, windowEffects, qmlErrors, windowChecksPassed);
    if (statesOnly) runWindowStateChecks(app, window, windowMotion, windowEffects, trayController, qmlErrors, stateChecksPassed);
    if (modelsOnly) runModelPageChecks(app, window, previewData.get(), qmlErrors, modelChecksPassed);
    if (voiceOnly) runVoicePageChecks(app, window, previewData.get(), qmlErrors, voiceChecksPassed);
    if (smoke && !windowOnly && !statesOnly && !modelsOnly && !chatOnly && !setupOnly && !voiceOnly) {
        // Capture the actual Qt scene, including each loaded page and a light theme.
        auto step = std::make_shared<int>(protocolsOnly ? 100 : actionsOnly ? 74 : profileOnly ? 67 : glassOnly ? 51 : 0);
        if (protocolsOnly) {
            window->setProperty("animationsEnabled", false); window->setProperty("selectedTab", 8); window->resize(800, 560);
        }
        if (actionsOnly) {
            window->setProperty("animationsEnabled", false);
            window->resize(800, 560); window->setProperty("selectedTab", 7);
        }
        if (profileOnly) {
            window->setProperty("animationsEnabled", false);
            window->resize(800, 560); window->setProperty("selectedTab", 6);
        }
        if (glassOnly) window->setProperty("animationsEnabled", false);
        auto unsettled = std::make_shared<int>(0);
        auto firstMessage = std::make_shared<QPointer<QObject>>();
        auto voiceScroll = std::make_shared<double>(0);
        auto originalSize = std::make_shared<QSize>();
        auto redComposite = std::make_shared<QColor>();
        auto clearContrast = std::make_shared<double>(0);
        auto frostedContrast = std::make_shared<double>(0);
        auto underlay = std::make_shared<BackdropFixture>();
        auto avatarFixture = std::make_shared<QTemporaryDir>();
        QImage avatarImage(256, 256, QImage::Format_RGB32); avatarImage.fill(QColor("#5588ff"));
        { QPainter painter(&avatarImage); painter.fillRect(128, 0, 128, 256, QColor("#53cf9e")); }
        const auto avatarPath = avatarFixture->filePath("avatar.png");
        if (!avatarImage.save(avatarPath)) return 20;
        QQmlComponent glassComponent(&engine, QUrl("qrc:/test/tests/GlassFixture.qml"));
        auto glassProbe = std::shared_ptr<QQuickWindow>(qobject_cast<QQuickWindow *>(glassComponent.createWithInitialProperties({{"hostWindow", QVariant::fromValue(window)}})));
        if (!glassProbe) { qWarning() << glassComponent.errors(); return 7; }
        auto probeEffects = std::make_shared<WindowEffects>();
        probeEffects->attach(glassProbe.get());
        const auto setUnderlayColor = [underlay](const QColor &color) {
            underlay->setColor(color);
        };
        const auto captureComposite = [glassProbe, underlay, probeEffects]() {
            underlay->presentBehind(glassProbe.get());
            QCoreApplication::processEvents();
            if (!underlay->ownsCaptureArea(glassProbe.get())) {
                qWarning("Owned compositor test windows are not in front; capture cancelled");
                return QImage{};
            }
            const QRect screen = glassProbe->screen()->geometry();
            const QRect bounds = glassProbe->geometry();
            // Only our app rectangle is captured; the test widget fills the area behind it.
            auto frame = glassProbe->screen()->grabWindow(0, bounds.x() - screen.x(), bounds.y() - screen.y(), bounds.width(), bounds.height()).toImage();
            const auto scene = glassProbe->grabWindow();
            if (frame.size() != scene.size()) return QImage{};
            // Validate opaque Qt foreground before saving any native capture.
            // A shell overlay may bypass ordinary Win32 window ordering.
            for (int y = 0; y < scene.height(); ++y)
                for (int x = 0; x < scene.width(); ++x) {
                    const auto expected = scene.pixelColor(x, y);
                    if (expected.alpha() != 255) continue;
                    const auto actual = frame.pixelColor(x, y);
                    if (qAbs(expected.red() - actual.red()) > 20 || qAbs(expected.green() - actual.green()) > 20 || qAbs(expected.blue() - actual.blue()) > 20) {
                        qWarning("Compositor probe foreground mismatch at %d,%d: expected=%s actual=%s; capture cancelled", x, y, qPrintable(expected.name()), qPrintable(actual.name())); return QImage{};
                    }
                }
            return frame;
        };
        const auto sample = [](const QImage &frame) {
            return frame.pixelColor(qMin(qRound(240 * frame.devicePixelRatio()), frame.width() / 4), frame.height() - qRound(12 * frame.devicePixelRatio()));
        };
        const auto stripeContrast = [](const QImage &frame) {
            const double scale = frame.devicePixelRatio();
            const int y = frame.height() - qRound(12 * scale);
            double sum = 0, squares = 0;
            int count = 0;
            for (int x = qRound(24 * scale); x < frame.width() - qRound(24 * scale); ++x) {
                const double value = qGray(frame.pixel(x, y));
                sum += value; squares += value * value; ++count;
            }
            return std::sqrt(qMax(0.0, squares / count - std::pow(sum / count, 2)));
        };
        auto timer = new QTimer(&app);
        timer->setInterval(1000);
        QDir().mkpath("screenshots");
        QObject::connect(timer, &QTimer::timeout, &app, [&, step, unsettled, firstMessage, voiceScroll, originalSize, redComposite, clearContrast, frostedContrast, underlay, glassProbe, probeEffects, avatarFixture, avatarPath, setUnderlayColor, captureComposite, sample, stripeContrast, timer, window] {
            const int current = *step;
            if (current > 0) {
                if (window->isVisible()) {
                    auto shot = window->grabWindow();
                    if (shot.isNull() || !shot.save(QString("screenshots/page-%1.png").arg(current - 1))) {
                        app.exit(3); return;
                    }
                }
                const auto *pages = window->findChild<QObject *>("pages");
                const auto *settings = window->findChild<QObject *>("settingsPage");
                const bool sectionUnsettled = window->property("selectedTab").toInt() == 5 &&
                    (!settings || settings->property("sectionTransitioning").toBool() || settings->property("section") != settings->property("displayedSection"));
                if (!pages || pages->property("opacity").toDouble() < 0.99 || qAbs(pages->property("pageOffset").toDouble()) > 0.01 ||
                    window->property("selectedTab") != window->property("displayedTab") || sectionUnsettled) {
                    // A font switch can delay render frames. Allow a bounded wait for
                    // completion, rather than sampling the transition on a fixed frame.
                    if (++*unsettled < 3) return;
                    qWarning("Page transition did not settle at step %d: selected=%d displayed=%d opacity=%g offset=%g", current,
                             window->property("selectedTab").toInt(), window->property("displayedTab").toInt(),
                             pages ? pages->property("opacity").toDouble() : -1,
                             pages ? pages->property("pageOffset").toDouble() : -1);
                    app.exit(8); return;
                }
                *unsettled = 0;
            }
            if (current == 10) {
                auto *list = window->findChild<QObject *>("memoryList");
                if (!list || list->property("count").toInt() != 1) { app.exit(10); return; }
            }
            if (current >= 11 && current <= 14) {
                const int expected[] = {2, 3, 0, 1};
                auto *chat = window->findChild<QObject *>("chatList");
                if (!chat || chat->property("count").toInt() != expected[current - 11]) {
                    qWarning("Chat model did not update"); app.exit(11); return;
                }
                if (current == 11) {
                    *firstMessage = visualItem(window->contentItem(), "chatMessage0");
                    if (firstMessage->isNull()) { qWarning("First chat delegate was not rendered"); app.exit(12); return; }
                }
                if (current == 12 && (firstMessage->isNull() || firstMessage->data() != visualItem(window->contentItem(), "chatMessage0"))) {
                    qWarning("Existing chat delegate was recreated on append"); app.exit(12); return;
                }
            }
            if (current == 36) {
                if (window->property("panelTransparency").toInt() != 70) { app.exit(15); return; }
                window->resize(800, 560);
                window->setProperty("animationsEnabled", true);
                window->setProperty("darkMode", false);
                window->setProperty("styleId", "glass");
                window->setProperty("selectedTab", 5);
                window->findChild<QObject *>("settingsPage")->setProperty("section", 0);
            }
            if (current == 37) {
                auto *firstTab = visualItem(window->contentItem(), "settingsTabsOption0");
                auto *settings = window->findChild<QObject *>("settingsPage");
                if (!firstTab || !settings) { app.exit(16); return; }
                firstTab->forceActiveFocus(Qt::TabFocusReason);
                const auto key = [window](int code) {
                    QKeyEvent press(QEvent::KeyPress, code, Qt::NoModifier);
                    QCoreApplication::sendEvent(window, &press);
                    QKeyEvent release(QEvent::KeyRelease, code, Qt::NoModifier);
                    QCoreApplication::sendEvent(window, &release);
                };
                for (const auto &entry : {qMakePair(Qt::Key_End, 2), qMakePair(Qt::Key_Home, 0), qMakePair(Qt::Key_Right, 1), qMakePair(Qt::Key_Left, 0)}) {
                    key(entry.first);
                    if (settings->property("section").toInt() != entry.second) { qWarning("Settings keyboard navigation failed"); app.exit(16); return; }
                }
                auto *popup = window->findChild<QObject *>("outputDevicePopup");
                if (!popup) { app.exit(16); return; }
                QMetaObject::invokeMethod(popup, "open");
            }
            if (current == 38) {
                QMetaObject::invokeMethod(window->findChild<QObject *>("outputDevicePopup"), "close");
                auto *scroll = window->findChild<QObject *>("settingsScroll");
                auto *flick = scroll->property("contentItem").value<QObject *>();
                if (!flick) { app.exit(16); return; }
                *voiceScroll = qMin(260.0, qMax(0.0, flick->property("contentHeight").toDouble() - flick->property("height").toDouble()));
                if (*voiceScroll < 50) { qWarning("Settings scrolling was not exercised"); app.exit(16); return; }
                flick->setProperty("contentY", *voiceScroll);
                auto *settings = window->findChild<QObject *>("settingsPage");
                settings->setProperty("volumeDraft", 52);
                settings->setProperty("volumeDirty", true);
                settings->setProperty("section", 1);
                QTimer::singleShot(35, &app, [settings] { settings->setProperty("section", 2); });
                QTimer::singleShot(140, &app, [settings] { settings->setProperty("section", 0); });
                QTimer::singleShot(255, &app, [settings] { settings->setProperty("section", 1); });
            }
            if (current == 39) {
                auto *settings = window->findChild<QObject *>("settingsPage");
                if (settings->property("displayedSection").toInt() != 1) { app.exit(16); return; }
                settings->setProperty("section", 0);
            }
            if (current == 40) {
                auto *settings = window->findChild<QObject *>("settingsPage");
                auto *scroll = window->findChild<QObject *>("settingsScroll");
                auto *flick = scroll->property("contentItem").value<QObject *>();
                if (!flick || qAbs(flick->property("contentY").toDouble() - *voiceScroll) > 1 ||
                    settings->property("volumeDraft").toInt() != 52 || !settings->property("volumeDirty").toBool()) {
                    qWarning("Settings scroll position or volume draft was lost: scroll=%g expected=%g draft=%d dirty=%d",
                             flick ? flick->property("contentY").toDouble() : -1, *voiceScroll,
                             settings->property("volumeDraft").toInt(), settings->property("volumeDirty").toBool()); app.exit(16); return;
                }
                settings->setProperty("section", 1);
                QTimer::singleShot(40, &app, [&, settings, window] {
                    window->setProperty("animationsEnabled", false);
                    const auto *sections = window->findChild<QObject *>("settingsSections");
                    if (settings->property("sectionTransitioning").toBool() || settings->property("displayedSection").toInt() != 1 ||
                        sections->property("opacity").toDouble() != 1 || sections->property("sectionOffset").toDouble() != 0) {
                        qWarning("Disabling motion did not finish the settings transition"); app.exit(16); return;
                    }
                    settings->setProperty("section", 2);
                    if (settings->property("displayedSection").toInt() != 2 || settings->property("sectionTransitioning").toBool()) { app.exit(16); }
                });
            }
            if (current == 41) {
                window->setProperty("animationsEnabled", true);
                window->findChild<QObject *>("settingsPage")->setProperty("section", 0);
                QTimer::singleShot(40, &app, [window] { window->hide(); });
                QTimer::singleShot(100, &app, [window] { window->show(); });
            }
            if (current == 42) {
                window->resize(800, 560);
                window->setProperty("styleId", "terminal-pro");
                window->setProperty("darkMode", true);
            }
            if (current == 43) previewData->setProperty("settingsBusy", true);
            if (current == 44) {
                const auto *activity = window->findChild<QObject *>("settingsActivity");
                const auto *quiet = window->findChild<QObject *>("quietSwitch");
                if (!activity || activity->property("reveal").toDouble() < 0.99 || !quiet || quiet->property("enabled").toBool()) { app.exit(16); return; }
                previewData->setProperty("settingsBusy", false);
                previewData->setProperty("settingsError", QStringLiteral("Не удалось применить изменение. Повторите попытку после восстановления соединения."));
                window->setProperty("styleId", "classic");
                window->setProperty("darkMode", false);
                window->findChild<QObject *>("settingsPage")->setProperty("section", 1);
            }
            if (current == 45) {
                previewData->setProperty("settingsError", "");
                previewData->setProperty("settingsNotice", QStringLiteral("Настройки сохранены."));
                window->findChild<QObject *>("settingsPage")->setProperty("section", 2);
            }
            if (current == 46) QMetaObject::invokeMethod(window->findChild<QObject *>("resetAppearanceDialog"), "open");
            if (current == 47) {
                QMetaObject::invokeMethod(window->findChild<QObject *>("resetAppearanceDialog"), "close");
                if (previewData->property("settingsWrites").toInt() != 0) { qWarning("Visual changes unexpectedly wrote settings"); app.exit(16); return; }
                window->setProperty("animationsEnabled", false);
                window->setProperty("styleId", "classic");
                window->setProperty("darkMode", true);
                window->setProperty("transparencyByStyle", QVariantMap{});
                for (int tab : {4, 2, 5, 3, 1, 0}) {
                    auto *button = visualItem(window->contentItem(), QString("navTab%1").arg(tab));
                    if (!button || !QMetaObject::invokeMethod(button, "clicked") || window->property("displayedTab").toInt() != tab) { qWarning("Grouped navigation opened the wrong page"); app.exit(17); return; }
                }
                window->setProperty("selectedTab", 4); // Memory at the minimum window size.
            }
            if (current == 48) {
                const auto *autoMemory = visualItem(window->contentItem(), "autoMemorySwitch");
                const auto *draftCard = visualItem(window->contentItem(), "memoryDraftCard");
                const auto *addMemory = visualItem(window->contentItem(), "addMemory");
                if (!autoMemory || !autoMemory->property("checked").toBool() ||
                    autoMemory->mapToScene(QPointF(autoMemory->width(), 0)).x() > window->width() ||
                    !draftCard || !addMemory || addMemory->mapToScene(QPointF(0, addMemory->height())).y() >
                    draftCard->mapToScene(QPointF(0, draftCard->height() - 12)).y()) {
                    qWarning("Memory controls do not fit the compact window"); app.exit(16); return;
                }
                if (!QQuickWindow::hasDefaultAlphaBuffer() || !(window->flags() & Qt::FramelessWindowHint) || sample(window->grabWindow()).alpha() != 255) { app.exit(17); return; }
                *originalSize = window->size();
                auto *maximize = visualItem(window->contentItem(), "windowMaximize");
                if (!maximize || !QMetaObject::invokeMethod(maximize, "clicked")) { qWarning("Custom maximize button was not found in the visual tree"); app.exit(17); return; }
            }
            if (current == 49) {
                if (window->visibility() != QWindow::Maximized) { qWarning("Custom maximize button failed"); app.exit(17); return; }
                QMetaObject::invokeMethod(visualItem(window->contentItem(), "windowMaximize"), "clicked");
            }
            if (current == 50) {
                if (window->visibility() != QWindow::Windowed || window->size() != *originalSize) {
                    qWarning("Custom restore button failed: visibility=%d size=%dx%d expected=%dx%d", int(window->visibility()),
                        window->width(), window->height(), originalSize->width(), originalSize->height()); app.exit(17); return;
                }
                QMetaObject::invokeMethod(visualItem(window->contentItem(), "windowMinimize"), "clicked");
                QTimer::singleShot(150, &app, [&, window] {
                    if (window->visibility() != QWindow::Minimized) { qWarning("Custom minimize button failed"); app.exit(17); return; }
                    window->showNormal();
                });
            }
            if (current == 51) {
                window->setProperty("styleId", "glass");
                window->setProperty("selectedTab", 3);
                auto *slider = window->findChild<QObject *>("glassFrostSlider");
                slider->setProperty("value", 65);
                QMetaObject::invokeMethod(slider, "moved");
                auto *scroll = window->findChild<QObject *>("appearanceScroll");
                auto *flick = scroll->property("contentItem").value<QObject *>();
                auto *card = window->findChild<QObject *>("glassFrostCard");
                flick->setProperty("contentY", card->property("y"));
            }
            if (current == 52) {
                if (window->property("glassFrost").toInt() != 65 || window->opacity() != 1 || sample(window->grabWindow()).alpha() <= 0 || sample(window->grabWindow()).alpha() >= 255) {
                    qWarning("Glass did not render an alpha background while keeping content opacity"); app.exit(18); return;
                }
                const QRect available = window->screen()->availableGeometry();
                window->setGeometry(available.x() + 16, available.y() + 16, 960, 680);
                window->setProperty("selectedTab", 0);
                window->setProperty("glassFrost", 0);
                if (windowEffects.active()) { qWarning("Clear Glass retained a native blur"); app.exit(18); return; }
                glassProbe->setPosition(available.x() + 16, available.y() + 16);
                setUnderlayColor(QColor("#a04c56"));
                underlay->presentBehind(glassProbe.get());
            }
            if (current == 53) {
                const auto nativeFrame = captureComposite();
                if (nativeFrame.isNull() || !nativeFrame.save("screenshots/glass-desktop-red.png")) { app.exit(18); return; }
                *redComposite = sample(nativeFrame);
                const auto rgba = sample(glassProbe->grabWindow());
                const QColor behind("#a04c56");
                const auto expected = [&](int front, int back) { return qRound(front * rgba.alphaF() + back * (1 - rgba.alphaF())); };
                if (qAbs(redComposite->red() - expected(rgba.red(), behind.red())) > 15 ||
                    qAbs(redComposite->green() - expected(rgba.green(), behind.green())) > 15 ||
                    qAbs(redComposite->blue() - expected(rgba.blue(), behind.blue())) > 15) {
                    qWarning("Native Glass composition differs from alpha blending: actual=%s front=%s alpha=%d", qPrintable(redComposite->name()), qPrintable(rgba.name()), rgba.alpha()); app.exit(18); return;
                }
                setUnderlayColor(QColor("#34678e"));
            }
            if (current == 54) {
                const auto nativeFrame = captureComposite();
                if (nativeFrame.isNull() || !nativeFrame.save("screenshots/glass-desktop-blue.png")) { app.exit(18); return; }
                const auto blueComposite = sample(nativeFrame);
                if (qAbs(blueComposite.red() - redComposite->red()) < 70) { qWarning("Changing the real window behind Glass did not change its visible background"); app.exit(18); return; }
                underlay->setPattern();
            }
            if (current == 55) {
                const auto clearFrame = captureComposite();
                if (!clearFrame.save("screenshots/glass-clear.png")) { app.exit(18); return; }
                *clearContrast = stripeContrast(clearFrame);
                if (*clearContrast < 65) { qWarning("Clear Glass obscured the test pattern: contrast=%g", *clearContrast); app.exit(18); return; }
                window->setProperty("glassFrost", 40);
            }
            if (current == 56) {
                const auto frame = captureComposite();
                if (!frame.save("screenshots/glass-frosted-40.png")) { app.exit(18); return; }
                *frostedContrast = stripeContrast(frame);
                const double scale = frame.devicePixelRatio();
                const auto left = frame.pixelColor(qRound(32 * scale), frame.height() / 2);
                const auto right = frame.pixelColor(frame.width() - qRound(32 * scale), frame.height() / 2);
                qInfo("Desktop Glass: native=%d active=%d clear contrast=%g frosted contrast=%g colors=%s/%s", windowEffects.available(), windowEffects.active(), *clearContrast, *frostedContrast, qPrintable(left.name()), qPrintable(right.name()));
#ifdef Q_OS_WIN
                // Supported Windows must blur the pattern beyond alpha blending alone.
                if (windowEffects.available() && (!windowEffects.active() || *frostedContrast > *clearContrast * 0.35 ||
                    left.red() - right.red() < 8 || right.blue() - left.blue() < 8)) {
                    qWarning("Acrylic did not blur the actual desktop backdrop"); app.exit(18); return;
                }
#endif
                window->setProperty("glassFrost", 100);
            }
            if (current == 57) {
                const auto frame = captureComposite();
                if (!frame.save("screenshots/glass-frosted-100.png")) { app.exit(18); return; }
                if (window->opacity() != 1 || sample(window->grabWindow()).alpha() < 200 ||
                    stripeContrast(frame) > *frostedContrast + 2) {
                    qWarning("Increasing frosted density did not obscure the background while keeping content opacity"); app.exit(18); return;
                }
                window->setProperty("glassFrost", 40);
                window->setProperty("darkMode", false);
                setUnderlayColor(QColor("#617f91"));
            }
            if (current == 58) {
                if (!captureComposite().save("screenshots/glass-desktop-light.png")) { app.exit(18); return; }
                window->setProperty("darkMode", true);
            }
            if (current == 59) {
                if (!captureComposite().save("screenshots/glass-desktop-dark.png")) { app.exit(18); return; }
                underlay->hide();
                glassProbe->hide();
                window->hide(); window->showNormal();
            }
            if (current == 60) {
                if (windowEffects.available() && !windowEffects.active()) { qWarning("Glass lost its backdrop after restoring the window"); app.exit(18); return; }
                window->setProperty("styleId", "classic");
                if (windowEffects.active()) { qWarning("Classic retained the Glass backdrop"); app.exit(18); return; }
                window->setProperty("styleId", "terminal-pro");
                if (windowEffects.active()) { qWarning("Terminal retained the Glass backdrop"); app.exit(18); return; }
                if (glassOnly) { timer->stop(); app.exit(qmlErrors ? 4 : 0); return; }
                window->resize(800, 560); window->setProperty("selectedTab", 0);
                window->setProperty("navigationExpanded", false);
            }
            if (current == 61) {
                auto *rail = visualItem(window->contentItem(), "navigationRail");
                auto *toggle = visualItem(window->contentItem(), "navigationToggle");
                if (!rail || qAbs(rail->width() - 64) > 0.5 || !toggle) { qWarning("Compact rail has wrong geometry"); app.exit(19); return; }
                QMetaObject::invokeMethod(toggle, "clicked");
            }
            if (current == 62) {
                auto *rail = visualItem(window->contentItem(), "navigationRail");
                if (!rail || qAbs(rail->width() - 164) > 0.5) { qWarning("Expanded rail has wrong geometry"); app.exit(19); return; }
                window->setProperty("alwaysOnTop", true);
                if (!(window->flags() & Qt::WindowStaysOnTopHint)) { qWarning("Topmost preference did not update window flags"); app.exit(19); return; }
                window->setProperty("navigationExpanded", false);
                const auto area = windowEffects.workArea();
                window->setPosition(area.x() + 3, area.y() + 3);
                QMetaObject::invokeMethod(window, "snapToScreenEdge");
                if (window->position() != area.topLeft() + QPoint(8, 8)) { qWarning("Edge docking missed the work area: position=%d,%d target=%d,%d visibility=%d visible=%d motion=%d", window->x(), window->y(), area.x() + 8, area.y() + 8, int(window->visibility()), window->isVisible(), window->property("animationsEnabled").toBool()); app.exit(19); return; }
            }
            if (current == 63) {
                window->setProperty("alwaysOnTop", false);
                QMetaObject::invokeMethod(window, "hideToBackground");
                if (window->isVisible()) { qWarning("Disabled motion did not hide immediately"); app.exit(19); return; }
                QMetaObject::invokeMethod(window, "restoreFromTray");
                if (!window->isVisible() || window->property("revealProgress").toDouble() != 1) { qWarning("Tray restore left the scene hidden"); app.exit(19); return; }
                window->setProperty("animationsEnabled", true);
                QMetaObject::invokeMethod(window, "hideToBackground");
                if (!window->property("pendingHide").toBool()) { qWarning("Animated hide did not start"); app.exit(19); return; }
            }
            if (current == 64) {
                if (window->isVisible() || window->property("pendingHide").toBool()) { qWarning("Animated hide did not finish"); app.exit(19); return; }
                QMetaObject::invokeMethod(window, "restoreFromTray");
            }
            if (current == 65) {
                if (!window->isVisible() || window->property("revealProgress").toDouble() < 0.99) { qWarning("Animated restore did not finish"); app.exit(19); return; }
                const auto area = windowEffects.workArea();
                window->setPosition(area.x() + 3, area.y() + 3);
                QMetaObject::invokeMethod(window, "snapToScreenEdge");
            }
            if (current == 66) {
                if (window->position() != windowEffects.workArea().topLeft() + QPoint(8, 8)) { qWarning("Animated docking did not finish"); app.exit(19); return; }
                window->setProperty("animationsEnabled", false); window->setProperty("selectedTab", 6);
            }
            if (current == 67) {
                auto *profile = window->findChild<QObject *>("profilePage");
                if (!profile || profile->property("nameDraft").toString() != QStringLiteral("Тестовый профиль")) { qWarning("Profile was not loaded"); app.exit(20); return; }
                profile->setProperty("nameDraft", QStringLiteral("Черновик")); profile->setProperty("dirty", true);
                window->setProperty("selectedTab", 1); window->setProperty("selectedTab", 6);
                window->setProperty("styleId", "glass");
            }
            if (current == 68) {
                auto *profile = window->findChild<QObject *>("profilePage");
                auto data = fixtureMap(previewData->property("profile")); data["name"] = QStringLiteral("Другой профиль");
                previewData->setProperty("profile", data);
                if (!profile->property("dirty").toBool() || profile->property("nameDraft").toString() != QStringLiteral("Черновик")) { qWarning("Profile refresh overwrote a draft"); app.exit(20); return; }
                if (!avatar.loadFile(avatarPath)) { app.exit(20); return; }
                avatar.setCrop(2, 25, -20);
                QMetaObject::invokeMethod(window->findChild<QObject *>("avatarCropDialog"), "open");
            }
            if (current == 69) {
                auto *dialog = window->findChild<QObject *>("avatarCropDialog");
                if (!dialog || !dialog->property("visible").toBool() || dialog->property("height").toDouble() > window->height() - 24) { qWarning("Photo crop dialog does not fit compact window"); app.exit(20); return; }
                QMetaObject::invokeMethod(dialog, "close");
                previewData->setProperty("profileBusy", true);
            }
            if (current == 70) {
                auto *save = visualItem(window->contentItem(), "saveProfile");
                if (!save || save->isEnabled()) { qWarning("Profile save is enabled during loading"); app.exit(20); return; }
                previewData->setProperty("profileBusy", false);
                previewData->setProperty("profileError", QStringLiteral("Пример ошибки сохранения. Черновик остаётся в окне."));
                window->setProperty("darkMode", false);
            }
            if (current == 71) {
                auto *profile = window->findChild<QObject *>("profilePage");
                if (profile->property("nameDraft").toString() != QStringLiteral("Черновик")) { app.exit(20); return; }
                previewData->setProperty("profileError", "");
                QMetaObject::invokeMethod(visualItem(window->contentItem(), "saveProfile"), "clicked");
                if (previewData->property("profileWrites").toInt() != 1) { qWarning("Profile save did not send exactly one request"); app.exit(20); return; }
                auto data = fixtureMap(previewData->property("profile")); data["name"] = QStringLiteral("Подтверждено");
                previewData->setProperty("profile", data); QMetaObject::invokeMethod(previewData.get(), "profileSaved");
                window->setProperty("styleId", "terminal-pro");
            }
            if (current == 72) {
                auto *profile = window->findChild<QObject *>("profilePage");
                if (profile->property("nameDraft").toString() != QStringLiteral("Подтверждено") || profile->property("dirty").toBool() || avatar.dirty()) { qWarning("Profile did not show confirmed data"); app.exit(20); return; }
                profile->setProperty("aboutDraft", QString(301, QChar('x')));
                QTimer::singleShot(0, &app, [window] {
                    auto *scroll = window->findChild<QObject *>("profileScroll");
                    auto *flick = scroll->property("contentItem").value<QObject *>();
                    flick->setProperty("contentY", qMax(0.0, flick->property("contentHeight").toDouble() - flick->property("height").toDouble()));
                });
            }
            if (current == 73) {
                auto *save = visualItem(window->contentItem(), "saveProfile");
                if (!save || save->isEnabled() || previewData->property("profileWrites").toInt() != 1) { qWarning("Profile length limit failed"); app.exit(20); return; }
                if (profileOnly) { timer->stop(); app.exit(qmlErrors ? 4 : 0); return; }
                window->setProperty("selectedTab", 7); window->setProperty("styleId", "classic"); window->setProperty("darkMode", true);
            }
            if (current >= 74 && current <= 84) {
                auto *actions = window->findChild<QObject *>("actionsPage");
                auto *search = window->findChild<QObject *>("actionsSearch");
                auto *composer = window->findChild<QObject *>("chatComposer");
                auto *category = window->findChild<QObject *>("actionsCategory");
                const auto fail = [&](const char *message) { qWarning("Actions: %s at step %d", message, current); app.exit(21); };
                if (!actions || !search || !composer || !category) { fail("page controls missing"); return; }
                if (current == 74) {
                    auto *nav = visualItem(window->contentItem(), "navTab7");
                    if (actions->property("resultCount").toInt() != 4 || !nav || !nav->isVisible() || nav->mapToItem(window->contentItem(), QPointF()).y() < 0) { fail("catalog or navigation missing"); return; }
                    search->setProperty("text", QStringLiteral("МИКРОФОНОВ"));
                }
                if (current == 75) {
                    auto *reason = visualItem(window->contentItem(), "actionReason_voice");
                    if (actions->property("resultCount").toInt() != 1 || !reason || !reason->isVisible() || visualItem(window->contentItem(), "actionExample_voice_0")) { fail("unavailable action or search incorrect"); return; }
                    search->setProperty("text", QStringLiteral("компьютер"));
                    composer->setProperty("text", QStringLiteral("Мой черновик"));
                }
                if (current == 76) {
                    auto *example = visualItem(window->contentItem(), "actionExample_power_0");
                    if (actions->property("resultCount").toInt() != 1 || !example || !example->isEnabled()) { fail("example is missing"); return; }
                    QMetaObject::invokeMethod(example, "clicked");
                    if (window->property("selectedTab").toInt() != 1 || composer->property("text").toString() != QStringLiteral("Мой черновик\nвыключи компьютер") || previewData->property("messagesSent").toInt()) { fail("example replaced draft or sent a command"); return; }
                    window->setProperty("selectedTab", 7); search->setProperty("text", "");
                    category->setProperty("currentIndex", 3); QMetaObject::invokeMethod(category, "activated", Q_ARG(int, 3));
                }
                if (current == 77) {
                    if (actions->property("resultCount").toInt() != 1 || actions->property("activeGroup").toString() != QStringLiteral("Компьютер")) { fail("category filter incorrect"); return; }
                    previewData->setProperty("online", false);
                    auto *example = visualItem(window->contentItem(), "actionExample_power_0");
                    auto *refresh = visualItem(window->contentItem(), "refreshActions");
                    if (!example || example->isEnabled() || !refresh || refresh->isEnabled()) { fail("offline controls enabled"); return; }
                    window->setProperty("navigationExpanded", true);
                }
                if (current == 78) {
                    previewData->setProperty("online", true); previewData->setProperty("abilitiesReady", false);
                    previewData->setProperty("abilitiesError", QStringLiteral("Не удалось обновить действия. Показан последний список."));
                    auto *example = visualItem(window->contentItem(), "actionExample_power_0");
                    if (!example || example->isEnabled()) { fail("stale example enabled"); return; }
                    window->setProperty("styleId", "glass");
                }
                if (current == 79) {
                    previewData->setProperty("abilitiesError", ""); previewData->setProperty("abilitiesReady", true); previewData->setProperty("abilitiesBusy", true);
                    actions->setProperty("activeGroup", ""); category->setProperty("currentIndex", 0); actions->setProperty("readyOnly", true);
                    window->setProperty("darkMode", false);
                }
                if (current == 80) {
                    if (actions->property("resultCount").toInt() != 3 || visualItem(window->contentItem(), "refreshActions")->isEnabled()) { fail("available filter or loading guard incorrect"); return; }
                    previewData->setProperty("abilitiesBusy", false); search->setProperty("text", "no-matching-example");
                    window->setProperty("styleId", "terminal-pro"); window->setProperty("darkMode", true);
                }
                if (current == 81) {
                    if (actions->property("resultCount").toInt() || !visualItem(window->contentItem(), "actionsEmpty")->isVisible()) { fail("empty search missing"); return; }
                    search->setProperty("text", ""); actions->setProperty("readyOnly", false);
                }
                if (current == 82) {
                    QMetaObject::invokeMethod(window->findChild<QObject *>("actionsList"), "positionViewAtEnd");
                }
                if (current == 83) {
                    auto *last = visualItem(window->contentItem(), "actionExample_reminders_0");
                    const QPointF point = last ? last->mapToItem(window->contentItem(), QPointF()) : QPointF();
                    if (!last || !last->isEnabled() || point.y() < 0 || point.y() + last->height() > window->height() || point.x() + last->width() > window->width()) { fail("last example does not fit compact window"); return; }
                    previewData->setProperty("abilities", QVariantList{}); previewData->setProperty("abilitiesTotal", 0); previewData->setProperty("abilitiesReadyCount", 0);
                }
                if (current == 84) {
                    if (actions->property("resultCount").toInt() || previewData->property("messagesSent").toInt()) { fail("empty catalog or read-only browsing incorrect"); return; }
                    timer->stop(); app.exit(qmlErrors ? 4 : 0); return;
                }
            }
            if (current >= 100 && current <= 118) {
                auto *page = window->findChild<QObject *>("protocolsPage");
                auto *search = window->findChild<QObject *>("protocolSearch");
                auto *save = visualItem(window->contentItem(), "saveProtocol");
                const auto fail = [&](const char *message) { qWarning("Protocols: %s at step %d", message, current); app.exit(22); };
                const auto draft = [page]() { QVariant value; QMetaObject::invokeMethod(page, "payload", Q_RETURN_ARG(QVariant, value)); return fixtureMap(value); };
                if (!page || !search || !save) { fail("controls missing"); return; }
                if (current == 100) {
                    auto *disabled = visualItem(window->contentItem(), "runProtocol_off-protocol");
                    if (page->property("resultCount").toInt() != 2 || !disabled || disabled->isEnabled() || previewData->property("protocolWrites").toInt() || previewData->property("protocolRuns").toInt()) { fail("catalog state incorrect"); return; }
                    search->setProperty("text", QStringLiteral("за работу"));
                }
                if (current == 101) {
                    if (page->property("resultCount").toInt() != 1) { fail("search does not match phrases"); return; }
                    search->setProperty("text", "");
                    const auto record = fixtureList(previewData->property("protocols")).first();
                    QMetaObject::invokeMethod(page, "loadDraft", Q_ARG(QVariant, record), Q_ARG(QVariant, false));
                }
                if (current == 102) {
                    if (!page->property("validDraft").toBool() || page->property("dirty").toBool() || draft().value("steps").toList().first().toMap().value("pause").toInt() != 2) { fail("editor lost saved settings"); return; }
                    page->setProperty("nameDraft", QStringLiteral("Черновик")); page->setProperty("dirty", true);
                    window->setProperty("selectedTab", 1); window->setProperty("selectedTab", 8);
                    window->setProperty("styleId", "glass"); window->setProperty("navigationExpanded", true);
                    previewData->setProperty("protocolsBusy", true);
                }
                if (current == 103) {
                    if (save->isEnabled() || page->property("nameDraft").toString() != QStringLiteral("Черновик")) { fail("draft or busy guard incorrect"); return; }
                    previewData->setProperty("protocolsBusy", false); previewData->setProperty("protocolsError", QStringLiteral("Не удалось сохранить. Черновик остаётся в редакторе."));
                    QMetaObject::invokeMethod(page, "cloneStep", Q_ARG(QVariant, 0)); page->setProperty("nameDraft", "");
                }
                if (current == 104) {
                    if (save->isEnabled() || page->property("validDraft").toBool() || draft().value("steps").toList().size() != 3) { fail("name validation or clone failed"); return; }
                    page->setProperty("nameDraft", QStringLiteral("Черновик")); page->setProperty("repeatDraft", 3); page->setProperty("stopDraft", false);
                    page->setProperty("scheduleDraft", QStringLiteral("пн, ср, пт в 18:00")); window->setProperty("darkMode", false);
                    QMetaObject::invokeMethod(window->findChild<QObject *>("protocolBulkDialog"), "open");
                }
                if (current == 105) {
                    window->findChild<QObject *>("protocolBulkText")->setProperty("text", QStringLiteral("  открой документы \n\nнапомни через час сделать перерыв"));
                    QMetaObject::invokeMethod(visualItem(window->contentItem(), "protocolBulkAdd"), "clicked");
                    if (draft().value("steps").toList().size() != 5) { fail("bulk paste incorrect"); return; }
                    QMetaObject::invokeMethod(window->findChild<QObject *>("protocolActionsDialog"), "open");
                }
                if (current == 106) {
                    auto *dialog = window->findChild<QObject *>("protocolActionsDialog");
                    auto *content = qobject_cast<QQuickItem *>(dialog->property("contentItem").value<QObject *>());
                    auto *example = visualItem(content, "actionExample_open_app_1");
                    if (!example || dialog->property("height").toDouble() > window->height() - 24) { fail("action picker does not fit"); return; }
                    QMetaObject::invokeMethod(example, "clicked");
                    if (draft().value("steps").toList().size() != 6 || previewData->property("protocolRuns").toInt()) { fail("action picker executed a command"); return; }
                    previewData->setProperty("protocolsError", "");
                }
                if (current == 107) {
                    if (!save->isEnabled()) { fail("valid draft cannot be saved"); return; }
                    QMetaObject::invokeMethod(save, "clicked");
                    const auto sent = fixtureMap(previewData->property("protocolDraftSent"));
                    if (previewData->property("protocolWrites").toInt() != 1 || sent.value("repeat_count").toInt() != 3 || sent.value("stop_on_error").toBool() || sent.value("steps").toList().size() != 6) { fail("save payload incorrect"); return; }
                    previewData->setProperty("protocolsError", QStringLiteral("Пример ошибки записи. Изменения сохранены в черновике."));
                }
                if (current == 108) {
                    if (!page->property("dirty").toBool() || page->property("nameDraft").toString() != QStringLiteral("Черновик")) { fail("failed save erased draft"); return; }
                    auto list = fixtureList(previewData->property("protocols")); auto record = list.first().toMap();
                    const auto sent = fixtureMap(previewData->property("protocolDraftSent"));
                    for (auto it = sent.begin(); it != sent.end(); ++it) if (it.key() != "schedule") record[it.key()] = it.value();
                    record["name"] = QStringLiteral("Подтверждено"); record["schedule_text"] = sent.value("schedule"); list[0] = record;
                    previewData->setProperty("protocols", list); previewData->setProperty("protocolsError", "");
                    QMetaObject::invokeMethod(previewData.get(), "protocolSaved", Q_ARG(QVariant, record));
                }
                if (current == 109) {
                    if (page->property("dirty").toBool() || page->property("nameDraft").toString() != QStringLiteral("Подтверждено")) { fail("confirmed record not displayed"); return; }
                    page->setProperty("pendingDelete", fixtureList(previewData->property("protocols")).first());
                    QMetaObject::invokeMethod(window->findChild<QObject *>("confirmDeleteProtocol"), "open");
                }
                if (current == 110) {
                    QMetaObject::invokeMethod(window->findChild<QObject *>("confirmDeleteProtocol"), "close");
                    if (previewData->property("protocolDeletes").toInt()) { fail("delete ran without confirmation"); return; }
                    previewData->setProperty("online", false); page->setProperty("dirty", true);
                    if (save->isEnabled()) { fail("offline save enabled"); return; }
                    window->setProperty("styleId", "terminal-pro"); window->setProperty("darkMode", true);
                    QTimer::singleShot(0, &app, [window] { auto *scroll = window->findChild<QObject *>("protocolEditorScroll"); auto *flick = scroll->property("contentItem").value<QObject *>(); flick->setProperty("contentY", qMax(0.0, flick->property("contentHeight").toDouble() - flick->property("height").toDouble())); });
                }
                if (current == 111) {
                    previewData->setProperty("online", true); page->setProperty("section", 0);
                    auto *run = visualItem(window->contentItem(), "runProtocol_demo-protocol");
                    if (!run || !run->isEnabled()) { fail("run button missing"); return; }
                    QMetaObject::invokeMethod(run, "clicked");
                }
                if (current == 112) {
                    auto *cancel = visualItem(window->contentItem(), "cancelProtocol");
                    if (!previewData->property("protocolRunning").toBool() || !cancel || !cancel->isEnabled() || previewData->property("protocolRuns").toInt() != 1) { fail("run state incorrect"); return; }
                    QMetaObject::invokeMethod(cancel, "clicked");
                }
                if (current == 113) {
                    if (previewData->property("protocolRunning").toBool() || previewData->property("protocolCancels").toInt() != 1) { fail("cancel failed"); return; }
                    QMetaObject::invokeMethod(window->findChild<QObject *>("confirmDeleteProtocol"), "open");
                    QMetaObject::invokeMethod(visualItem(window->contentItem(), "deleteProtocolConfirmed"), "clicked");
                    if (previewData->property("protocolDeletes").toInt() != 1) { fail("confirmed delete missing"); return; }
                    auto imported = fixtureMap(previewData->property("protocolDraftSent")); imported["enabled"] = false; imported["schedule"] = "";
                    emit protocolFiles.imported(imported);
                }
                if (current == 114) {
                    if (!page->property("editId").toString().isEmpty() || page->property("enabledDraft").toBool() || !page->property("scheduleDraft").toString().isEmpty() || !page->property("dirty").toBool()) { fail("import restored automatic execution"); return; }
                    page->setProperty("nameDraft", QString(101, QChar('x')));
                }
                if (current == 115) {
                    if (save->isEnabled() || previewData->property("protocolWrites").toInt() != 1) { fail("length limit or unintended write"); return; }
                    previewData->setProperty("protocols", QVariantList{}); page->setProperty("section", 0); page->setProperty("dirty", false);
                    search->setProperty("text", ""); page->setProperty("listFilter", "all");
                }
                if (current == 116) {
                    auto *button = visualItem(window->contentItem(), "protocolEmptyTemplate0");
                    if (!button || !button->isVisible()) { fail("empty catalog template missing"); return; }
                    const auto position = button->mapToItem(window->contentItem(), QPointF(button->width() / 2, button->height() / 2));
                    const auto global = window->mapToGlobal(position.toPoint());
                    QMouseEvent press(QEvent::MouseButtonPress, position, global, Qt::LeftButton, Qt::LeftButton, Qt::NoModifier);
                    QMouseEvent release(QEvent::MouseButtonRelease, position, global, Qt::LeftButton, Qt::NoButton, Qt::NoModifier);
                    // Dispatch to our own QQuickWindow; never click the desktop foreground.
                    QApplication::sendEvent(window, &press); QApplication::sendEvent(window, &release);
                }
                if (current == 117) {
                    if (page->property("section").toInt() != 1 || page->property("nameDraft").toString() != QStringLiteral("Рабочий день") || draft().value("steps").toList().size() != 3) { fail("template click was intercepted"); return; }
                    QMetaObject::invokeMethod(visualItem(window->contentItem(), "newProtocol"), "clicked");
                }
                if (current == 118) {
                    auto *dialog = window->findChild<QObject *>("discardProtocolDraft");
                    if (!dialog->property("visible").toBool() || page->property("nameDraft").toString() != QStringLiteral("Рабочий день") || previewData->property("protocolWrites").toInt() != 1) { fail("draft replacement lacked confirmation"); return; }
                    QMetaObject::invokeMethod(dialog, "close");
                    timer->stop(); app.exit(qmlErrors ? 4 : 0); return;
                }
            }
            if (current < 10) window->setProperty("selectedTab", current < 5 ? current : current == 5 ? 0 : 4);
            if (current == 5) window->setProperty("darkMode", false);
            if (current == 6) window->setProperty("animationsEnabled", false);
            if (current == 7) {
                window->resize(800, 560);
                window->setProperty("darkMode", true);
                window->setProperty("animationsEnabled", true);
                for (int tab : {0, 2, 1, 4}) window->setProperty("selectedTab", tab);
            }
            if (current == 8) {
                auto *memory = window->findChild<QObject *>("memoryPage");
                auto *dialog = window->findChild<QObject *>("confirmForget");
                if (!memory || !dialog) { app.exit(9); return; }
                memory->setProperty("pendingText", QStringLiteral("Пример записи для проверки подтверждения. Настоящая память не изменяется."));
                QMetaObject::invokeMethod(dialog, "open");
            }
            if (current == 9) {
                auto *dialog = window->findChild<QObject *>("confirmForget");
                QMetaObject::invokeMethod(dialog, "close");
                auto *search = window->findChild<QObject *>("memorySearch");
                if (!search) { app.exit(9); return; }
                search->setProperty("text", QStringLiteral("C++"));
            }
            if (current == 10) window->setProperty("selectedTab", 1);
            if (current == 11 || current == 13) QMetaObject::invokeMethod(previewData.get(), "appendDemoMessage");
            if (current == 12) QMetaObject::invokeMethod(previewData.get(), "clearChat");
            if (current == 14) {
                window->setProperty("selectedTab", 2);
                QTimer::singleShot(40, &app, [&, window] {
                    window->setProperty("animationsEnabled", false);
                    const auto *pages = window->findChild<QObject *>("pages");
                    if (!pages || pages->property("opacity").toDouble() != 1 || pages->property("pageOffset").toDouble() != 0 ||
                        window->property("displayedTab").toInt() != 2) {
                        qWarning("Disabling motion did not finish the transition immediately"); app.exit(13);
                    }
                });
            }
            if (current == 15) {
                window->setProperty("animationsEnabled", true);
                window->setProperty("selectedTab", 0);
                QTimer::singleShot(35, &app, [window] { window->setProperty("selectedTab", 3); });
                QTimer::singleShot(150, &app, [window] { window->setProperty("selectedTab", 4); });
            }
            if (current == 16) {
                window->setProperty("selectedTab", 0);
                QTimer::singleShot(40, &app, [window] { window->hide(); });
                QTimer::singleShot(100, &app, [window] { window->show(); });
            }
            if (current == 17) {
                window->setProperty("darkMode", false);
                window->setProperty("selectedTab", 3);
            }
            if (current == 18) {
                QMetaObject::invokeMethod(visualItem(window->contentItem(), "styleTile-glass"), "clicked");
                if (window->property("styleId").toString() != "glass") { app.exit(14); return; }
                window->setProperty("selectedTab", 0);
            }
            if (current == 19) {
                window->setProperty("darkMode", true);
                window->setProperty("selectedTab", 4);
                window->findChild<QObject *>("memorySearch")->setProperty("text", "");
                auto *draft = qobject_cast<QQuickItem *>(window->findChild<QObject *>("memoryDraft"));
                QTimer::singleShot(350, &app, [draft] { draft->forceActiveFocus(); });
            }
            if (current == 20) QMetaObject::invokeMethod(window->findChild<QObject *>("memoryKindPopup"), "open");
            if (current == 21) {
                QMetaObject::invokeMethod(window->findChild<QObject *>("memoryKindPopup"), "close");
                previewData->setProperty("memoryError", QStringLiteral("Проверочный пример ошибки. Повторите загрузку, когда соединение восстановится."));
            }
            if (current == 22) {
                QMetaObject::invokeMethod(visualItem(window->contentItem(), "styleTile-terminal-pro"), "clicked");
                if (window->property("styleId").toString() != "terminal-pro") { app.exit(14); return; }
                window->setProperty("selectedTab", 0);
            }
            if (current == 23) {
                window->setProperty("darkMode", false);
                window->setProperty("selectedTab", 3);
            }
            if (current == 24) {
                window->setProperty("animationsEnabled", false);
                window->setProperty("styleId", "classic");
                window->setProperty("selectedTab", 4);
                previewData->setProperty("memoryError", "");
                previewData->setProperty("memoryNotice", QStringLiteral("Проверочный пример: запись сохранена."));
            }
            if (current == 25) {
                window->setProperty("animationsEnabled", true);
                window->setProperty("darkMode", true);
                window->setProperty("styleId", "terminal-pro");
                window->setProperty("selectedTab", 1);
            }
            if (current == 26) window->setProperty("selectedTab", 4);
            if (current == 27) {
                window->resize(1240, 820);
                window->setProperty("styleId", "glass");
                window->setProperty("selectedTab", 0);
            }
            if (current == 28) window->setProperty("selectedTab", 3);
            if (current == 29) {
                window->setProperty("selectedTab", 5);
                window->setProperty("transparencyByStyle", QVariantMap{{"glass", 60}});
            }
            if (current == 30) window->findChild<QObject *>("settingsPage")->setProperty("section", 1);
            if (current == 31) window->findChild<QObject *>("settingsPage")->setProperty("section", 2);
            if (current == 32) {
                window->resize(800, 560);
                window->setProperty("styleId", "terminal-pro");
                window->findChild<QObject *>("settingsPage")->setProperty("section", 0);
            }
            if (current == 33) {
                window->setProperty("styleId", "glass");
                window->setProperty("transparencyByStyle", QVariantMap{{"glass", 0}, {"classic", 100}});
                if (window->property("panelTransparency").toInt() != 0) { app.exit(15); return; }
                window->setProperty("selectedTab", 0);
            }
            if (current == 34) {
                window->setProperty("animationsEnabled", false);
                window->setProperty("styleId", "classic");
                if (window->property("panelTransparency").toInt() != 100) { app.exit(15); return; }
                if (window->property("surface").value<QColor>().alpha() != 0) { app.exit(15); return; }
            }
            if (current == 35) {
                window->setProperty("selectedTab", 3);
                auto *slider = window->findChild<QObject *>("transparencySlider");
                slider->setProperty("value", 70);
                QMetaObject::invokeMethod(slider, "moved");
                auto *scroll = window->findChild<QObject *>("appearanceScroll");
                auto *flick = scroll->property("contentItem").value<QObject *>();
                auto *card = window->findChild<QObject *>("transparencyCard");
                if (!flick || !card) { app.exit(15); return; }
                flick->setProperty("contentY", qMin(card->property("y").toDouble(), qMax(0.0, flick->property("contentHeight").toDouble() - flick->property("height").toDouble())));
            }
            ++*step;
        });
        timer->start();
    }
    if (integration) {
        auto sent = std::make_shared<bool>(false);
        auto finished = std::make_shared<bool>(false);
        QObject::connect(&client, &BackendClient::stateChanged, &app, [&, sent, finished] {
            if (client.online() && !*sent) {
                *sent = true;
                client.sendMessage(QStringLiteral("Сколько свободной памяти?"));
            } else if (*sent && !*finished && !client.busy() && !client.messages().isEmpty()) {
                *finished = true;
                const bool success = client.messages().last().toMap().value("role") == "assistant";
                window->setProperty("selectedTab", 1);
                QTimer::singleShot(700, &app, [&, success] {
                    QDir().mkpath("screenshots");
                    const bool saved = window->grabWindow().save("screenshots/live-chat.png");
                    qInfo("Live backend: online=%d, metrics=%d, answer=%d", client.online(), !client.metrics().isEmpty(), success);
                    app.exit(success && saved && !qmlErrors && !client.metrics().isEmpty() ? 0 : 5);
                });
            }
        });
        QTimer::singleShot(parser.isSet("start-backend") ? 90000 : 20000, &app, [&app] { app.exit(6); });
    }
    const int result = app.exec();
    return windowOnly && !windowChecksPassed ? 22 : statesOnly && !stateChecksPassed ? 23 : modelsOnly && !modelChecksPassed ? 24 : voiceOnly && !voiceChecksPassed ? 25 : result;
}
#include "main.moc"
