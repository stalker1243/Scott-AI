#include <QCoreApplication>
#include <QTcpServer>
#include <QTcpSocket>
#include <QFile>
#include <QTimer>
#include <QJsonDocument>
#include <QJsonObject>
#include <memory>
#include <cstdio>

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    QFile count(qEnvironmentVariable("SCOTT_RECOVERY_COUNT"));
    int launches = 0;
    if (count.open(QIODevice::ReadOnly)) { launches = count.readAll().trimmed().toInt(); count.close(); }
    if (!count.open(QIODevice::WriteOnly | QIODevice::Truncate)) return 71;
    count.write(QByteArray::number(++launches)); count.close();
    if (qEnvironmentVariableIsSet("SCOTT_RECOVERY_CRASH_LOOP")) return 91;
    QTcpServer server;
    if (!server.listen(QHostAddress::LocalHost, qEnvironmentVariableIntValue("SCOTT_RECOVERY_PORT"))) return 72;
    std::fputs("READY\n", stdout); std::fflush(stdout);
    QObject::connect(&server, &QTcpServer::newConnection, &app, [&] {
        auto *socket = server.nextPendingConnection();
        QObject::connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
        auto buffer = std::make_shared<QByteArray>();
        QObject::connect(socket, &QTcpSocket::readyRead, socket, [&, socket, buffer] {
            buffer->append(socket->readAll());
            const auto &data = *buffer;
            if (!data.contains("\r\n\r\n")) return;
            const bool crash = data.startsWith("GET /fixture/crash ");
            QJsonObject body{{"success", true}};
            if (data.startsWith("GET /health ")) body = {{"status", "online"}, {"features", QJsonObject{{"request_receipts", 1}}}};
            if (data.startsWith("GET /listen/status ")) body = {{"available", false}, {"listening", false}};
            const auto bytes = QJsonDocument(body).toJson(QJsonDocument::Compact);
            socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: " + QByteArray::number(bytes.size()) + "\r\n\r\n" + bytes);
            socket->disconnectFromHost();
            if (crash) QTimer::singleShot(50, &app, [&app] { app.exit(91); });
        });
    });
    return app.exec();
}
