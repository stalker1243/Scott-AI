#include <QCoreApplication>
#include <QThread>
#include <cstdio>
#ifdef Q_OS_WIN
#include <qt_windows.h>
#endif
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
#ifdef Q_OS_WIN
    if (GetConsoleWindow()) { std::puts("{\"type\":\"error\",\"message\":\"Unexpected console window\"}"); return 1; }
#endif
    if (app.arguments().contains("--check")) {
        if (qEnvironmentVariableIsSet("SCOTT_SETUP_PROBE_READY")) return 0;
        const auto mode = qEnvironmentVariable("SCOTT_SETUP_PROBE_MODE", "auto").toUtf8();
        std::printf("{\"type\":\"check\",\"ready\":false,\"runtime_mode\":\"%s\",\"space\":{\"compact\":{\"hint\":\"Compact capacity estimate\"},\"cpu\":{\"hint\":\"CPU capacity estimate\"},\"auto\":{\"hint\":\"GPU capacity estimate\"}}}\n",mode.constData()); return 2;
    }
    if (qEnvironmentVariableIsSet("SCOTT_SETUP_PROBE_EXPECT_CPU") && qEnvironmentVariable("SCOTT_TORCH_BACKEND") != "cpu") { std::puts("{\"type\":\"error\",\"message\":\"CPU option missing\"}"); return 1; }
    const auto expected = qEnvironmentVariable("SCOTT_SETUP_PROBE_EXPECT_MODE");
    if (!expected.isEmpty()) {
        const auto index = app.arguments().indexOf("--runtime-mode");
        if (index < 0 || app.arguments().value(index+1) != expected
            || qEnvironmentVariable("SCOTT_RUNTIME_PROFILE") != (expected == "compact" ? "compact" : "full")
            || qEnvironmentVariable("SCOTT_TORCH_BACKEND") != (expected == "auto" ? "auto" : "cpu")
            || (expected != "auto" && qEnvironmentVariable("WHISPER_DEVICE") != "cpu")
            || (expected == "compact" && qEnvironmentVariable("WHISPER_ENGINE") != "faster")) {
            std::puts("{\"type\":\"error\",\"message\":\"Runtime selection missing\"}"); return 1;
        }
    }
    std::puts("{\"type\":\"progress\",\"message\":\"Preparing\",\"fraction\":0.5}"); std::fflush(stdout);
    if (qEnvironmentVariableIsSet("SCOTT_SETUP_PROBE_WAIT")) QThread::sleep(30);
    if (qEnvironmentVariableIsSet("SCOTT_SETUP_PROBE_FAIL")) { std::puts("{\"type\":\"error\",\"message\":\"Network unavailable\"}"); return 1; }
    std::puts("{\"type\":\"done\"}"); return 0;
}
