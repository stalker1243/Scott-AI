#pragma once
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QMutex>
#include <QMutexLocker>
#include <QRegularExpression>

namespace AppLog {
inline QString directory;
inline QMutex mutex;
inline void ensureDirectory(const QString &path) {
    QStringList missing;
    auto current = QFileInfo(path).absoluteFilePath();
    while (!QFileInfo::exists(current)) {
        missing.append(current);
        const auto parent = QFileInfo(current).absolutePath();
        if (parent == current) break;
        current = parent;
    }
    for (auto entry = missing.crbegin(); entry != missing.crend(); ++entry) {
        if (QDir().mkdir(*entry)) {
#ifndef Q_OS_WIN
            QFile::setPermissions(*entry, QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
#endif
        }
    }
}
inline QString defaultDirectory() {
    const auto override = qEnvironmentVariable("SCOTT_LOG_DIR");
    if (!override.isEmpty()) return override;
#ifdef Q_OS_WIN
    auto base = qEnvironmentVariable("LOCALAPPDATA");
    if (base.isEmpty()) base = QDir::homePath() + "/AppData/Local";
#else
    auto base = qEnvironmentVariable("XDG_STATE_HOME");
    if (base.isEmpty() || !QDir::isAbsolutePath(base)) base = QDir::homePath() + "/.local/state";
#endif
    return base + "/ScottAI/logs";
}
inline QString redact(QString text) {
    for (const auto &pattern : {QStringLiteral("(?:sk-|gsk_|github_pat_|gh[pousr]_)[A-Za-z0-9_-]{8,}"),
            QStringLiteral("(?i)Bearer\\s+[^\\s\"'<>]+"),
            QStringLiteral("(?i)(?:[\\w-]*(?:api[_-]?key|token|secret|password)|authorization|токен|ключ)\\s*[\"']?\\s*[:=]\\s*[\"']?[^\\s,;\"']+")})
        text.replace(QRegularExpression(pattern), QStringLiteral("***СКРЫТО***"));
    const QRegularExpression privateLine(QStringLiteral("(?i)user[_ ]?(?:text|message|prompt)|recognized[_ ]text|распознано|текст команды|user command|prompt\\s*[:=]"));
    auto lines = text.split('\n');
    for (auto &line : lines) if (privateLine.match(line).hasMatch()) line = QStringLiteral("[Текст запроса скрыт]");
    text = lines.join('\n');
    text.replace(QDir::homePath(), "<HOME>");
    return text;
}
inline void append(const QString &name, const QString &message) {
    if (directory.isEmpty()) return;
    QMutexLocker locker(&mutex);
    ensureDirectory(directory);
    const auto path = directory + "/" + name;
    constexpr qint64 limit = 2 * 1024 * 1024;
    if (QFileInfo(path).isSymLink()) return;
    if (QFileInfo(path).size() >= limit) {
        for (int index = 2; index >= 1; --index) {
            const auto source = index == 1 ? path : path + ".1";
            const auto destination = path + "." + QString::number(index);
            if (QFileInfo(source).isSymLink() || QFileInfo(destination).isSymLink()) continue;
            QFile::remove(destination); QFile::rename(source, destination);
        }
    }
    QFile file(path);
    if (file.open(QIODevice::WriteOnly | QIODevice::Append)) {
        file.setPermissions(QFile::ReadOwner | QFile::WriteOwner);
        file.write((QDateTime::currentDateTime().toString(Qt::ISODate) + " " + redact(message) + "\n").toUtf8().right(limit));
    }
}
inline void appendChunk(const QString &name, QByteArray &buffer, const QByteArray &bytes) {
    buffer += bytes;
    while (buffer.contains('\n')) {
        const auto end = buffer.indexOf('\n');
        append(name, QString::fromUtf8(buffer.left(end)));
        buffer.remove(0, end + 1);
    }
    if (buffer.size() > 65536) { append(name, "[Long output line omitted]"); buffer.clear(); }
}
}
