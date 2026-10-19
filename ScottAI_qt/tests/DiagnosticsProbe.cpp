#include <QCoreApplication>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <cstdio>
#ifdef Q_OS_WIN
#include <qt_windows.h>
#endif
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
#ifdef Q_OS_WIN
    if (GetConsoleWindow()) return 5;
#endif
    const auto args = app.arguments();
    QJsonObject result{{"success", true}};
    if (args.contains("--output")) {
        const auto index = args.indexOf("--output");
        QFile archive(args.value(index + 1));
        if (!archive.open(QIODevice::WriteOnly)) return 6;
        archive.write("synthetic archive"); archive.close(); result.insert("path", archive.fileName());
    } else {
        result.insert("selected", "setup.log");
        result.insert("logs", QJsonArray{QJsonObject{{"name", "setup.log"}, {"exists", true}, {"size_bytes", 10}}});
        result.insert("log", QJsonObject{{"lines", QJsonArray{"ERROR synthetic install failure"}}});
    }
    const auto bytes = QJsonDocument(result).toJson(QJsonDocument::Compact);
    std::puts(bytes.constData());
    return 0;
}
