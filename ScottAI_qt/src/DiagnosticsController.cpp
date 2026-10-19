#include "DiagnosticsController.h"
#include "AppLog.h"
#include "ProcessSupport.h"
#include <QFileDialog>
#include <QDesktopServices>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QStandardPaths>
#include <QUrl>

DiagnosticsController::DiagnosticsController(QObject *parent) : QObject(parent) {
    backgroundProcess(m_process);
    m_timeout.setSingleShot(true);
    connect(&m_timeout, &QTimer::timeout, this, [this] {
        m_error = QStringLiteral("Сбор диагностики занял слишком много времени. Повторите попытку.");
        m_process.kill();
    });
    connect(&m_process, &QProcess::readyReadStandardOutput, this, [this] {
        m_output += m_process.readAllStandardOutput();
        if (m_output.size() > 4 * 1024 * 1024) { m_error = QStringLiteral("Ответ диагностики слишком большой."); m_process.kill(); }
    });
    connect(&m_process, &QProcess::readyReadStandardError, this, [this] { m_process.readAllStandardError(); });
    connect(&m_process, &QProcess::finished, this, [this](int code, QProcess::ExitStatus) { finish(code); });
    connect(&m_process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        if (error == QProcess::FailedToStart) {
            m_timeout.stop(); m_busy = false;
            m_error = QStringLiteral("Не удалось запустить Python для диагностики. Проверьте установку приложения."); emit changed();
        }
    });
}
DiagnosticsController::~DiagnosticsController() {
    if (m_process.state() != QProcess::NotRunning) { m_process.kill(); m_process.waitForFinished(1500); }
}
void DiagnosticsController::configure(const QString &python, const QString &backend) {
    m_python = python.isEmpty() ? QStandardPaths::findExecutable("python") : python;
    m_backend = backend;
}
void DiagnosticsController::run(const QStringList &arguments, bool exporting) {
    if (m_busy) return;
    m_error.clear(); m_notice.clear(); m_output.clear(); m_exporting = exporting;
    if (!QFileInfo::exists(m_python) || !QFileInfo::exists(m_backend + "/diagnostics.py")) {
        m_error = QStringLiteral("Не найдены Python или модуль диагностики."); emit changed(); return;
    }
    auto env = QProcessEnvironment::systemEnvironment();
    env.insert("PYTHONIOENCODING", "utf-8"); env.insert("PYTHONUTF8", "1");
    env.insert("SCOTT_LOG_DIR", AppLog::directory.isEmpty() ? AppLog::defaultDirectory() : AppLog::directory);
    m_process.setProcessEnvironment(env); m_process.setWorkingDirectory(m_backend);
    m_busy = true; emit changed();
    m_timeout.start(45000);
    m_process.start(m_python, QStringList{"-u", m_backend + "/diagnostics.py", "--json"} + arguments);
}
void DiagnosticsController::refresh(const QString &name) { run({"--log", name}, false); }
void DiagnosticsController::exportArchive() {
    if (m_busy) return;
    const auto path = QFileDialog::getSaveFileName(nullptr, QStringLiteral("Сохранить диагностику ScottAI"),
        QStandardPaths::writableLocation(QStandardPaths::DownloadLocation) + "/ScottAI-diagnostics-" + QDateTime::currentDateTime().toString("yyyyMMdd-HHmmss") + ".zip", "ZIP (*.zip)");
    if (!path.isEmpty()) exportTo(path);
}
void DiagnosticsController::exportTo(const QString &path) { if (!path.isEmpty()) run({"--output", path}, true); }
void DiagnosticsController::openFolder() {
    const auto path = m_archive.isEmpty() ? AppLog::defaultDirectory() : QFileInfo(m_archive).absolutePath();
    QDesktopServices::openUrl(QUrl::fromLocalFile(path));
}
void DiagnosticsController::finish(int code) {
    m_timeout.stop(); m_busy = false;
    m_output += m_process.readAllStandardOutput();
    const auto data = QJsonDocument::fromJson(m_output).object();
    if (code != 0 || !data.value("success").toBool()) {
        if (m_error.isEmpty()) m_error = data.value("message").toString(QStringLiteral("Не удалось собрать диагностику."));
    } else if (m_exporting) {
        m_archive = data.value("path").toString();
        m_notice = QStringLiteral("Архив сохранён. Его можно приложить к сообщению о проблеме.");
    } else {
        m_logs = data.value("logs").toArray().toVariantList();
        m_selected = data.value("selected").toString(m_selected);
        const auto log = data.value("log").toObject();
        QStringList lines; for (const auto &line : log.value("lines").toArray()) lines.append(line.toString());
        m_text = lines.isEmpty() ? log.value("message").toString(QStringLiteral("Журнал пока пуст.")) : lines.join('\n');
    }
    emit changed();
}
