#pragma once
#include <QApplication>
#include <QQuickWindow>
#include <QQuickItem>
#include <QJSValue>
#include <QTimer>
#include <QDir>
#include <memory>

inline QQuickItem *modelPageItem(QQuickItem *parent, const QString &name) {
    if (parent->objectName() == name) return parent;
    for (auto *child : parent->childItems()) if (auto *found = modelPageItem(child, name)) return found;
    return nullptr;
}
inline void runModelPageChecks(QApplication &app, QQuickWindow *window, QObject *preview, bool &qmlErrors, bool &passed) {
    auto phase = std::make_shared<int>(0); auto *timer = new QTimer(&app); timer->setInterval(220);
    const auto fail = [&app, timer, phase](const char *text) { qWarning("Models UI: %s at phase %d", text, *phase); timer->stop(); app.exit(24); };
    QObject::connect(timer, &QTimer::timeout, &app, [&, window, preview, timer, phase, fail] {
        if (window->opacity() != 1) return;
        auto *page = window->findChild<QObject *>("modelsPage");
        auto *apply = modelPageItem(window->contentItem(), "applyModel");
        auto *token = window->findChild<QObject *>("modelToken");
        const auto choose = [page](const QString &id) { QMetaObject::invokeMethod(page, "chooseProvider", Q_ARG(QVariant, id)); };
        const auto screenshot = [window](const QString &name) {
            QDir().mkpath("screenshots"); return window->grabWindow().save("screenshots/models-" + name + ".png");
        };
        if (!page || !apply || !token || qmlErrors) { fail("missing controls or QML warning"); return; }
        if (*phase == 0) {
            window->setProperty("animationsEnabled", false); window->setProperty("selectedTab", 9);
            if (page->property("providerId").toString() != "Groq" || preview->property("modelWrites").toInt()) { fail("initial state or unsolicited write"); return; }
            screenshot("classic"); choose("OpenAI");
        } else if (*phase == 1) {
            if (apply->isEnabled() || page->property("selectedModel").toString() != "gpt-demo") { fail("unconfigured provider did not require token"); return; }
            page->setProperty("apiToken", "fixture-key"); page->setProperty("dirty", true);
        } else if (*phase == 2) {
            if (!apply->isEnabled() || token->property("echoMode").toInt() != 2) { fail("token was visible or draft invalid"); return; }
            QMetaObject::invokeMethod(modelPageItem(window->contentItem(), "revealModelToken"), "clicked");
            if (!page->property("showToken").toBool()) { fail("reveal did not work"); return; }
            choose("Anthropic");
            if (!page->property("apiToken").toString().isEmpty() || page->property("showToken").toBool()) { fail("provider switch retained token"); return; }
            page->setProperty("manualModel", true); page->setProperty("customModel", "  claude-fixture-new  "); page->setProperty("apiToken", "fixture-key");
            page->setProperty("dirty", true); QMetaObject::invokeMethod(preview, "modelsChanged");
            window->setProperty("selectedTab", 1); window->setProperty("selectedTab", 9);
        } else if (*phase == 3) {
            if (page->property("modelId").toString() != "claude-fixture-new" || page->property("apiToken").toString() != "fixture-key" || !apply->isEnabled()) { fail("refresh/navigation lost custom draft"); return; }
            QMetaObject::invokeMethod(apply, "clicked");
        } else if (*phase == 4) {
            auto request = preview->property("modelLastRequest");
            const auto sent = request.canConvert<QJSValue>() ? request.value<QJSValue>().toVariant().toMap() : request.toMap();
            if (preview->property("modelWrites").toInt() != 1 || sent.value("model").toString() != "claude-fixture-new" || !sent.value("has_key").toBool() ||
                !page->property("apiToken").toString().isEmpty() || page->property("dirty").toBool()) { fail("apply did not use manual model or clear token"); return; }
            window->setProperty("styleId", "glass"); page->setProperty("apiToken", "fixture-retry-key"); page->setProperty("dirty", true);
            preview->setProperty("modelsError", QStringLiteral("Не удалось применить настройки. Проверьте ключ; черновик сохранён."));
            preview->setProperty("modelsBusy", true);
        } else if (*phase == 5) {
            if (apply->isEnabled() || page->property("apiToken").toString() != "fixture-retry-key") { fail("busy guard or error discarded draft"); return; }
            screenshot("glass-busy"); preview->setProperty("modelsBusy", false); preview->setProperty("online", false);
            window->setProperty("darkMode", false);
        } else if (*phase == 6) {
            if (apply->isEnabled()) { fail("offline apply enabled"); return; }
            screenshot("glass-light-offline"); preview->setProperty("online", true); preview->setProperty("modelsError", "");
            window->setProperty("styleId", "terminal-pro"); window->setProperty("darkMode", true);
            window->resize(800, 560); window->setProperty("navigationExpanded", true); choose("OpenRouter");
            page->setProperty("search", "large");
        } else if (*phase == 7) {
            if (page->property("apiToken").toString().length() || page->property("selectedModel").toString() != "vendor/free-demo") { fail("search/switch corrupted model or token"); return; }
            const auto choices = page->property("choices").value<QJSValue>().toVariant().toList();
            if (choices.size() != 1 || choices.first().toMap().value("id").toString() != "vendor/large-demo") { fail("model search failed"); return; }
            const auto position = apply->mapToItem(window->contentItem(), QPointF());
            if (position.y() + apply->height() > window->height()) { fail("apply does not fit compact window"); return; }
            screenshot("terminal-compact"); page->setProperty("manualModel", true); page->setProperty("customModel", "bad model"); page->setProperty("apiToken", "fixture-key");
        } else if (*phase == 8) {
            if (apply->isEnabled()) { fail("invalid custom ID accepted"); return; }
            page->setProperty("customModel", "vendor/custom-latest");
        } else if (*phase == 9) {
            QMetaObject::invokeMethod(apply, "clicked");
            if (preview->property("modelWrites").toInt() != 2) { fail("custom OpenRouter model was not sent"); return; }
            preview->setProperty("modelsReady", false);
        } else if (*phase == 10) {
            if (apply->isEnabled()) { fail("unloaded settings could apply"); return; }
            preview->setProperty("modelsReady", true); preview->setProperty("aiProviders", QVariantList{});
        } else if (*phase == 11) {
            if (apply->isEnabled()) { fail("empty catalog could apply"); return; }
            screenshot("empty"); passed = true; timer->stop();
            qInfo("Models UI: providers, masked token, drafts, manual ID, search, apply, states and compact styles passed"); app.exit(0);
        }
        ++*phase;
    });
    QTimer::singleShot(15000, &app, [fail] { fail("timeout"); }); timer->start();
}
