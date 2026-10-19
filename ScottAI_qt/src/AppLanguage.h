#pragma once
#include <QObject>
#include <QSettings>
#include <QTimer>
#include <QTranslator>
#include <QVariantList>
#include <memory>

class AppLanguage : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString language READ language NOTIFY languageChanged)
    Q_PROPERTY(QString locale READ locale NOTIFY languageChanged)
    Q_PROPERTY(QVariantList languages READ languages CONSTANT)
public:
    explicit AppLanguage(bool temporary=false, const QString &settingsFile={}, QObject *parent=nullptr);
    ~AppLanguage() override;
    QString language() const { return m_language; }
    QString locale() const;
    QVariantList languages() const;
    Q_INVOKABLE bool setLanguage(const QString &language);
    static QString text(const QString &source);
signals:
    void languageChanged();
private:
    bool apply(const QString &language, bool persist);
    bool m_temporary;
    QString m_language;
    std::unique_ptr<QSettings> m_settings;
    std::unique_ptr<QTranslator> m_translator;
    QTimer m_watch;
};
