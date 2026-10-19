#include "ChatContent.h"
#include "CodeHighlighter.h"
#include <QtTest>
#include <QTextDocument>
#include <QTextBlock>
#include <QTextLayout>
#include <QClipboard>
#include <QMimeData>

class ChatContentTests : public QObject {
    Q_OBJECT
private slots:
    void fencesPreserveLiteralSource() {
        ChatContent content;
        const QString source = "    print(\"<script> & `literal`\")\r\n\treturn 42\r\n";
        const auto parts = content.split("Before\r\n```py\r\n" + source + "```\r\nAfter");
        QCOMPARE(parts.size(), 3);
        QCOMPARE(parts[0].toMap()["text"].toString(), QString("Before\r\n"));
        QCOMPARE(parts[1].toMap()["kind"].toString(), QString("code"));
        QCOMPARE(parts[1].toMap()["language"].toString(), QString("python"));
        QCOMPARE(parts[1].toMap()["text"].toString(), source);
        QCOMPARE(parts[2].toMap()["text"].toString(), QString("After"));
    }
    void multipleAndIncompleteFences() {
        ChatContent content;
        const auto parts = content.split("~~~c++\nint x = 1;\n~~~~\nText\n````json\n{\"x\": 2}\n```\n");
        QCOMPARE(parts.size(), 3);
        QCOMPARE(parts[0].toMap()["language"].toString(), QString("cpp"));
        QCOMPARE(parts[2].toMap()["text"].toString(), QString("{\"x\": 2}\n```\n"));
        const auto empty = content.split("```python");
        QCOMPARE(empty.size(), 1);
        QCOMPARE(empty[0].toMap()["kind"].toString(), QString("code"));
        const auto inlineText = content.split("Use ```code``` inline.\n    ```py\nnot a fence");
        QCOMPARE(inlineText.size(), 1);
        QCOMPARE(inlineText[0].toMap()["kind"].toString(), QString("text"));
    }
    void longCodeIsNeverTruncated() {
        ChatContent content;
        const QString source = QString(90000, 'x') + "\n";
        const auto parts = content.split("```unknown\n" + source + "```\n");
        QCOMPARE(parts.size(), 1);
        QCOMPARE(parts[0].toMap()["text"].toString(), source);
    }
    void clipboardContainsOnlyExactCode() {
        auto *clipboard = QGuiApplication::clipboard();
        auto *saved = new QMimeData;
        if (const auto *original = clipboard->mimeData())
            for (const auto &format : original->formats()) saved->setData(format, original->data(format));
        struct Restore { QClipboard *clipboard; QMimeData *saved; ~Restore() { clipboard->setMimeData(saved); } } restore{clipboard, saved};
        ChatContent content;
        const QString source = "\tprint(\"<img src='private.png'>\")\n\n";
        QVERIFY(content.copyCode(source));
        QCOMPARE(clipboard->text(), source);
    }
    void syntaxThemesCommentsAndUnknownLanguage() {
        QTextDocument doc;
        CodeHighlighter highlighter;
        highlighter.setDocument(&doc);
        highlighter.setLanguage("py");
        doc.setPlainText("def f():\n    return \"if\" # 42\n\"\"\"comment\nsecond\"\"\"\nreturn 1");
        highlighter.rehighlight();
        const auto first = doc.firstBlock().layout()->formats();
        QVERIFY(!first.isEmpty());
        const QColor dark = first[0].format.foreground().color();
        const auto second = doc.findBlockByNumber(1).layout()->formats();
        QVERIFY(second.size() >= 3);
        QCOMPARE(doc.findBlockByNumber(2).userState(), 3);
        QCOMPARE(doc.findBlockByNumber(3).userState(), 0);
        highlighter.setDark(false);
        QVERIFY(doc.firstBlock().layout()->formats()[0].format.foreground().color() != dark);
        highlighter.setLanguage("unknown");
        QVERIFY(doc.firstBlock().layout()->formats().isEmpty());
        QCOMPARE(doc.toPlainText(), QString("def f():\n    return \"if\" # 42\n\"\"\"comment\nsecond\"\"\"\nreturn 1"));
    }
    void cCommentsAndCaseInsensitiveSql() {
        QTextDocument doc;
        CodeHighlighter highlighter;
        highlighter.setDocument(&doc);
        highlighter.setLanguage("c++");
        doc.setPlainText("/* comment\nend */ int x = 42; // return\nreturn x;");
        highlighter.rehighlight();
        QCOMPARE(doc.firstBlock().userState(), 1);
        QCOMPARE(doc.findBlockByNumber(1).userState(), 0);
        QVERIFY(doc.findBlockByNumber(1).layout()->formats().size() >= 4);
        highlighter.setLanguage("sql");
        doc.setPlainText("SELECT 'it''s fine' FROM items WHERE id = 12 -- comment");
        highlighter.rehighlight();
        QVERIFY(doc.firstBlock().layout()->formats().size() >= 6);
    }
};
QTEST_MAIN(ChatContentTests)
#include "ChatContentTests.moc"
