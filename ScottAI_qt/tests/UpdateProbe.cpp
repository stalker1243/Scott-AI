// Handoff fixture: no download, installation, parent shutdown or app restart.
#include <QCoreApplication>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLocalSocket>
#include <QTimer>
int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);const auto args=app.arguments();
    QFile file(args.value(args.indexOf("--job")+1));if(!file.open(QIODevice::ReadOnly))return 2;
    const auto job=QJsonDocument::fromJson(file.readAll()).object();QLocalSocket socket;
    QObject::connect(&socket,&QLocalSocket::connected,&app,[&]{socket.write(job["cookie"].toString().toUtf8()+"\n");socket.flush();});
    QObject::connect(&socket,&QLocalSocket::readyRead,&app,[&]{
        if(socket.readAll()!="accepted\n")return;
        QFile proof(job["root"].toString()+"/handoff-proof");if(!proof.open(QIODevice::WriteOnly))app.exit(4);
        else{proof.write("accepted without closing the fixture parent");proof.close();app.exit(0);}
    });
    QTimer::singleShot(5000,&app,[&]{app.exit(5);});socket.connectToServer(job["server"].toString());return app.exec();
}
