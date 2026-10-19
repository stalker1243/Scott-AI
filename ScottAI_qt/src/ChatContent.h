#pragma once
#include <QObject>
#include <QVariantList>

class ChatContent : public QObject {
    Q_OBJECT
public:
    using QObject::QObject;
    Q_INVOKABLE QVariantList split(const QString &text) const;
    Q_INVOKABLE bool copyCode(const QString &text) const;
    static QString languageName(const QString &name);
};
