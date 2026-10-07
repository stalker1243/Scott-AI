#include "SetupController.h"
#include <QJsonDocument>
#include <QJsonObject>
#include <QFileInfo>

SetupController::SetupController(QObject *parent) : QObject(parent) {
    connect(&m_process, &QProcess::readyReadStandardOutput, this, [this] {
        m_buffer += m_process.readAllStandardOutput();
        while (m_buffer.contains('\n')) {
            const auto end = m_buffer.indexOf('\n'); const auto line = m_buffer.left(end); m_buffer.remove(0, end + 1);
            const auto value = QJsonDocument::fromJson(line).object();
            if (value.value("type").toString() == "progress") {
                m_message = value.value("message").toString(); m_progress = qBound(0.0, value.value("fraction").toDouble(), 1.0); emit changed();
            } else if (value.value("type").toString() == "error") m_error = value.value("message").toString();
        }
    });
    connect(&m_process, &QProcess::readyReadStandardError, this, [this] { m_process.readAllStandardError(); });
    connect(&m_process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        if (error == QProcess::FailedToStart) { m_busy = false; m_error = QStringLiteral("Не удалось запустить подготовку. Проверьте runtime/python.exe."); emit changed(); }
    });
    connect(&m_process, &QProcess::finished, this, [this](int code, QProcess::ExitStatus status) {
        m_busy = false;
        if (code == 0 && status == QProcess::NormalExit) { m_visible = false; m_progress = 1; emit changed(); emit ready(); return; }
        if (m_check && code == 2) { m_message = QStringLiteral("Подготовим библиотеки и модели речи для вашего компьютера."); m_error.clear(); }
        else if (m_error.isEmpty()) m_error = QStringLiteral("Подготовка не завершена. Проверьте подключение к интернету и повторите попытку.");
        emit changed();
    });
}
SetupController::~SetupController() { cancel(); }
void SetupController::check(const QString &python, const QString &backend) { m_python = python; m_backend = backend; run(true); }
void SetupController::run(bool check) {
    if (m_process.state() != QProcess::NotRunning) return;
    m_check = check; m_visible = true; m_busy = true; m_progress = 0; m_error.clear(); m_buffer.clear();
    m_message = check ? QStringLiteral("Проверяем готовность…") : QStringLiteral("Начинаем подготовку…"); emit changed();
    auto env = QProcessEnvironment::systemEnvironment(); env.insert("PYTHONIOENCODING", "utf-8"); m_process.setProcessEnvironment(env);
    m_process.setWorkingDirectory(m_backend);
    QStringList arguments{"-u", m_backend + "/bootstrap.py", "--json"}; if (check) arguments.append("--check");
    m_process.start(m_python, arguments);
}
void SetupController::prepare() { if (!m_python.isEmpty()) run(false); }
void SetupController::cancel() {
    if (m_process.state() == QProcess::NotRunning) return;
    // Only the process tree started by this controller belongs to preparation.
#ifdef Q_OS_WIN
    QProcess stop; stop.start("taskkill", {"/PID", QString::number(m_process.processId()), "/T", "/F"}); stop.waitForFinished(3000);
#else
    m_process.kill();
#endif
    m_process.waitForFinished(1500);
}
