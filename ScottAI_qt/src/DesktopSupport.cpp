#include "DesktopSupport.h"
#include <QSystemTrayIcon>

DesktopSupport::DesktopSupport(QString platform, TrayProbe probe, QObject *parent)
    : QObject(parent), m_platform(std::move(platform)),
      m_probe(probe ? std::move(probe) : TrayProbe(QSystemTrayIcon::isSystemTrayAvailable)) {
    refresh();
    m_timer.setInterval(1000);
    connect(&m_timer, &QTimer::timeout, this, &DesktopSupport::refresh);
    m_timer.start();
}
void DesktopSupport::refresh() {
    const bool available = m_probe();
    if (available == m_available) return;
    m_available = available;
    emit trayAvailableChanged(available);
}
