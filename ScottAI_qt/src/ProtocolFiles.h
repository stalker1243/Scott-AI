#pragma once
#include <QObject>
#include <QVariantMap>

class ProtocolFiles : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString error READ error NOTIFY errorChanged)
    Q_PROPERTY(QString notice READ notice NOTIFY errorChanged)
public:
    using QObject::QObject;
    QString error() const { return m_error; }
    QString notice() const { return m_notice; }
    Q_INVOKABLE void chooseImport();
    Q_INVOKABLE void chooseExport(const QString &json);
    bool importFile(const QString &path);
    bool exportFile(const QString &path, const QString &json);
signals:
    void imported(const QVariantMap &draft);
    void errorChanged();
private:
    QString m_error, m_notice;
};
