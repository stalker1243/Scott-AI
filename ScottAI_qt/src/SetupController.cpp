#include "SetupController.h"
#include "ProcessSupport.h"
#include "AppLog.h"
#include <QJsonDocument>
#include <QJsonObject>
#include <QFileInfo>
#ifndef Q_OS_WIN
#include <signal.h>
#include <unistd.h>
#endif

SetupController::SetupController(QObject *parent) : QObject(parent) {
    backgroundProcess(m_process);
    m_tick.setInterval(1000);
    connect(&m_tick, &QTimer::timeout, this, &SetupController::changed);
    connect(&m_process, &QProcess::readyReadStandardOutput, this, [this] {
        const auto bytes = m_process.readAllStandardOutput();
        m_buffer += bytes;
        while (m_buffer.contains('\n')) {
            const auto end = m_buffer.indexOf('\n'); const auto line = m_buffer.left(end); m_buffer.remove(0, end + 1);
            AppLog::append("setup.log", QString::fromUtf8(line));
            const auto value = QJsonDocument::fromJson(line).object();
            if (value.value("type").toString() == "progress") {
                m_message = value.value("message").toString(); m_progress = qBound(0.0, value.value("fraction").toDouble(), 1.0); emit changed();
            } else if (value.value("type").toString() == "check") {
                const auto mode = value.value("runtime_mode").toString();
                if (!m_modeSelected && (mode == "auto" || mode == "cpu" || mode == "compact")) m_runtimeMode = mode;
                m_space = value.value("space").toObject(); emit changed();
            } else if (value.value("type").toString() == "error") m_error = value.value("message").toString();
        }
    });
    connect(&m_process, &QProcess::readyReadStandardError, this, [this] { AppLog::appendChunk("setup.log", m_errorBuffer, m_process.readAllStandardError()); });
    connect(&m_process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        if (error == QProcess::FailedToStart) { m_tick.stop(); m_busy = false; m_error = QStringLiteral("Не удалось запустить Python для подготовки. Повторите установку приложения."); emit changed(); }
    });
    connect(&m_process, &QProcess::finished, this, [this](int code, QProcess::ExitStatus status) {
        m_tick.stop();
        AppLog::appendChunk("setup.log", m_errorBuffer, "\n");
        m_busy = false;
        if (m_cancelled) { m_message = QStringLiteral("Подготовка остановлена. Нажмите «Продолжить» — скачанная часть модели сохранена."); m_error.clear(); emit changed(); return; }
        if (code == 0 && status == QProcess::NormalExit) {
            m_prepared = true; m_launching = true; m_busy = true; m_progress = 0;
            m_message = QStringLiteral("Подключаем backend…"); emit changed(); emit ready(); return;
        }
        if (m_check && code == 2) { m_message = QStringLiteral("Подготовим библиотеки и модели речи для вашего компьютера."); m_error.clear(); }
        else if (m_error.isEmpty()) m_error = QStringLiteral("Подготовка не завершена. Соберите логи — в них сохранена причина ошибки. Затем повторите попытку.");
        emit changed();
    });
}
QString SetupController::sizeHint() const {
    const auto hint = m_space.value(m_runtimeMode).toObject().value("hint").toString();
    if (!hint.isEmpty()) return hint;
    if (m_runtimeMode == "compact") return QStringLiteral("Компактный backend с моделью small: около 1 ГиБ на Windows, без Qt и Scott Voice. Для подготовки оставьте 2,5 ГиБ свободно. На других системах размер может отличаться. Уже установленные пакеты не удаляются.");
    return compact() ? QStringLiteral("Чат и распознавание: около 2 ГиБ. На время подготовки оставьте 2,5 ГиБ свободно.")
        : QStringLiteral("Чат и распознавание: около 2 ГиБ на CPU или 5–7 ГиБ на GPU. Scott Voice готовится отдельно.");
}
void SetupController::setRuntimeMode(const QString &value) {
    if (m_busy || (value != "auto" && value != "cpu" && value != "compact")) return;
    m_runtimeMode = value; m_modeSelected = true; m_prepared = false; emit changed();
}
SetupController::~SetupController() {
    // QProcess is destroyed after the buffers it writes into. A late finished
    // signal must never invoke these callbacks during member destruction.
    disconnect(&m_process, nullptr, this, nullptr);
    cancel();
}
void SetupController::check(const QString &python, const QString &backend) { m_python = python; m_backend = backend; m_prepared = false; m_launching = false; run(true); }
void SetupController::run(bool check) {
    if (m_process.state() != QProcess::NotRunning) return;
    m_check = check; m_cancelled = false; m_visible = true; m_busy = true; m_progress = 0; m_error.clear(); m_buffer.clear();
    m_elapsed.start(); m_tick.start();
    m_message = check ? QStringLiteral("Проверяем готовность…") : QStringLiteral("Начинаем подготовку…"); emit changed();
    auto env = QProcessEnvironment::systemEnvironment(); env.insert("PYTHONIOENCODING", "utf-8");
    env.insert("SCOTT_LOG_DIR", AppLog::directory.isEmpty() ? AppLog::defaultDirectory() : AppLog::directory);
    // The stdlib bootstrap owns persistence. Do not depend on python-dotenv
    // before pip, and never modify the parent process environment or .env.
    if (m_modeSelected) {
        env.insert("SCOTT_RUNTIME_PROFILE", m_runtimeMode == "compact" ? "compact" : "full");
        env.insert("SCOTT_TORCH_BACKEND", m_runtimeMode == "auto" ? "auto" : "cpu");
        if (m_runtimeMode != "auto") env.insert("WHISPER_DEVICE", "cpu");
        if (m_runtimeMode == "compact") env.insert("WHISPER_ENGINE", "faster");
    }
    env.insert("SCOTT_SETUP_GROUP", "1"); m_process.setProcessEnvironment(env);
    m_process.setWorkingDirectory(m_backend);
    QStringList arguments{"-u", m_backend + "/bootstrap.py", "--json"}; if (check) arguments.append("--check");
    if (!check && m_modeSelected) arguments << "--runtime-mode" << m_runtimeMode;
    m_process.start(m_python, arguments);
}
void SetupController::prepare() {
    if (m_busy) return;
    if (m_prepared) {
        m_busy = true; m_launching = true; m_error.clear(); m_progress = 0;
        m_message = QStringLiteral("Подключаем backend…"); emit changed(); emit ready();
    } else if (!m_python.isEmpty()) run(false);
}
void SetupController::backendReady() {
    if (!m_launching) return;
    m_launching = false; m_busy = false; m_visible = false; m_progress = 1; m_tick.stop();
    m_error.clear(); emit changed();
}
void SetupController::backendFailed(const QString &error) {
    if (!m_launching) return;
    m_launching = false; m_busy = false; m_visible = true; m_tick.stop();
    m_error = error; emit changed();
}
void SetupController::cancel() {
    m_launching = false; m_busy = false; m_tick.stop();
    if (m_process.state() == QProcess::NotRunning) return;
    m_cancelled = true;
    // Only the process tree started by this controller belongs to preparation.
#ifdef Q_OS_WIN
    const auto pid=m_process.processId();
    if(pid>0) {
        QProcess stop; backgroundProcess(stop); stop.start("taskkill", {"/PID", QString::number(pid), "/T", "/F"});
        if(!stop.waitForFinished(3000)) { stop.kill();stop.waitForFinished(1000); }
    }
    // taskkill can be unavailable or fail under a restricted account. The
    // QProcess handle still identifies only our own preparation process.
    if(m_process.state()!=QProcess::NotRunning)m_process.kill();
#else
    const auto pid = static_cast<pid_t>(m_process.processId());
    if (pid > 0 && getpgid(pid) == pid) ::kill(-pid, SIGKILL);
    else m_process.kill();
#endif
    m_process.waitForFinished(1500);
}
