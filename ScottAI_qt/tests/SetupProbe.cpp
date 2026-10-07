#include <QCoreApplication>
#include <QThread>
#include <cstdio>
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    if (app.arguments().contains("--check")) { std::puts("{\"type\":\"check\",\"ready\":false}"); return 2; }
    std::puts("{\"type\":\"progress\",\"message\":\"Preparing\",\"fraction\":0.5}"); std::fflush(stdout);
    if (qEnvironmentVariableIsSet("SCOTT_SETUP_PROBE_WAIT")) QThread::sleep(30);
    if (qEnvironmentVariableIsSet("SCOTT_SETUP_PROBE_FAIL")) { std::puts("{\"type\":\"error\",\"message\":\"Network unavailable\"}"); return 1; }
    std::puts("{\"type\":\"done\"}"); return 0;
}
