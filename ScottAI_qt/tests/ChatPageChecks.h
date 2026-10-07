#pragma once
#include <QQuickWindow>
#include <QQuickItem>
#include <QTimer>
#include <QApplication>
#include <QJSValue>
#include <QDir>

inline void startChatPageChecks(QApplication &app, QQuickWindow *window, QObject *preview, bool &qmlErrors) {
    auto phase = std::make_shared<int>(0);
    auto *timer = new QTimer(&app); timer->setInterval(300);
    QObject::connect(timer, &QTimer::timeout, &app, [&, window, preview, timer, phase] {
        const auto fail = [&](const char *message) { qWarning("Chat UI: %s at phase %d", message, *phase); timer->stop(); app.exit(42); };
        const auto shot = [&](const QString &name) { QDir().mkpath("screenshots"); return window->grabWindow().save("screenshots/chat-" + name + ".png"); };
        if (window->opacity() != 1) return;
        auto *composer = window->findChild<QObject *>("chatComposer");
        auto *history = window->findChild<QObject *>("chatHistoryPopup");
        auto *rename = window->findChild<QObject *>("renameChatDialog");
        auto *confirmation = window->findChild<QObject *>("chatDeleteDialog");
        if (qmlErrors || !composer || !history || !rename || !confirmation) { fail("QML warning or missing controls"); return; }
        if (*phase == 0) {
            window->setProperty("animationsEnabled", false); window->setProperty("selectedTab", 1); window->resize(800, 560);
        } else if (*phase == 1) {
            if (!shot("classic")) { fail("screenshot"); return; }
            QMetaObject::invokeMethod(history, "open");
        } else if (*phase == 2) {
            if (!history->property("visible").toBool() || !shot("history")) { fail("history"); return; }
            if (history->property("width").toInt() > 340 || history->property("height").toInt() < 450) { fail("history should be a compact side panel"); return; }
            QMetaObject::invokeMethod(history, "close"); QMetaObject::invokeMethod(rename, "open");
        } else if (*phase == 3) {
            if (!shot("rename")) { fail("rename"); return; }
            QMetaObject::invokeMethod(rename, "close"); QMetaObject::invokeMethod(confirmation, "open");
        } else if (*phase == 4) {
            if (!shot("clear-confirmation")) { fail("confirmation"); return; }
            QMetaObject::invokeMethod(confirmation, "close");
            preview->setProperty("attachments", QVariantList{QVariantMap{{"name", "notes.txt"}, {"mime", "text/plain"}, {"size", 40}, {"url", ""}}});
            composer->setProperty("text", QStringLiteral("Объясни содержимое файла")); window->setProperty("styleId", "glass");
        } else if (*phase == 5) {
            if (!shot("attachment-glass")) { fail("attachment"); return; }
            preview->setProperty("attachments", QVariantList{}); composer->setProperty("generateImage", true);
            composer->setProperty("text", QStringLiteral("Город на рассвете, мягкий свет")); window->setProperty("styleId", "terminal-pro");
        } else if (*phase == 6) {
            if (!shot("generation-terminal")) { fail("generation"); return; }
            preview->setProperty("busy", true);
        } else if (*phase == 7) {
            if (composer->property("text").toString().isEmpty() || !shot("progress")) { fail("pending draft lost"); return; }
            preview->setProperty("busy", false); preview->setProperty("chatCapabilities", QVariantMap{{"capabilities", QVariantMap{{"text", true}, {"documents", true}, {"images", false}, {"image_generation", false}}}});
        } else if (*phase == 8) {
            if (composer->property("generateImage").toBool() || preview->property("messagesSent").toInt() || qmlErrors) { fail("unsupported generation or unsolicited request"); return; }
            preview->setProperty("messages", QVariantList{QVariantMap{{"role", "assistant"}, {"text", QStringLiteral("Изображение готово.")}, {"model", "Demo Image"}, {"attachments", QVariantList{QVariantMap{{"name", "Scott-image.png"}, {"mime", "image/png"}, {"url", "qrc:/brand/scott-logo.png"}}}}}});
            window->setProperty("styleId", "classic");
        } else if (*phase == 9) {
            if (!shot("generated-image") || qmlErrors) { fail("generated image preview"); return; }
            preview->setProperty("chatCapabilities", QVariantMap{{"enabled", true}, {"model", "Demo Text"}, {"capabilities", QVariantMap{{"known", true}, {"text", true}, {"documents", true}, {"images", false}, {"video", false}, {"image_generation", false}}}});
            auto *photo = window->findChild<QObject *>("attachPhotoButton");
            if (!photo || !photo->property("enabled").toBool()) { fail("unavailable photo must explain itself"); return; }
            QMetaObject::invokeMethod(photo, "clicked");
        } else if (*phase == 10) {
            auto *notice = window->findChild<QObject *>("chatCapabilityNotice");
            if (!notice || !notice->property("text").toString().contains(QStringLiteral("не поддерживает")) || !shot("photo-warning") || preview->property("messagesSent").toInt()) { fail("photo warning"); return; }
            auto *generate = window->findChild<QObject *>("generateImageButton");
            if (!generate || !generate->property("visible").toBool()) { fail("unavailable generation must explain itself"); return; }
            QMetaObject::invokeMethod(generate, "clicked");
        } else if (*phase == 11) {
            auto *notice = window->findChild<QObject *>("chatCapabilityNotice");
            if (composer->property("generateImage").toBool() || !notice->property("text").toString().contains(QStringLiteral("генерация")) || !shot("generation-warning")) { fail("generation warning"); return; }
            preview->setProperty("chatCapabilities", QVariantMap{{"enabled", true}, {"model", "Unknown ID"}, {"capabilities", QVariantMap{{"known", false}}}});
            window->setProperty("chatWarningFeature", "video"); window->setProperty("styleId", "terminal-pro");
        } else if (*phase == 12) {
            auto *notice = window->findChild<QObject *>("chatCapabilityNotice");
            if (!notice->property("text").toString().contains(QStringLiteral("не подтверждена")) || !shot("unknown-warning")) { fail("unknown must not be called unsupported"); return; }
            window->setProperty("chatWarningFeature", "");
        } else if (*phase == 13) {
            if (!window->property("chatCapabilityWarning").toString().isEmpty()) { fail("unknown model must not warn before a feature is clicked"); return; }
            auto *file = window->findChild<QObject *>("attachFileButton");
            if (!file || !file->property("enabled").toBool()) { fail("file action must explain missing support"); return; }
            QMetaObject::invokeMethod(file, "clicked");
        } else if (*phase == 14) {
            auto *notice = window->findChild<QObject *>("chatCapabilityNotice");
            if (!notice->property("text").toString().contains(QStringLiteral("файлами")) || preview->property("attachmentDialogsOpened").toInt()) { fail("unsupported file should warn before opening picker"); return; }
            if (composer->property("text").toString().isEmpty() || !shot("file-warning")) { fail("warning must preserve draft"); return; }
            preview->setProperty("chatCapabilities", QVariantMap{{"enabled", true}, {"model", "Demo Vision"}, {"capabilities", QVariantMap{{"known", true}, {"text", true}, {"documents", true}, {"images", true}}}});
            QMetaObject::invokeMethod(window->findChild<QObject *>("attachFileButton"), "clicked");
        } else if (*phase == 15) {
            if (!window->property("chatCapabilityWarning").toString().isEmpty() || preview->property("attachmentDialogsOpened").toInt() != 1) { fail("supported file must open picker without warning"); return; }
            QMetaObject::invokeMethod(history, "open");
            auto *search = window->findChild<QObject *>("chatHistorySearch");
            if (!search) { fail("history search missing"); return; }
            search->setProperty("text", "no-such-chat");
        } else if (*phase == 16) {
            auto *list = window->findChild<QObject *>("chatHistoryList");
            if (list->property("count").toInt() != 0 || composer->property("text").toString().isEmpty() || !shot("history-search")) { fail("history search or draft lost"); return; }
            QMetaObject::invokeMethod(history, "close");
            window->setProperty("chatWarningFeature", "images");
            preview->setProperty("chatCapabilities", QVariantMap{{"enabled", true}, {"model", "Demo Text"}, {"capabilities", QVariantMap{{"known", true}, {"images", false}}}});
            QMetaObject::invokeMethod(window->findChild<QObject *>("chatWarningModelsButton"), "clicked");
        } else if (*phase == 17) {
            if (window->property("selectedTab").toInt() != 9 || qmlErrors) { fail("choose model navigation"); return; }
            timer->stop(); qInfo("Chat UI: history, media, generation and model capability warnings passed"); app.exit(0); return;
        }
        ++*phase;
    });
    timer->start();
}
