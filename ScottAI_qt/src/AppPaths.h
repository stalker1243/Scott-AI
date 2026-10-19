#pragma once
#include <QDir>
#include <QFileInfo>
#include <QStandardPaths>

namespace AppPaths {
inline QString avatarDirectory(const QString &installRoot, const QString &previous, const QString &platform) {
    if (platform != "linux" || !QFileInfo::exists(installRoot + "/.scott-linux-install.json")) return previous;
    auto base = qEnvironmentVariable("XDG_DATA_HOME");
    if (!QDir::isAbsolutePath(base)) base = QDir::homePath() + "/.local/share";
    return QDir::cleanPath(base + "/scottai/qt/profile");
}
inline bool unlinked(const QString &path) {
    auto current = QDir::cleanPath(QFileInfo(path).absoluteFilePath());
    while (true) {
        if (QFileInfo(current).isSymLink()) return false;
        const auto parent = QFileInfo(current).absolutePath();
        if (parent == current) return true;
        current = parent;
    }
}
}
