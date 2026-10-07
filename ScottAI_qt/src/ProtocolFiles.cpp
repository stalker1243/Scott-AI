#include "ProtocolFiles.h"
#include "ProtocolValidation.h"
#include <QFileDialog>
#include <QFile>
#include <QSaveFile>
#include <QJsonDocument>

void ProtocolFiles::chooseImport() {
    const auto path = QFileDialog::getOpenFileName(nullptr, QStringLiteral("Импорт протокола"), {}, QStringLiteral("Протокол Scott (*.json)"));
    if (!path.isEmpty()) importFile(path);
}
void ProtocolFiles::chooseExport(const QString &json) {
    const auto path = QFileDialog::getSaveFileName(nullptr, QStringLiteral("Экспорт протокола"), "protocol.scott.json", QStringLiteral("Протокол Scott (*.json)"));
    if (!path.isEmpty()) exportFile(path, json);
}
bool ProtocolFiles::importFile(const QString &path) {
    m_error.clear(); m_notice.clear(); QFile file(path); QJsonObject draft;
    if (file.open(QIODevice::ReadOnly) && file.size() <= 1024 * 1024) {
        const auto root = QJsonDocument::fromJson(file.readAll()).object();
        if (root.value("format") == "scott-protocol" && root.value("version").toInt() == 1 && root.value("protocol").isObject())
            draft = protocolDraft(root.value("protocol").toObject());
    }
    if (!protocolDraftValid(draft)) { m_error = QStringLiteral("Файл повреждён или имеет неподдерживаемый формат протокола."); emit errorChanged(); return false; }
    // Imported automation is a draft and must be reviewed before saving.
    draft["enabled"] = false; draft["schedule"] = "";
    m_notice = QStringLiteral("Протокол импортирован в черновик. Проверьте шаги перед сохранением.");
    emit imported(draft.toVariantMap()); emit errorChanged(); return true;
}
bool ProtocolFiles::exportFile(const QString &path, const QString &json) {
    m_error.clear(); m_notice.clear(); const auto draft = QJsonDocument::fromJson(json.toUtf8()).object();
    if (!protocolDraftValid(draft)) { m_error = QStringLiteral("Заполните имя и шаги перед экспортом."); emit errorChanged(); return false; }
    QSaveFile file(path);
    const auto bytes = QJsonDocument(QJsonObject{{"format", "scott-protocol"}, {"version", 1}, {"protocol", draft}}).toJson(QJsonDocument::Indented);
    if (!file.open(QIODevice::WriteOnly) || file.write(bytes) != bytes.size() || !file.commit()) {
        m_error = QStringLiteral("Не удалось записать файл протокола."); emit errorChanged(); return false;
    }
    m_notice = QStringLiteral("Протокол экспортирован."); emit errorChanged(); return true;
}
