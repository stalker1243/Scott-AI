#pragma once
#include <QObject>
#include <QImage>
#include <QQuickImageProvider>
#include <QVariantMap>

class ProfileAvatar final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool hasAvatar READ hasAvatar NOTIFY changed)
    Q_PROPERTY(bool dirty READ dirty NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QString source READ source NOTIFY changed)
    Q_PROPERTY(QString previewSource READ previewSource NOTIFY changed)
    Q_PROPERTY(QVariantMap crop READ crop NOTIFY changed)
    Q_PROPERTY(QVariantMap cropSize READ cropSize NOTIFY changed)
public:
    explicit ProfileAvatar(QString directory, bool temporary = false, QString legacyDirectory = {});
    bool hasAvatar() const { return !m_image.isNull(); }
    bool dirty() const { return m_dirty; }
    QString error() const { return m_error; }
    QString source() const { return hasAvatar() ? QString("image://avatar/source?v=%1").arg(m_sourceRevision) : QString(); }
    QString previewSource() const { return hasAvatar() ? QString("image://avatar/preview?v=%1").arg(m_revision) : QString(); }
    QVariantMap crop() const { return {{"zoom", m_zoom}, {"x", m_x}, {"y", m_y}}; }
    QVariantMap cropSize() const;
    QImage image() const { return m_image; }
    QImage preview() const;
    Q_INVOKABLE bool choose();
    bool loadFile(const QString &path);
    Q_INVOKABLE void remove();
    Q_INVOKABLE void setCrop(double zoom, double x, double y);
    Q_INVOKABLE void resetCrop() { setCrop(1, 0, 0); }
    Q_INVOKABLE void zoomAt(double zoom, double x, double y);
    Q_INVOKABLE void beginCrop();
    Q_INVOKABLE void finishCrop(bool accept);
    Q_INVOKABLE bool save();
    Q_INVOKABLE void revert();
signals:
    void changed();
private:
    QString m_directory, m_error;
    QImage m_image;
    bool m_temporary = false, m_dirty = false;
    int m_revision = 0;
    int m_sourceRevision = 0;
    double m_zoom = 1, m_x = 0, m_y = 0;
    QImage m_savedImage;
    double m_savedZoom = 1, m_savedX = 0, m_savedY = 0;
    QImage m_editImage;
    double m_editZoom = 1, m_editX = 0, m_editY = 0;
    bool m_editing = false, m_editDirty = false;
};

class AvatarProvider final : public QQuickImageProvider {
public:
    explicit AvatarProvider(ProfileAvatar *avatar) : QQuickImageProvider(Image), m_avatar(avatar) {}
    QImage requestImage(const QString &id, QSize *size, const QSize &) override {
        const auto result = id.startsWith("preview") ? m_avatar->preview() : m_avatar->image();
        if (size) *size = result.size();
        return result;
    }
private:
    ProfileAvatar *m_avatar;
};
