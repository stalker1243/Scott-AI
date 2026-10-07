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
    QVariantMap voices{{"current", "scott-voice"}, {"scott_profile", "natural"}, {"scott_streaming", false}, {"scott_acceleration", false}, {"scott_buffer", "immediate"},
        {"scott_buffers", QVariantList{QVariantMap{{"id", "immediate"}, {"title", QStringLiteral("Сразу")}},
                                      QVariantMap{{"id", "2s"}, {"title", QStringLiteral("2 секунды звука")}},
                                      QVariantMap{{"id", "4s"}, {"title", QStringLiteral("4 секунды звука")}},
                                      QVariantMap{{"id", "complete"}, {"title", QStringLiteral("Вся фраза")}}}},
        {"voices", QVariantList{QVariantMap{{"id", "scott-voice"}, {"label", "Scott Voice"}, {"local", true}, {"available", true}, {"streaming_available", true}, {"acceleration_available", true}},
                               QVariantMap{{"id", "demo"}, {"label", "Евгений"}, {"local", true}}}},
        {"scott_profiles", QVariantList{QVariantMap{{"id", "natural"}, {"title", QStringLiteral("Исходный — уверенный и сдержанный")}},
                                       QVariantMap{{"id", "restrained"}, {"title", QStringLiteral("Сдержанный — лёгкая цифровая окраска")}},
                                       QVariantMap{{"id", "scott"}, {"title", QStringLiteral("Scott — умеренная цифровая окраска")}},
                                       QVariantMap{{"id", "digital"}, {"title", QStringLiteral("Цифровой — выраженный машинный тембр")}}}}};
    settings["voices"] = voices;
    preview->setProperty("settings", settings);
    QDir().mkpath("screenshots/voice");
    auto phase = std::make_shared<int>(0);
    auto *timer = new QTimer(&app);
    timer->setInterval(350);
    const auto fail = [&](const char *message) { qWarning("Voice UI: %s", message); app.exit(25); };
    QObject::connect(timer, &QTimer::timeout, &app, [&, timer, phase, page, preview, window, fail] {
        auto *choice = window->findChild<QObject *>("voiceCharacter");
        auto *scroll = window->findChild<QObject *>("settingsScroll");
        if (!choice || !scroll || qmlErrors) { fail("missing control or QML error"); return; }
        auto *flick = scroll->property("contentItem").value<QObject *>();
        const auto screenshot = [&](const char *name) {
            if (!window->grabWindow().save(QString("screenshots/voice/%1.png").arg(name))) fail("screenshot failed");
        };
        if (*phase == 0) {
            auto *warm = window->findChild<QObject *>("warmScottVoice");
            auto *release = window->findChild<QObject *>("releaseScottVoice");
            if (!warm || !release || !warm->property("visible").toBool() || !warm->property("enabled").toBool() || release->property("visible").toBool()) { fail("manual preparation controls invalid"); return; }
            QMetaObject::invokeMethod(warm, "clicked");
            if (!page->property("scottSelected").toBool() || choice->property("count").toInt() != 4 || choice->property("currentIndex").toInt() != 0) { fail("profile catalog not displayed"); return; }
            auto *stream = window->findChild<QObject *>("scottStreaming");
            if (!stream || !stream->property("visible").toBool() || !stream->property("enabled").toBool() || stream->property("checked").toBool()) { fail("streaming default or availability incorrect"); return; }
            stream->setProperty("checked", true);
            QMetaObject::invokeMethod(stream, "toggled");
            if (flick) flick->setProperty("contentY", qMax(0.0, flick->property("contentHeight").toDouble()-flick->property("height").toDouble()));
        } else if (*phase == 1) {
            auto *release = window->findChild<QObject *>("releaseScottVoice");
            if (!release->property("visible").toBool() || !release->property("enabled").toBool()) { fail("loaded model cannot be released"); return; }
            QMetaObject::invokeMethod(release, "clicked");
            auto *acceleration = window->findChild<QObject *>("scottAcceleration");
            if (!acceleration || !acceleration->property("visible").toBool() || !acceleration->property("enabled").toBool() || acceleration->property("checked").toBool()) { fail("acceleration default or availability incorrect"); return; }
            acceleration->setProperty("checked", true);
            QMetaObject::invokeMethod(acceleration, "toggled");
            if (preview->property("settingsLastGroup").toString() != "voiceAcceleration") { fail("acceleration choice did not reach client"); return; }
            auto *buffer = window->findChild<QObject *>("scottBuffer");
            if (!buffer || !buffer->property("visible").toBool() || !buffer->property("enabled").toBool() || buffer->property("count").toInt() != 4 || buffer->property("currentIndex").toInt() != 0) { fail("buffer default or availability incorrect"); return; }
            buffer->setProperty("currentIndex", 2);
            QMetaObject::invokeMethod(buffer, "activated", Q_ARG(int, 2));
            if (preview->property("settingsLastGroup").toString() != "voiceBuffer") { fail("buffer choice did not reach client"); return; }
            if (flick) flick->setProperty("contentY", qMax(0.0, flick->property("contentHeight").toDouble()-flick->property("height").toDouble()));
            screenshot("classic");
            choice->setProperty("currentIndex", 2);
            QMetaObject::invokeMethod(choice, "activated", Q_ARG(int, 2));
        } else if (*phase == 2) {
            if (!window->findChild<QObject *>("warmScottVoice")->property("visible").toBool()) { fail("prepare unavailable after release"); return; }
            if (preview->property("settingsLastGroup").toString() != "voiceProfile" || choice->property("currentIndex").toInt() != 2) { fail("profile selection did not reach client"); return; }
            window->setProperty("styleId", "glass");
            preview->setProperty("settingsBusy", true);
            preview->setProperty("settingsNotice", QStringLiteral("Готовим Scott Voice. Первая новая фраза может занять до минуты…"));
        } else if (*phase == 3) {
            if (choice->property("enabled").toBool()) { fail("profile enabled during preview"); return; }
            if (window->findChild<QObject *>("scottBuffer")->property("enabled").toBool()) { fail("buffer enabled during preview"); return; }
            if (flick) flick->setProperty("contentY", qMax(0.0, flick->property("contentHeight").toDouble()-flick->property("height").toDouble()));
            screenshot("glass-preparing");
            preview->setProperty("settingsBusy", false);
            preview->setProperty("settingsNotice", "");
            window->resize(800, 560); window->setProperty("styleId", "terminal-pro");
        } else if (*phase == 4) {
            if (flick) flick->setProperty("contentY", qMax(0.0, flick->property("contentHeight").toDouble()-flick->property("height").toDouble()));
        } else if (*phase == 5) {
            screenshot("terminal-compact");
            QMetaObject::invokeMethod(preview, "prepareScottVoice", Q_ARG(QVariant, false));
        } else if (*phase == 6) {
            auto *cancel = window->findChild<QObject *>("cancelScottVoice");
            auto *install = window->findChild<QObject *>("installScottVoice");
            if (!cancel || !cancel->property("visible").toBool() || !cancel->property("enabled").toBool() || install->property("enabled").toBool()) { fail("installation controls invalid"); return; }
            screenshot("terminal-installing");
            QMetaObject::invokeMethod(cancel, "clicked");
        } else if (*phase == 7) {
            auto *install = window->findChild<QObject *>("installScottVoice");
            if (preview->property("voiceInstall").value<QJSValue>().toVariant().toMap().value("state").toString() != "cancelled" || !install->property("enabled").toBool()) { fail("retry unavailable after cancellation"); return; }
            screenshot("terminal-retry");
            preview->setProperty("online", false);
        } else if (*phase == 8) {
            if (choice->property("enabled").toBool()) { fail("offline selection enabled"); return; }
            if (window->findChild<QObject *>("scottBuffer")->property("enabled").toBool()) { fail("offline buffer enabled"); return; }
            if (window->findChild<QObject *>("installScottVoice")->property("enabled").toBool()) { fail("offline installation enabled"); return; }
            passed = true; timer->stop();
            qInfo("Voice UI: optional catalog, profiles, preparing, offline and three styles passed");
            app.exit(0);
        }
        ++*phase;
    });
    QTimer::singleShot(10000, &app, [fail] { fail("timeout"); });
    timer->start();
}
