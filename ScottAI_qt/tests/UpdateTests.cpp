#include "UpdateRelease.h"
#include "UpdateTransfer.h"
#include <QtTest>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QSignalSpy>
#include <QFile>

class UpdateTests:public QObject {
    Q_OBJECT
private slots:
    void linkedCacheFileIsPreserved() {
#ifdef Q_OS_WIN
        QSKIP("Linux symbolic link contract; Windows test user lacks symlink privilege");
#else
        QTemporaryDir dir;QFile protectedFile(dir.path()+"/preserve");QVERIFY(protectedFile.open(QIODevice::WriteOnly));protectedFile.write("preserve");protectedFile.close();
        UpdateRelease release;release.name="ScottAI-9.0.0-Qt-setup.exe";release.size=8;release.sha256=QString(64,'a');
        QVERIFY(QFile::link(protectedFile.fileName(),dir.path()+"/"+release.name+".part"));
        UpdateTransfer transfer;QSignalSpy failed(&transfer,&UpdateTransfer::failed);transfer.start(release,dir.path());
        QCOMPARE(failed.count(),1);QVERIFY(protectedFile.open(QIODevice::ReadOnly));QCOMPARE(protectedFile.readAll(),QByteArray("preserve"));
#endif
    }
    void releaseSelection() {
        QJsonObject asset{{"name","ScottAI-9.0.0-Qt-setup.exe"},{"size",12},
            {"digest","sha256:"+QString(64,'a')},
            {"browser_download_url","https://github.com/test/scott/releases/download/v9.0.0/ScottAI-9.0.0-Qt-setup.exe"}};
        QJsonObject json{{"tag_name","v9.0.0"},{"assets",QJsonArray{asset}}};
        auto r=releaseFromGitHub(json,"2.0.1","test/scott","windows");
        QVERIFY(r.available);QVERIFY(r.verifiedSource());
        QVERIFY(!releaseFromGitHub(json,"9.0.0","test/scott","windows").available);
        QVERIFY(!releaseFromGitHub(json,"9.0.1","test/scott","windows").available);
        json["prerelease"]=true;QVERIFY(!releaseFromGitHub(json,"2.0.1","test/scott","windows").available);
        r.download=QUrl("https://github.com/another/repo/releases/download/v9.0.0/"+r.name);QVERIFY(!r.verifiedSource());
        r.download=QUrl("http://github.com/test/scott/releases/download/v9.0.0/"+r.name);QVERIFY(!r.verifiedSource());
    }
    void checksumFallbackAndPlatform() {
        const auto url="https://github.com/test/scott/releases/download/v9/";
        QJsonObject asset{{"name","ScottAI-9.0.0-Qt-linux-x86_64.tar.gz"},{"size",12},
            {"browser_download_url",QString(url)+"ScottAI-9.0.0-Qt-linux-x86_64.tar.gz"}};
        QJsonObject checksum{{"name",asset["name"].toString()+".sha256"},{"browser_download_url",QString(url)+asset["name"].toString()+".sha256"}};
        QJsonObject json{{"tag_name","v9.0.0"},{"assets",QJsonArray{asset,checksum}}};
        auto r=releaseFromGitHub(json,"2.0.1","test/scott","linux");QVERIFY(r.verifiedSource());
        QVERIFY(!releaseFromGitHub(json,"2.0.1","test/scott","windows").verifiedSource());
        r.checksum=QUrl(QString(url)+"different.sha256");QVERIFY(!r.verifiedSource());
        r.name="../escape";QVERIFY(!r.verifiedSource());
    }
    void appImageAssetSelection() {
        const auto url=QStringLiteral("https://github.com/test/scott/releases/download/v9/");
        const QString tar="ScottAI-9.0.0-Qt-linux-x86_64.tar.gz",image="ScottAI-9.0.0-Qt-linux-x86_64.AppImage";
        QJsonArray assets;
        for(const auto &name:{tar,image})assets.append(QJsonObject{{"name",name},{"size",128},
            {"digest","sha256:"+QString(64,'a')},{"browser_download_url",url+name}});
        const QJsonObject release{{"tag_name","v9.0.0"},{"assets",assets}};
        const auto selected=releaseFromGitHub(release,"2.0.1","test/scott","appimage");
        QCOMPARE(selected.name,image);QVERIFY(selected.verifiedSource());
        QCOMPARE(releaseFromGitHub(release,"2.0.1","test/scott","linux").name,tar);
    }
    void download_data() {
        QTest::addColumn<QString>("mode");
        for(const auto &mode:{"fresh","bad-final-size","resume","interrupted","ignored-range","wrong-range","wrong-hash","checksum","bad-checksum","http-error","cancel"})
            QTest::newRow(mode)<<QString(mode);
    }
    void download() {
        QFETCH(QString,mode);QTemporaryDir directory;QTcpServer server;QVERIFY(server.listen(QHostAddress::LocalHost));
        const QByteArray data("verified fixture installer; this is never executed");
        const auto hash=QString::fromLatin1(QCryptographicHash::hash(data,QCryptographicHash::Sha256).toHex());
        UpdateRelease release;release.name="ScottAI-9.0.0-Qt-setup.exe";release.size=data.size();release.sha256=hash;
        release.download=QUrl(QString("http://127.0.0.1:%1/file").arg(server.serverPort()));
        if(mode=="checksum" || mode=="bad-checksum") {release.sha256.clear();release.checksum=QUrl(QString("http://127.0.0.1:%1/checksum").arg(server.serverPort()));}
        if(mode=="wrong-hash")release.sha256=QString(64,'0');
        if(mode=="bad-final-size"){QFile final(directory.path()+"/"+release.name);QVERIFY(final.open(QIODevice::WriteOnly));final.write("truncated");}
        if(mode=="resume" || mode=="ignored-range" || mode=="wrong-range") {
            QFile part(directory.path()+"/"+release.name+".part");QVERIFY(part.open(QIODevice::WriteOnly));part.write(data.left(8));
        }
        QList<QByteArray> requests;
        connect(&server,&QTcpServer::newConnection,this,[&]{
            auto *socket=server.nextPendingConnection();auto buffer=std::make_shared<QByteArray>();
            connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
            connect(socket,&QTcpSocket::readyRead,this,[&,socket,buffer]{
                *buffer+=socket->readAll();if(!buffer->contains("\r\n\r\n"))return;
                requests.append(*buffer);
                if(buffer->startsWith("GET /checksum")) {
                    const auto body=mode=="bad-checksum" ? QByteArray("invalid") : (hash+"  "+release.name+"\n").toUtf8();
                    socket->write("HTTP/1.1 200 OK\r\nContent-Length: "+QByteArray::number(body.size())+"\r\n\r\n"+body);socket->disconnectFromHost();return;
                }
                if(mode=="cancel") {socket->write("HTTP/1.1 200 OK\r\nContent-Length: "+QByteArray::number(data.size())+"\r\n\r\n"+data.left(8));return;}
                if(mode=="interrupted" && requests.size()==1) {socket->write("HTTP/1.1 200 OK\r\nContent-Length: "+QByteArray::number(data.size())+"\r\n\r\n"+data.left(8));socket->disconnectFromHost();return;}
                if(mode=="http-error") {socket->write("HTTP/1.1 503 Unavailable\r\nContent-Length: 0\r\n\r\n");socket->disconnectFromHost();return;}
                QByteArray header="HTTP/1.1 200 OK\r\n",body=data;
                if(mode=="resume" || mode=="wrong-range" || mode=="interrupted") {
                    body=data.mid(8);header="HTTP/1.1 206 Partial Content\r\nContent-Range: bytes "+QByteArray(mode=="wrong-range"?"7":"8")+"-"+QByteArray::number(data.size()-1)+"/"+QByteArray::number(data.size())+"\r\n";
                }
                socket->write(header+"Content-Length: "+QByteArray::number(body.size())+"\r\n\r\n"+body);socket->disconnectFromHost();
            });
        });
        UpdateTransfer transfer;QSignalSpy verified(&transfer,&UpdateTransfer::verified),failed(&transfer,&UpdateTransfer::failed),progress(&transfer,&UpdateTransfer::progress);
        transfer.start(release,directory.path());
        if(mode=="interrupted") {QTRY_COMPARE_WITH_TIMEOUT(failed.count(),1,3000);QCOMPARE(QFileInfo(directory.path()+"/"+release.name+".part").size(),qint64(8));transfer.start(release,directory.path());}
        if(mode=="cancel"){QTRY_VERIFY_WITH_TIMEOUT(!progress.isEmpty(),2000);transfer.cancel();}
        const bool success=mode=="fresh" || mode=="bad-final-size" || mode=="resume" || mode=="interrupted" || mode=="ignored-range" || mode=="checksum";
        if(success) {
            QTRY_COMPARE_WITH_TIMEOUT(verified.count(),1,3000);QCOMPARE(failed.count(),mode=="interrupted"?1:0);
            QFile file(verified[0][0].toString());QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),data);QCOMPARE(verified[0][1].toString(),hash);
            if(mode=="resume" || mode=="interrupted" || mode=="ignored-range")QVERIFY(requests.last().contains("Range: bytes=8-"));
            const auto count=requests.size();transfer.start(release,directory.path());QTRY_COMPARE_WITH_TIMEOUT(verified.count(),2,3000);
            // A companion checksum can be requested again, but the installer is reused.
            QCOMPARE(requests.size()-count,mode=="checksum"?1:0);
        } else {QTRY_COMPARE_WITH_TIMEOUT(failed.count(),1,3000);QCOMPARE(verified.count(),0);}
        QVERIFY(!transfer.active());
    }
};
QTEST_GUILESS_MAIN(UpdateTests)
#include "UpdateTests.moc"
