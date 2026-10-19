#include "CodeHighlighter.h"
#include "ChatContent.h"
#include <QTextDocument>

CodeHighlighter::CodeHighlighter(QObject *parent) : QSyntaxHighlighter(parent) {}

void CodeHighlighter::setSource(QQuickTextDocument *source) {
    if (m_source == source) return;
    if (m_source) disconnect(m_source, nullptr, this, nullptr);
    m_source = source;
    setDocument(source ? source->textDocument() : nullptr);
    if (source) {
        connect(source, &QQuickTextDocument::textDocumentChanged, this, [this] {
            setDocument(m_source ? m_source->textDocument() : nullptr);
        });
        connect(source, &QObject::destroyed, this, [this] { setDocument(nullptr); emit sourceChanged(); });
    }
    emit sourceChanged();
}

void CodeHighlighter::setLanguage(const QString &language) {
    const auto key = ChatContent::languageName(language);
    if (m_language == key) return;
    m_language = key;
    m_keywords.clear();
    static const QMap<QString, QString> words{
        {"python", "and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield match case"},
        {"cpp", "alignas auto bool break case catch char class const constexpr continue default delete do double else enum explicit extern false float for friend if inline int long namespace new nullptr override private protected public return short signed sizeof static struct switch template this throw true try typedef typename union unsigned using virtual void volatile while"},
        {"c", "auto break case char const continue default do double else enum extern float for if int long return short signed sizeof static struct switch typedef union unsigned void volatile while"},
        {"csharp", "async await base bool break case catch char class const continue decimal default delegate do double else enum event false finally float for foreach if in int interface internal is lock namespace new null object override private protected public readonly return sealed static string struct switch this throw true try typeof using var virtual void while yield"},
        {"javascript", "async await break case catch class const continue debugger default delete do else export extends false finally for from function if import in instanceof let new null of return static super switch this throw true try typeof undefined var void while yield"},
        {"typescript", "abstract any as async await boolean break case catch class const continue declare default do else enum export extends false finally for from function if implements import in interface keyof let namespace never new null number of private protected public readonly return static string super switch this throw true try type typeof undefined unknown var void while yield"},
        {"java", "abstract boolean break byte case catch char class const continue default do double else enum extends false final finally float for if implements import instanceof int interface long native new null package private protected public return short static super switch synchronized this throw throws true try void volatile while"},
        {"go", "break case chan const continue default defer else fallthrough for func go goto if import interface map package range return select struct switch type var true false nil"},
        {"rust", "as async await break const continue crate dyn else enum extern false fn for if impl in let loop match mod move mut pub ref return self Self static struct super trait true type unsafe use where while"},
        {"json", "true false null"},
        {"yaml", "true false null yes no"},
        {"bash", "if then else elif fi for while do done in case esac function select until export local return"},
        {"powershell", "begin break catch class continue data do else elseif end enum exit filter finally for foreach from function if in param process return switch throw trap try until using var while"},
        {"sql", "select from where join left right inner outer on as and or not null true false insert into values update set delete create table alter drop distinct group by order having limit union all case when then else end asc desc exists in is"},
        {"html", "html head body div span script style a img input button p meta link title"},
        {"css", "important inherit initial unset auto none"}};
    for (const auto &word : words.value(key).split(' ', Qt::SkipEmptyParts)) m_keywords.insert(word);
    rehighlight();
    emit languageChanged();
}

void CodeHighlighter::setDark(bool dark) {
    if (m_dark == dark) return;
    m_dark = dark;
    rehighlight();
    emit darkChanged();
}

void CodeHighlighter::highlightBlock(const QString &text) {
    setCurrentBlockState(0);
    if (m_keywords.isEmpty()) return; // Unknown languages stay readable and literal.
    const QColor keyword(m_dark ? "#c7a5ff" : "#7442a8");
    const QColor string(m_dark ? "#9ed5ae" : "#236744");
    const QColor number(m_dark ? "#f5c78e" : "#955514");
    const QColor comment(m_dark ? "#93a2b7" : "#627080");
    const QColor symbol(m_dark ? "#8fd1ee" : "#176c92");
    const bool hash = m_language == "python" || m_language == "bash" || m_language == "powershell" || m_language == "yaml";
    const bool cComments = m_language == "cpp" || m_language == "c" || m_language == "csharp" || m_language == "javascript" || m_language == "typescript" || m_language == "java" || m_language == "go" || m_language == "rust" || m_language == "css";
    const bool sql = m_language == "sql";
    int state = qMax(0, previousBlockState());
    qsizetype i = 0;
    // A linear scan avoids expensive regular expressions on pasted long lines.
    while (i < text.size()) {
        if (state) {
            const QString end = state == 1 ? "*/" : state == 2 ? "'''" : state == 3 ? "\"\"\"" : state == 4 ? "-->" : "#>";
            const auto close = text.indexOf(end, i);
            const auto until = close < 0 ? text.size() : close + end.size();
            setFormat(i, until - i, state == 2 || state == 3 ? string : comment);
            i = until;
            if (close < 0) break;
            state = 0;
            continue;
        }
        if ((cComments || sql) && text.mid(i, 2) == "/*") state = 1;
        else if (m_language == "python" && text.mid(i, 3) == "'''") state = 2;
        else if (m_language == "python" && text.mid(i, 3) == "\"\"\"") state = 3;
        else if (m_language == "html" && text.mid(i, 4) == "<!--") state = 4;
        else if (m_language == "powershell" && text.mid(i, 2) == "<#") state = 5;
        if (state) {
            const qsizetype length = state == 2 || state == 3 ? 3 : state == 4 ? 4 : 2;
            setFormat(i, length, state == 2 || state == 3 ? string : comment);
            i += length;
            continue;
        }
        if ((hash && text[i] == '#') || (cComments && text.mid(i, 2) == "//") || (sql && text.mid(i, 2) == "--")) {
            setFormat(i, text.size() - i, comment);
            break;
        }
        const QChar ch = text[i];
        if (ch == '\'' || ch == '"' || (ch == '`' && (m_language == "javascript" || m_language == "typescript" || m_language == "go"))) {
            const auto start = i++;
            while (i < text.size()) {
                if (text[i] == '\\' && !sql) { i = qMin(i + 2, text.size()); continue; }
                if (text[i++] == ch) {
                    if (sql && i < text.size() && text[i] == ch) { ++i; continue; }
                    break;
                }
            }
            setFormat(start, i - start, string);
        } else if (ch.isDigit() && (i == 0 || !(text[i - 1].isLetterOrNumber() || text[i - 1] == '_'))) {
            const auto start = i++;
            while (i < text.size() && (text[i].isLetterOrNumber() || text[i] == '.' || text[i] == '_')) ++i;
            setFormat(start, i - start, number);
        } else if (ch.isLetter() || ch == '_' || (ch == '$' && (m_language == "bash" || m_language == "powershell"))) {
            const auto start = i++;
            while (i < text.size() && (text[i].isLetterOrNumber() || text[i] == '_' || text[i] == '-')) ++i;
            auto word = text.mid(start, i - start);
            if (sql || m_language == "powershell") word = word.toLower();
            if (m_keywords.contains(word)) setFormat(start, i - start, keyword);
            else if (ch == '$') setFormat(start, i - start, symbol);
        } else ++i;
    }
    setCurrentBlockState(state);
}
