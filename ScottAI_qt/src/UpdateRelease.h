#pragma once
#include <QJsonObject>
#include <QJsonArray>
#include <QUrl>
#include <QVersionNumber>
#include <QRegularExpression>

struct UpdateRelease {
    QString version, name, sha256, repo;
    QUrl download, checksum, page;
    qint64 size = 0;
    bool available = false;
    QJsonObject json() const {
        return {{"version",version},{"name",name},{"sha256",sha256},{"repo",repo},
                {"download",download.toString()},{"checksum",checksum.toString()},
                {"page",page.toString()},{"size",size},{"available",available}};
    }
    static UpdateRelease fromJson(const QJsonObject &o) {
        return {o["version"].toString(),o["name"].toString(),o["sha256"].toString(),o["repo"].toString(),
                QUrl(o["download"].toString()),QUrl(o["checksum"].toString()),QUrl(o["page"].toString()),
                o["size"].toInteger(),o["available"].toBool()};
    }
    bool verifiedSource() const {
        const QRegularExpression repository("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$");
        const QRegularExpression file("^[A-Za-z0-9][A-Za-z0-9._+-]{0,180}$");
        auto trusted = [&](const QUrl &url, const QString &filename) {
            return url.scheme()=="https" && url.host()=="github.com" && url.userInfo().isEmpty()
                && url.port(-1)==-1 && !url.hasQuery() && !url.hasFragment()
                && url.path().startsWith("/"+repo+"/releases/download/")
                && url.fileName()==filename;
        };
        return available && repository.match(repo).hasMatch() && file.match(name).hasMatch()
            && name!="." && name!=".." && size>0 && size<=2LL*1024*1024*1024
            && trusted(download,name) && (QRegularExpression("^[a-f0-9]{64}$").match(sha256).hasMatch()
                                       || trusted(checksum,name+".sha256"));
    }
};

inline UpdateRelease releaseFromGitHub(const QJsonObject &o, const QString &current,
                                      const QString &repo, const QString &platform) {
    UpdateRelease r; r.repo=repo; r.version=o["tag_name"].toString();
    if (r.version.startsWith('v',Qt::CaseInsensitive)) r.version.remove(0,1);
    const QRegularExpression version("^[0-9]+(?:\\.[0-9]+){1,3}$");
    r.available=!o["draft"].toBool() && !o["prerelease"].toBool()
        && version.match(r.version).hasMatch()
        && QVersionNumber::fromString(r.version)>QVersionNumber::fromString(current);
    r.page=QUrl("https://github.com/"+repo+"/releases");
    const auto assets=o["assets"].toArray();
    const QString suffix=platform=="windows" ? "-setup.exe"
        : platform=="appimage" ? "-linux-x86_64.AppImage" : "-linux-x86_64.tar.gz";
    for (const auto &entry:assets) {
        const auto asset=entry.toObject(); const auto name=asset["name"].toString();
        if (!name.startsWith("ScottAI-",Qt::CaseInsensitive) || !name.endsWith(suffix,Qt::CaseInsensitive)
            || name.contains("arm64",Qt::CaseInsensitive)) continue;
        r.name=name; r.size=asset["size"].toInteger(); r.download=QUrl(asset["browser_download_url"].toString());
        const auto digest=asset["digest"].toString();
        if (digest.startsWith("sha256:")) r.sha256=digest.mid(7).toLower();
        for (const auto &candidate:assets) {
            const auto checksum=candidate.toObject();
            if (checksum["name"].toString()==name+".sha256") r.checksum=QUrl(checksum["browser_download_url"].toString());
        }
        break;
    }
    return r;
}
