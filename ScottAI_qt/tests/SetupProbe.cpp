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
        std::puts("{\"type\":\"check\",\"ready\":false,\"space\":{\"cpu\":{\"hint\":\"CPU capacity estimate\"},\"auto\":{\"hint\":\"GPU capacity estimate\"}}}"); return 2;
    }
    if (qEnvironmentVariableIsSet("SCOTT_SETUP_PROBE_EXPECT_CPU") && qEnvironmentVariable("SCOTT_TORCH_BACKEND") != "cpu") { std::puts("{\"type\":\"error\",\"message\":\"CPU option missing\"}"); return 1; }
    std::puts("{\"type\":\"progress\",\"message\":\"Preparing\",\"fraction\":0.5}"); std::fflush(stdout);
    if (qEnvironmentVariableIsSet("SCOTT_SETUP_PROBE_WAIT")) QThread::sleep(30);
    if (qEnvironmentVariableIsSet("SCOTT_SETUP_PROBE_FAIL")) { std::puts("{\"type\":\"error\",\"message\":\"Network unavailable\"}"); return 1; }
    std::puts("{\"type\":\"done\"}"); return 0;
}
