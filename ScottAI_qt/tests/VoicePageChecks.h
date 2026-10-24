#pragma once
#include <QApplication>
#include <QQuickWindow>
#include <QJSValue>
#include <QDir>
#include <QTimer>
#include <memory>

inline void runVoicePageChecks(QApplication &app, QQuickWindow *window, QObject *preview,
                              bool &qmlErrors, bool &passed) {
    window->setProperty("animationsEnabled", false);
    window->setProperty("selectedTab", 5);
    window->resize(1000, 720);
    auto *page = window->findChild<QObject *>("settingsPage");
    page->setProperty("section", 0);
    auto settings = preview->property("settings").value<QJSValue>().toVariant().toMap();
    const QVariantMap voices{{"current", "scott-voice"}, {"scott_profile", "scott"},
        {"scott_streaming", true}, {"scott_acceleration", true}, {"scott_buffer", "4s"},
        {"voices", QVariantList{QVariantMap{{"id", "scott-voice"}, {"label", "Scott Voice"}, {"local", true}, {"available", true}}}}};
    settings["voices"] = voices; preview->setProperty("settings", settings);
    QDir().mkpath("screenshots/voice");
    auto phase = std::make_shared<int>(0);
    auto *timer = new QTimer(&app); timer->setInterval(350);
    const auto fail = [&](const char *message) { qWarning("Voice UI: %s", message); app.exit(25); };
    QObject::connect(timer, &QTimer::timeout, &app, [&, timer, phase, page, voices, preview, window, fail] {
        auto *scroll = window->findChild<QObject *>("settingsScroll");
        if (!scroll || qmlErrors) { fail("missing scroll or QML error"); return; }
        for (const auto *name : {"voiceChoice", "voiceCharacter", "voiceInputMode", "liveApiToken", "saveLiveToken",
                                 "scottStreaming", "scottAcceleration", "scottBuffer", "adaptiveSpeechHint"}) {
            if (window->findChild<QObject *>(name)) { fail("retired control remains in object tree"); return; }
        }
        const auto stored = preview->property("settings");
        const auto current = stored.metaType() == QMetaType::fromType<QJSValue>() ? stored.value<QJSValue>().toVariant().toMap() : stored.toMap();
        if (current.value("voices").toMap() != voices || preview->property("settingsWrites").toInt() != 0) {
            qWarning() << "Voice fixture map type:" << stored.metaType().name() << "writes:" << preview->property("settingsWrites");
            fail("opening settings changed accepted voice preferences"); return;
        }
        auto *flick = scroll->property("contentItem").value<QObject *>();
        const auto screenshot = [&](const char *name) {
            if (flick) flick->setProperty("contentY", 0);
            if (!window->grabWindow().save(QString("screenshots/voice/%1.png").arg(name))) fail("screenshot failed");
        };
        auto *warm = window->findChild<QObject *>("warmScottVoice");
        auto *release = window->findChild<QObject *>("releaseScottVoice");
        auto *previewButton = window->findChild<QObject *>("previewScottVoice");
        if (!warm || !release || !previewButton) { fail("voice controls missing"); return; }
        if (*phase == 0) {
            auto *storage = window->findChild<QObject *>("scottVoiceStorageInfo");
            if (!window->findChild<QObject *>("scottVoiceName") || !storage || !storage->property("visible").toBool() ||
                !storage->property("text").toString().contains(QStringLiteral("3–4 ГиБ"))) { fail("voice identity or capacity hint missing"); return; }
            if (!warm->property("visible").toBool() || !warm->property("enabled").toBool() || release->property("visible").toBool()) { fail("preparation controls invalid"); return; }
            QMetaObject::invokeMethod(warm, "clicked");
        } else if (*phase == 1) {
            if (!release->property("visible").toBool() || !release->property("enabled").toBool()) { fail("loaded model cannot be released"); return; }
            QMetaObject::invokeMethod(release, "clicked"); screenshot("classic");
            window->setProperty("styleId", "glass"); preview->setProperty("settingsBusy", true);
        } else if (*phase == 2) {
            if (warm->property("enabled").toBool() || previewButton->property("enabled").toBool()) { fail("busy controls enabled"); return; }
            screenshot("glass-preparing"); preview->setProperty("settingsBusy", false);
            window->resize(800, 560); window->setProperty("styleId", "terminal-pro");
        } else if (*phase == 3) {
            screenshot("terminal-compact"); QMetaObject::invokeMethod(preview, "prepareScottVoice", Q_ARG(QVariant, false));
        } else if (*phase == 4) {
            auto *cancel = window->findChild<QObject *>("cancelScottVoice");
            auto *install = window->findChild<QObject *>("installScottVoice");
            if (!cancel || !cancel->property("visible").toBool() || !cancel->property("enabled").toBool() || install->property("enabled").toBool()) { fail("installation controls invalid"); return; }
            screenshot("terminal-installing"); QMetaObject::invokeMethod(cancel, "clicked");
        } else if (*phase == 5) {
            auto *install = window->findChild<QObject *>("installScottVoice");
            if (preview->property("voiceInstall").value<QJSValue>().toVariant().toMap().value("state").toString() != "cancelled" || !install->property("enabled").toBool()) { fail("retry unavailable after cancellation"); return; }
            screenshot("terminal-retry"); preview->setProperty("online", false);
        } else if (*phase == 6) {
            if (warm->property("enabled").toBool() || previewButton->property("enabled").toBool() ||
                window->findChild<QObject *>("installScottVoice")->property("enabled").toBool()) { fail("offline controls enabled"); return; }
            passed = true; timer->stop();
            qInfo("Voice UI: simple controls, unchanged preferences, preparation, installation, offline state and three styles passed");
            app.exit(0);
        }
        ++*phase;
    });
    QTimer::singleShot(10000, &app, [fail] { fail("timeout"); }); timer->start();
}
