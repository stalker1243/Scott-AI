#pragma once
#include "AppPaths.h"
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#ifdef Q_OS_LINUX
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace AppImageSupport {
inline QByteArray processIdentity(const QString &pid) {
    QFile file("/proc/"+pid+"/stat");
    if(!file.open(QIODevice::ReadOnly)) return {};
    const auto bytes=file.readAll();
    const auto fields=bytes.mid(bytes.lastIndexOf(')')+2).split(' ');
    return fields.size()>=20 ? fields[19] : QByteArray();
}
inline QJsonObject snapshot(const QString &path) {
#ifdef Q_OS_LINUX
    struct stat info{};
    if(!QDir::isAbsolutePath(path) || !AppPaths::unlinked(path)
        || ::lstat(QFile::encodeName(path).constData(),&info)!=0
        || !S_ISREG(info.st_mode) || info.st_uid!=::getuid() || info.st_nlink!=1
        || info.st_size<64 || info.st_size>2LL*1024*1024*1024 || (info.st_mode&07000)
        || !QFileInfo(QFileInfo(path).absolutePath()).isWritable())return {};
    QFile file(path);if(!file.open(QIODevice::ReadOnly))return {};
    const auto head=file.read(64);
    if(head.size()!=64 || head.left(6)!=QByteArray::fromHex("7f454c460201")
        || head.mid(8,3)!=QByteArray("AI\2",3) || head.mid(18,2)!=QByteArray::fromHex("3e00"))return {};
    return {{"path",path},{"device",QString::number(qulonglong(info.st_dev))},
            {"inode",QString::number(qulonglong(info.st_ino))},{"size",QString::number(info.st_size)},
            {"mtime_ns",QString::number(qlonglong(info.st_mtim.tv_sec)*1000000000LL+info.st_mtim.tv_nsec)}};
#else
    Q_UNUSED(path);return {};
#endif
}
inline bool unchanged(const QJsonObject &image) {
    const auto current=snapshot(image["path"].toString());
    if(current.isEmpty())return false;
    for(const auto &key:current.keys())if(current[key]!=image[key])return false;
    return true;
}
inline QJsonObject context(const QString &root) {
#ifdef Q_OS_LINUX
    QFile marker(root+"/.scott-linux-install.json");
    if(!marker.open(QIODevice::ReadOnly) || marker.size()>32768
        || QJsonDocument::fromJson(marker.readAll()).object()["image_layout"].toInt()!=1
        || QFileInfo(qEnvironmentVariable("APPDIR")).canonicalFilePath()!=QFileInfo(root).canonicalFilePath())return {};
    auto image=snapshot(qEnvironmentVariable("APPIMAGE"));
    if(image.isEmpty())return {};
    const bool extract=QFileInfo(root).fileName().startsWith("appimage_extracted_")
        || qEnvironmentVariableIsSet("APPIMAGE_EXTRACT_AND_RUN");
    image["extract"]=extract;
    if(extract) {
        const auto parent=QString::number(::getppid());
        const auto start=processIdentity(parent);
        if(start.isEmpty())return {};
        image["runtime_parent"]=parent;image["runtime_identity"]=QString::fromLatin1(start);
    }
    return image;
#else
    Q_UNUSED(root);return {};
#endif
}
}
