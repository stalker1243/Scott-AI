#pragma once
#include <QSyntaxHighlighter>
#include <QQuickTextDocument>
#include <QPointer>
#include <QSet>

class CodeHighlighter : public QSyntaxHighlighter {
    Q_OBJECT
    Q_PROPERTY(QQuickTextDocument *source READ source WRITE setSource NOTIFY sourceChanged)
    Q_PROPERTY(QString language READ language WRITE setLanguage NOTIFY languageChanged)
    Q_PROPERTY(bool dark READ dark WRITE setDark NOTIFY darkChanged)
public:
    explicit CodeHighlighter(QObject *parent = nullptr);
    QQuickTextDocument *source() const { return m_source; }
    void setSource(QQuickTextDocument *source);
    QString language() const { return m_language; }
    void setLanguage(const QString &language);
    bool dark() const { return m_dark; }
    void setDark(bool dark);
signals:
    void sourceChanged();
    void languageChanged();
    void darkChanged();
protected:
    void highlightBlock(const QString &text) override;
private:
    QPointer<QQuickTextDocument> m_source;
    QString m_language;
    QSet<QString> m_keywords;
    bool m_dark = true;
};
