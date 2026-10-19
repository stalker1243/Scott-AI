#include "ChatContent.h"
#include <QClipboard>
#include <QGuiApplication>
#include <QRegularExpression>

QString ChatContent::languageName(const QString &name) {
    const auto key = name.trimmed().toLower();
    static const QMap<QString, QString> aliases{
        {"py", "python"}, {"python3", "python"}, {"c++", "cpp"}, {"cxx", "cpp"},
        {"cs", "csharp"}, {"c#", "csharp"}, {"js", "javascript"}, {"ts", "typescript"},
        {"sh", "bash"}, {"shell", "bash"}, {"ps1", "powershell"}, {"ps", "powershell"},
        {"yml", "yaml"}, {"htm", "html"}};
    return aliases.value(key, key);
}

QVariantList ChatContent::split(const QString &text) const {
    // Only fenced code is special. Text and code remain literal; neither can load
    // HTML resources or execute instructions. Offsets preserve the copied source.
    static const QRegularExpression opening(QStringLiteral("^ {0,3}(`{3,}|~{3,})([^\\r\\n]*)$"));
    QVariantList blocks;
    qsizetype proseStart = 0, codeStart = -1, position = 0;
    QString fence, language;
    const auto append = [&](const QString &kind, qsizetype start, qsizetype length, const QString &lang = {}) {
        if (length > 0 || kind == "code")
            blocks.append(QVariantMap{{"kind", kind}, {"text", text.mid(start, length)}, {"language", lang}});
    };
    while (position < text.size()) {
        const qsizetype end = text.indexOf('\n', position);
        const qsizetype lineEnd = end < 0 ? text.size() : end;
        QString line = text.mid(position, lineEnd - position);
        if (line.endsWith('\r')) line.chop(1);
        const qsizetype next = end < 0 ? text.size() : end + 1;
        if (codeStart < 0) {
            const auto match = opening.match(line);
            if (match.hasMatch() && !(match.captured(1).startsWith('`') && match.captured(2).contains('`'))) {
                append("text", proseStart, position - proseStart);
                fence = match.captured(1);
                language = languageName(match.captured(2).trimmed().section(' ', 0, 0));
                codeStart = next;
            }
        } else {
            const auto trimmed = line.trimmed();
            qsizetype indent = 0;
            while (indent < line.size() && line[indent] == ' ') ++indent;
            bool closing = indent <= 3 && trimmed.size() >= fence.size();
            for (const auto ch : trimmed) closing = closing && ch == fence[0];
            if (closing) {
                append("code", codeStart, position - codeStart, language);
                codeStart = -1;
                proseStart = next;
            }
        }
        position = next;
    }
    if (codeStart >= 0) append("code", codeStart, text.size() - codeStart, language);
    else append("text", proseStart, text.size() - proseStart);
    return blocks;
}

bool ChatContent::copyCode(const QString &text) const {
    auto *clipboard = QGuiApplication::clipboard();
    if (!clipboard) return false;
    clipboard->setText(text);
    return true;
}
