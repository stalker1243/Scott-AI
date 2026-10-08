#include "ProfileAvatar.h"
#include <QBuffer>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QImageReader>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPainter>
#include <QPainterPath>
#include <QSaveFile>
#include <cmath>

ProfileAvatar::ProfileAvatar(QString directory, bool temporary, QString legacyDirectory)
    : m_directory(std::move(directory)), m_temporary(temporary) {
    if (temporary) return;
    const QString fileName = m_directory + "/avatar.json";
    QFile file(fileName);
    if (file.exists()) {
        bool valid = false;
        if (file.size() <= 32 * 1024 * 1024 && file.open(QIODevice::ReadOnly)) {
            const auto data = QJsonDocument::fromJson(file.readAll()).object();
            const auto bytes = QByteArray::fromBase64(data.value("png").toString().toLatin1());
            QBuffer buffer; buffer.setData(bytes); buffer.open(QIODevice::ReadOnly);
            QImageReader reader(&buffer, "PNG");
            const auto size = reader.size();
            if (size.isValid() && qint64(size.width()) * size.height() <= 25000000) m_image = reader.read();
            valid = data.value("png").isString() && (data.value("png").toString().isEmpty() || !m_image.isNull());
            setCrop(data.value("zoom").toDouble(1), data.value("x").toDouble(), data.value("y").toDouble());
        }
        if (!valid) m_error = QStringLiteral("Не удалось прочитать фото. Можно выбрать другое.");
    } else if (!legacyDirectory.isEmpty() && QFileInfo::exists(legacyDirectory + "/avatar.png")) {
        loadFile(legacyDirectory + "/avatar.png");
        QFile legacy(legacyDirectory + "/launcher.json");
        if (legacy.size() < 1024 * 1024 && legacy.open(QIODevice::ReadOnly)) {
            const auto data = QJsonDocument::fromJson(legacy.readAll()).object();
            setCrop(data.value("AvatarZoom").toDouble(1), data.value("AvatarOffsetX").toDouble(), data.value("AvatarOffsetY").toDouble());
        }
    }
    m_dirty = false;
    m_savedImage = m_image; m_savedZoom = m_zoom; m_savedX = m_x; m_savedY = m_y;
}
bool ProfileAvatar::choose() {
    if (m_temporary) return false;
    const auto path = QFileDialog::getOpenFileName(nullptr, QStringLiteral("Фото профиля"), {}, QStringLiteral("Изображения (*.png *.jpg *.jpeg *.webp *.bmp)"));
    return !path.isEmpty() && loadFile(path);
}
bool ProfileAvatar::loadFile(const QString &path) {
    QImageReader reader(path);
    reader.setAutoTransform(true);
    const auto size = reader.size();
    if (QFileInfo(path).size() > 16 * 1024 * 1024 || !size.isValid() || qint64(size.width()) * size.height() > 25000000) {
        m_error = QStringLiteral("Выберите изображение до 16 МБ и 25 мегапикселей."); emit changed(); return false;
    }
    const auto image = reader.read();
    if (image.isNull()) { m_error = QStringLiteral("Файл не удалось открыть как изображение."); emit changed(); return false; }
    m_image = image.width() > 2048 || image.height() > 2048 ? image.scaled(QSize(2048, 2048), Qt::KeepAspectRatio, Qt::SmoothTransformation) : image;
    m_zoom = 1; m_x = m_y = 0; m_error.clear(); m_dirty = true; ++m_revision; ++m_sourceRevision; emit changed(); return true;
}
void ProfileAvatar::remove() {
    m_image = {}; m_zoom = 1; m_x = m_y = 0; m_dirty = true; m_error.clear(); ++m_revision; ++m_sourceRevision; emit changed();
}
void ProfileAvatar::setCrop(double zoom, double x, double y) {
    if (!std::isfinite(zoom) || !std::isfinite(x) || !std::isfinite(y)) return;
    zoom = qBound(1.0, zoom, 4.0);
    const double scale = m_image.isNull() ? 0 : qMax(220.0 / m_image.width(), 220.0 / m_image.height()) * zoom;
    const double slackX = qMax(0.0, (m_image.width() * scale - 220) / 2);
    const double slackY = qMax(0.0, (m_image.height() * scale - 220) / 2);
    x = qBound(-slackX, x, slackX); y = qBound(-slackY, y, slackY);
    if (m_zoom == zoom && m_x == x && m_y == y) return;
    m_zoom = zoom; m_x = x; m_y = y; m_dirty = true; ++m_revision; emit changed();
}
QVariantMap ProfileAvatar::cropSize() const {
    if (m_image.isNull()) return {{"width", 220}, {"height", 220}};
    const double scale = qMax(220.0 / m_image.width(), 220.0 / m_image.height()) * m_zoom;
    return {{"width", m_image.width() * scale}, {"height", m_image.height() * scale}};
}
void ProfileAvatar::zoomAt(double zoom, double x, double y) {
    if (!std::isfinite(zoom) || !std::isfinite(x) || !std::isfinite(y)) return;
    const double ratio = qBound(1.0, zoom, 4.0) / m_zoom;
    setCrop(zoom, x + (m_x - x) * ratio, y + (m_y - y) * ratio);
}
void ProfileAvatar::beginCrop() {
    if (m_editing) return;
    m_editing = true; m_editImage = m_image; m_editZoom = m_zoom; m_editX = m_x; m_editY = m_y; m_editDirty = m_dirty;
}
void ProfileAvatar::finishCrop(bool accept) {
    if (!m_editing) return;
    m_editing = false;
    if (!accept) {
        m_image = m_editImage; m_zoom = m_editZoom; m_x = m_editX; m_y = m_editY; m_dirty = m_editDirty;
        ++m_revision; ++m_sourceRevision; emit changed();
    }
    m_editImage = {};
}
QImage ProfileAvatar::preview() const {
    if (m_image.isNull()) return {};
    QImage result(220, 220, QImage::Format_ARGB32_Premultiplied); result.fill(Qt::transparent);
    QPainter painter(&result); painter.setRenderHint(QPainter::Antialiasing); painter.setRenderHint(QPainter::SmoothPixmapTransform);
    QPainterPath circle; circle.addEllipse(QRectF(0, 0, 220, 220)); painter.setClipPath(circle);
    const double scale = qMax(220.0 / m_image.width(), 220.0 / m_image.height()) * m_zoom;
    const QSizeF size(m_image.width() * scale, m_image.height() * scale);
    painter.drawImage(QRectF((220 - size.width()) / 2 + m_x, (220 - size.height()) / 2 + m_y, size.width(), size.height()), m_image);
    return result;
}
bool ProfileAvatar::save() {
    if (!m_dirty) return true;
    m_error.clear();
    if (!m_temporary) {
        QByteArray png; QBuffer buffer(&png); buffer.open(QIODevice::WriteOnly);
        if ((!m_image.isNull() && !m_image.save(&buffer, "PNG")) || !QDir().mkpath(m_directory)) {
            m_error = QStringLiteral("Не удалось сохранить фото."); emit changed(); return false;
        }
        // One atomic record keeps the source image and its crop together.
        QSaveFile file(m_directory + "/avatar.json");
        const auto bytes = QJsonDocument(QJsonObject{{"png", QString::fromLatin1(png.toBase64())}, {"zoom", m_zoom}, {"x", m_x}, {"y", m_y}}).toJson(QJsonDocument::Compact);
        if (!file.open(QIODevice::WriteOnly) || file.write(bytes) != bytes.size() || !file.commit()) {
            m_error = QStringLiteral("Не удалось сохранить фото. Черновик сохранён в окне."); emit changed(); return false;
        }
    }
    m_dirty = false; m_savedImage = m_image; m_savedZoom = m_zoom; m_savedX = m_x; m_savedY = m_y; emit changed(); return true;
}
void ProfileAvatar::revert() {
    m_image = m_savedImage; m_zoom = m_savedZoom; m_x = m_savedX; m_y = m_savedY;
    m_dirty = false; m_error.clear(); ++m_revision; ++m_sourceRevision; emit changed();
}
