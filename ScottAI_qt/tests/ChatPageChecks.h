#pragma once
#include <QQuickWindow>
#include <QQuickItem>
#include <QTimer>
#include <QApplication>
#include <QJSValue>
#include <QDir>
#include <QClipboard>
#include <QMimeData>

inline QQuickItem *chatVisual(QQuickItem *item, const QString &name) {
    if (item->objectName() == name) return item;
    for (auto *child : item->childItems()) if (auto *found = chatVisual(child, name)) return found;
    return nullptr;
}

inline void startChatPageChecks(QApplication &app, QQuickWindow *window, QObject *preview, bool &qmlErrors, bool layoutOnly = false) {
    if (!layoutOnly) {
    auto savedClipboard = std::make_shared<QMimeData>();
    if (const auto *original = app.clipboard()->mimeData())
        for (const auto &format : original->formats()) savedClipboard->setData(format, original->data(format));
    QObject::connect(&app, &QCoreApplication::aboutToQuit, &app, [savedClipboard] {
        auto *restored = new QMimeData;
        for (const auto &format : savedClipboard->formats()) restored->setData(format, savedClipboard->data(format));
        QApplication::clipboard()->setMimeData(restored);
    });
    }
    auto phase = std::make_shared<int>(0);
    auto *timer = new QTimer(&app); timer->setInterval(300);
    QObject::connect(timer, &QTimer::timeout, &app, [&, window, preview, timer, phase, layoutOnly] {
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
            auto *first = chatVisual(window->contentItem(), "chatMessage0");
            auto *second = chatVisual(window->contentItem(), "chatMessage1");
            if (!first || !second || first->y() + first->height() > second->y() + 0.5) {
                if (first && second) qWarning("Chat geometry: first y=%g height=%g second y=%g", first->y(), first->height(), second->y());
                if (auto *list = chatVisual(window->contentItem(), "chatList")) {
                    QMetaObject::invokeMethod(list, "forceLayout");
                    if (first && second) qWarning("After forced layout: first height=%g second y=%g", first->height(), second->y());
                }
                fail("message bubbles overlap"); return;
            }
            auto *userCard=chatVisual(window->contentItem(),"chatMessageCard0");
            auto *scottCard=chatVisual(window->contentItem(),"chatMessageCard1");
            if(!userCard||!scottCard||qAbs(userCard->width()-scottCard->width())>1||qAbs(userCard->x()-scottCard->x())>1){fail("user and Scott cards must share the reading column");return;}
            if (!shot("classic")) { fail("screenshot"); return; }
            if (layoutOnly) { timer->stop(); qInfo("Chat layout: initial message geometry passed"); app.exit(0); return; }
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
            preview->setProperty("attachments", QVariantList{});
            composer->setProperty("text", QStringLiteral("Нарисуй город на рассвете, мягкий свет")); window->setProperty("styleId", "terminal-pro");
        } else if (*phase == 6) {
            if (!shot("generation-terminal")) { fail("generation"); return; }
            preview->setProperty("busy", true);
        } else if (*phase == 7) {
            if (composer->property("text").toString().isEmpty() || !shot("progress")) { fail("pending draft lost"); return; }
            preview->setProperty("busy", false); preview->setProperty("chatCapabilities", QVariantMap{{"capabilities", QVariantMap{{"text", true}, {"documents", true}, {"images", false}, {"image_generation", false}}}});
        } else if (*phase == 8) {
            if (window->findChild<QObject *>("generateImageButton") || window->findChild<QObject *>("chatBrowserButton") || preview->property("messagesSent").toInt() || qmlErrors) { fail("function toggles or unsolicited request"); return; }
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
            window->setProperty("chatWarningFeature", "image_generation");
        } else if (*phase == 11) {
            auto *notice = window->findChild<QObject *>("chatCapabilityNotice");
            if (!notice->property("text").toString().contains(QStringLiteral("генерация")) || !shot("generation-warning")) { fail("generation warning"); return; }
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
            auto *modelLink = chatVisual(window->contentItem(), "navTab9");
            if (!modelLink || !QMetaObject::invokeMethod(modelLink, "clicked")) { fail("model navigation entry"); return; }
        } else if (*phase == 17) {
            if (window->property("selectedTab").toInt() != 9 || qmlErrors) { fail("choose model navigation"); return; }
            window->setProperty("selectedTab", 1); window->setProperty("styleId", "classic");
            window->setProperty("chatWarningFeature", ""); composer->setProperty("text", "");
            preview->setProperty("messages", QVariantList{QVariantMap{{"role", "assistant"}, {"model", "Demo Code"},
                {"text", QStringLiteral("Вот пример:\n```python\ndef greet(name):\n    return f\"Привет, {name}!\"\n\nprint(greet(\"Scott\"))\n```\nФункция возвращает приветствие.")}}});
        } else if (*phase == 18) {
            auto *code = chatVisual(window->contentItem(), "chatCode0_1");
            auto *copy = chatVisual(window->contentItem(), "chatCode0_1Copy");
            auto *editor = chatVisual(window->contentItem(), "chatCode0_1Text");
            auto *list = window->findChild<QObject *>("chatList");
            if (!code || !copy || !editor || code->width() < 450 || code->height() > 224 || list->property("height").toReal() < 230) { fail("compact code layout"); return; }
            QMetaObject::invokeMethod(copy, "clicked");
            if (QApplication::clipboard()->text() != editor->property("text").toString() || QApplication::clipboard()->text().contains("```")) { fail("copy exact code"); return; }
            if (preview->property("messagesSent").toInt() || !shot("code-classic")) { fail("code must not submit commands"); return; }
            preview->setProperty("messages", QVariantList{QVariantMap{{"role", "assistant"}, {"model", "Demo Code"},
                {"text", "```cpp\n" + QString("    int value = 123456789;\n").repeated(40) + QString(400, 'x') + "\n```\nSecond example:\n```json\n{\"ok\": true}\n```"}}});
        } else if (*phase == 19) {
            auto *first = chatVisual(window->contentItem(), "chatCode0_0");
            auto *last = chatVisual(window->contentItem(), "chatCode0_2");
            auto *editor = chatVisual(window->contentItem(), "chatCode0_0Text");
            auto *copy = chatVisual(window->contentItem(), "chatCode0_0Copy");
            auto *scroll = chatVisual(window->contentItem(), "chatCode0_0Flick");
            if (!first || !last || !editor || !copy || first->height() < 600 || editor->property("contentWidth").toReal() < 1000) { fail("long code should scroll without widening chat"); return; }
            if (!scroll || scroll->property("contentHeight").toReal() > scroll->height() + 1 || scroll->property("contentWidth").toReal() <= scroll->width()) { fail("long code must have only horizontal inner scrolling"); return; }
            scroll->setProperty("contentX", 100);
            if (scroll->property("contentX").toInt() != 100) { fail("code scrolling"); return; }
            QMetaObject::invokeMethod(copy, "clicked");
            if (QApplication::clipboard()->text() != editor->property("text").toString()) { fail("long code copy is truncated"); return; }
            window->setProperty("darkMode", false);
        } else if (*phase == 20) {
            if (!shot("code-light")) { fail("code light screenshot"); return; }
            window->setProperty("darkMode", true); window->setProperty("styleId", "glass");
        } else if (*phase == 21) {
            if (!shot("code-glass")) { fail("code glass screenshot"); return; }
            window->setProperty("styleId", "terminal-pro");
        } else if (*phase == 22) {
            if (!shot("code-terminal") || qmlErrors) { fail("code terminal screenshot"); return; }
            window->setProperty("styleId", "classic");
            composer->setProperty("text", QStringLiteral("Нарисуй город на рассвете"));
            auto *button = window->findChild<QObject *>("appearanceButton");
            if (!button) { fail("appearance entry missing"); return; }
            QMetaObject::invokeMethod(button, "clicked");
        } else if (*phase == 23) {
            auto *panel = window->findChild<QObject *>("appearancePopup");
            if (!panel || !panel->property("visible").toBool() ||
                qAbs(panel->property("width").toDouble() - qMin(460, window->width()-32)) > 1 ||
                panel->property("height").toInt() > 496 || !shot("appearance-classic")) { fail("appearance popup compact layout"); return; }
            QMetaObject::invokeMethod(chatVisual(window->contentItem(), "appearanceStyle1"), "clicked");
        } else if (*phase == 24) {
            if (window->property("styleId").toString() != "glass" || !shot("appearance-glass")) { fail("style preview action"); return; }
            QMetaObject::invokeMethod(chatVisual(window->contentItem(), "appearanceAccent2"), "clicked");
            QMetaObject::invokeMethod(chatVisual(window->contentItem(), "appearanceLight"), "clicked");
        } else if (*phase == 25) {
            if (window->property("accentOverride").toString() != "#b078f5" || window->property("darkMode").toBool() || !shot("appearance-light-accent")) { fail("live accent and theme preview"); return; }
            QMetaObject::invokeMethod(chatVisual(window->contentItem(), "appearanceStyle2"), "clicked");
            window->setProperty("darkMode", true);
        } else if (*phase == 26) {
            if (window->property("styleId").toString() != "terminal-pro" || composer->property("text").toString().isEmpty() || !shot("appearance-terminal")) { fail("appearance draft lost"); return; }
            QMetaObject::invokeMethod(window->findChild<QObject *>("appearancePopup"), "close");
            QVariantList candidates;
            for (int i = 0; i < 5; ++i) candidates.append(QVariantMap{{"video_id", "abcdefghijk"}, {"title", QStringLiteral("Очень длинное название найденного видео — урок Qt Quick, интерфейс, анимация и настройка приложения ").repeated(3)}});
            preview->setProperty("browserState", QVariantMap{{"state", "complete"}, {"installed", true}, {"enabled", true}, {"browser_open", true}, {"candidates", candidates}, {"results_id", QString(32, 'a')}, {"message", QStringLiteral("Выберите видео или скажите «включи второе»")}});
        } else if (*phase == 27) {
            if (!chatVisual(window->contentItem(), "chatBrowserResult1") || !shot("inline-browser-results") || preview->property("messagesSent").toInt()) { fail("inline results or unsolicited request"); return; }
            QMetaObject::invokeMethod(composer, "submit");
            if (preview->property("messagesSent").toInt() != 1 || preview->property("lastChatImageMode").toBool() || preview->property("lastChatText").toString() != QStringLiteral("Нарисуй город на рассвете")) { fail("plain request must use automatic chat routing"); return; }
            preview->setProperty("browserState", QVariantMap{}); preview->setProperty("messages", QVariantList{});
            window->setProperty("styleId", "classic"); window->setProperty("accentOverride", "");
            window->setProperty("navigationExpanded", true); window->resize(1100, 740);
        } else if (*phase == 28) {
            if (!shot("workspace-empty") || qmlErrors) { fail("workspace screenshot"); return; }
            preview->setProperty("error", QStringLiteral("Выбранная модель не поддерживает генерацию изображений"));
            composer->setProperty("text", QStringLiteral("Нарисуй город"));
        } else if (*phase == 29) {
            auto *error = window->findChild<QObject *>("chatRequestError");
            if (!error || !error->property("visible").toBool() || composer->property("text").toString().isEmpty() || !shot("request-error")) { fail("server warning or draft lost"); return; }
            preview->setProperty("error", ""); composer->setProperty("text", "");
            window->resize(1560, 900);
        } else if (*phase == 30) {
            auto *workspace = chatVisual(window->contentItem(), "chatWorkspace");
            if (!workspace || qAbs(workspace->width() - qMin(1040.0, workspace->parentItem()->width())) > 1 || qAbs(workspace->x() - (workspace->parentItem()->width() - workspace->width()) / 2) > 1 || !shot("workspace-wide")) { fail("wide workspace must stay centered and readable"); return; }
            timer->stop(); qInfo("Chat UI: history, media, code, automatic requests and live appearance passed"); app.exit(0); return;
        }
        ++*phase;
    });
    timer->start();
}
