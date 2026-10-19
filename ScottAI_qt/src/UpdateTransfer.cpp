#include "UpdateTransfer.h"
#include "AppLog.h"
#include <QDir>
#include <QTimer>
#include <QFileInfo>
#include <memory>

UpdateTransfer::UpdateTransfer(QObject *parent):QObject(parent) {
    m_hashTimer.setSingleShot(true);connect(&m_hashTimer,&QTimer::timeout,this,&UpdateTransfer::hashStep);
}
UpdateTransfer::~UpdateTransfer() {
    m_hashTimer.stop();m_active=false;
    if(m_reply){disconnect(m_reply,nullptr,this,nullptr);m_reply->abort();m_reply=nullptr;}
    m_file.close();
}
QNetworkRequest UpdateTransfer::request(const QUrl &url) const {
    QNetworkRequest r(url); r.setTransferTimeout(30000);
    r.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::NoLessSafeRedirectPolicy);
    r.setRawHeader("User-Agent","ScottAI-Updater");
    // Transparent decompression would make byte counts/Range ambiguous.
    r.setRawHeader("Accept-Encoding","identity"); return r;
}
void UpdateTransfer::start(const UpdateRelease &release,const QString &directory) {
    if (m_active) return;
    m_release=release; m_directory=directory; m_cancelled=false; m_active=true;
    if(!QRegularExpression("^[A-Za-z0-9][A-Za-z0-9._+-]{0,180}$").match(release.name).hasMatch()
        || release.name==".." || release.size<=0 || release.size>2LL*1024*1024*1024) {fail(QStringLiteral("Некорректный файл обновления."));return;}
    if (!QDir().mkpath(directory)) { fail(QStringLiteral("Нет доступа к папке обновления.")); return; }
    if (QRegularExpression("^[a-f0-9]{64}$").match(release.sha256).hasMatch()) download();
    else getChecksum();
}
void UpdateTransfer::getChecksum() {
    emit stage(QStringLiteral("Получаем контрольную сумму…"));
    auto *reply=m_network.get(request(m_release.checksum));m_reply=reply;
    auto bytes=std::make_shared<QByteArray>();
    connect(reply,&QNetworkReply::readyRead,this,[this,reply,bytes] {
        if (m_reply!=reply) return;
        *bytes+=reply->readAll();
        if (bytes->size()>16384) fail(QStringLiteral("Некорректный файл контрольной суммы."));
    });
    connect(reply,&QNetworkReply::finished,this,[this,reply,bytes] {
        reply->deleteLater(); if (m_reply!=reply) return; m_reply=nullptr;
        if (reply->error()!=QNetworkReply::NoError) { AppLog::append("updater.log",QStringLiteral("Checksum transport: %1").arg(reply->errorString()));fail(QStringLiteral("Не удалось получить контрольную сумму. Повторите загрузку.")); return; }
        *bytes+=reply->readAll();
        const auto text=QString::fromUtf8(*bytes).trimmed();
        const auto match=QRegularExpression("^([a-fA-F0-9]{64})(?:[ \\t]+\\*?([^\\r\\n]+))?$").match(text);
        if (bytes->size()>16384 || !match.hasMatch() || (!match.captured(2).isEmpty() && match.captured(2)!=m_release.name)) {
            fail(QStringLiteral("Контрольная сумма обновления не подтверждена.")); return;
        }
        m_release.sha256=match.captured(1).toLower(); download();
    });
}
void UpdateTransfer::download() {
    emit stage(QStringLiteral("Скачиваем обновление…"));
    const auto final=m_directory+"/"+m_release.name;
    if(QFileInfo(final).isSymLink() || QFileInfo(final+".part").isSymLink()) {
        fail(QStringLiteral("Файл обновления заменён ссылкой. Выберите чистую папку кеша."));return;
    }
    if (QFileInfo::exists(final)) {
        if(QFileInfo(final).size()==m_release.size){verify(final);return;}
        if(!QFile::remove(final)){fail(QStringLiteral("Не удалось заменить повреждённый файл в кеше обновления."));return;}
    }
    m_path=final+".part";m_file.setFileName(m_path);
    if (!m_file.open(QIODevice::ReadWrite)) { fail(QStringLiteral("Не удалось открыть файл обновления для записи.")); return; }
    m_offset=m_file.size();
    if (m_offset>m_release.size) {m_file.resize(0);m_offset=0;}
    if (m_offset==m_release.size) { m_file.close();verify(m_path);return; }
    auto r=request(m_release.download);
    if (m_offset) r.setRawHeader("Range","bytes="+QByteArray::number(m_offset)+"-");
    auto *reply=m_network.get(r);reply->setReadBufferSize(1024*1024);m_reply=reply;m_headers=false;
    auto consume=[this,reply] {
        if (m_reply!=reply) return;
        if (!m_headers) {
            const int status=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
            if (status==206 && m_offset) {
                const auto match=QRegularExpression("^bytes ([0-9]+)-([0-9]+)/([0-9]+)$").match(QString::fromLatin1(reply->rawHeader("Content-Range")));
                if (!match.hasMatch() || match.captured(1).toLongLong()!=m_offset || match.captured(3).toLongLong()!=m_release.size) {
                    fail(QStringLiteral("Сервис вернул неверный диапазон файла. Повторите загрузку."));return;
                }
            } else if (status==200) {m_file.resize(0);m_offset=0;}
            else if (status>=300) { fail(QStringLiteral("Сервис загрузки ответил ошибкой %1. Скачанная часть сохранена.").arg(status));return; }
            else { fail(QStringLiteral("Неожиданный ответ сервиса загрузки."));return; }
            m_headers=true;m_file.seek(m_offset);
        }
        const auto bytes=reply->readAll();
        if (m_file.pos()+bytes.size()>m_release.size || m_file.write(bytes)!=bytes.size()) {
            fail(QStringLiteral("Не удалось записать обновление. Проверьте свободное место."));return;
        }
        emit progress(m_file.pos(),m_release.size);
    };
    connect(reply,&QNetworkReply::readyRead,this,consume);
    connect(reply,&QNetworkReply::finished,this,[this,reply,consume] {
        reply->deleteLater(); if (m_reply!=reply) return;
        if (reply->error()!=QNetworkReply::NoError) {
            AppLog::append("updater.log",QStringLiteral("Download transport %1: %2").arg(int(reply->error())).arg(reply->errorString()));
            const auto status=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
            fail(status>=400 ? QStringLiteral("Сервис загрузки ответил кодом %1. Скачанная часть сохранена.").arg(status)
                             : QStringLiteral("Загрузка прервалась. Скачанная часть сохранена; можно повторить."));return;
        }
        consume();if (m_reply!=reply) return;
        m_reply=nullptr;const auto size=m_file.size();m_file.close();
        if (size!=m_release.size) { fail(QStringLiteral("Файл скачан не полностью. Повторите загрузку."));return; }
        verify(m_path);
    });
}
void UpdateTransfer::verify(const QString &path) {
    emit stage(QStringLiteral("Проверяем обновление…"));m_path=path;m_hash.reset();m_file.setFileName(path);
    if (!m_file.open(QIODevice::ReadOnly) || m_file.size()!=m_release.size) { fail(QStringLiteral("Файл обновления неполный."));return; }
    m_hashTimer.start(0);
}
void UpdateTransfer::hashStep() {
    if (!m_active || m_cancelled) return;
    const auto bytes=m_file.read(4*1024*1024);
    if (bytes.isEmpty() && !m_file.atEnd()) { fail(QStringLiteral("Не удалось прочитать обновление."));return; }
    m_hash.addData(bytes);
    if (!m_file.atEnd()) {m_hashTimer.start(0);return;}
    m_file.close();
    if (QString::fromLatin1(m_hash.result().toHex())!=m_release.sha256) {
        QFile::remove(m_path);fail(QStringLiteral("Контрольная сумма не совпала. Повторите загрузку файла."));return;
    }
    const auto final=m_directory+"/"+m_release.name;
    if (m_path!=final && !QFile::rename(m_path,final)) {fail(QStringLiteral("Не удалось сохранить проверенное обновление."));return;}
    m_active=false;emit verified(final,m_release.sha256);
}
void UpdateTransfer::fail(const QString &message) {
    m_active=false;m_file.close();m_hashTimer.stop();
    if (m_reply) {auto *reply=m_reply;m_reply=nullptr;reply->abort();}
    emit failed(message);
}
void UpdateTransfer::cancel() { if (m_active) {m_cancelled=true;fail(QStringLiteral("Загрузка отменена."));} }
