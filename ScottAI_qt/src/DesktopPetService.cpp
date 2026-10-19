#include "DesktopPetService.h"
#include "PetController.h"
#include <QApplication>
#include <QCursor>
#include <QDir>
#include <QFile>
#include <QDateTime>
#include <QRegularExpression>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLocalSocket>
#include <QQuickWindow>
#include <QScreen>
#include <memory>
#include <cmath>

namespace {
bool wayland() { return QGuiApplication::platformName().startsWith("wayland"); }
QPoint fit(QPoint point,QSize size,const QRect &area) {
    return {qBound(area.left(),point.x(),qMax(area.left(),area.right()-size.width()+1)),
            qBound(area.top(),point.y(),qMax(area.top(),area.bottom()-size.height()+1))};
}
}

DesktopPetService::DesktopPetService(QString root,bool trackDesktop)
    :m_root(std::move(root)),m_settings(m_root+"/settings.ini",QSettings::IniFormat),m_lock(m_root+"/service.lock"),m_desktopActivity(this),m_trackDesktop(trackDesktop) {
    m_kind=m_settings.value("kind","scott").toString();
    if(PetController::variants(m_kind).isEmpty())m_kind="scott";
    m_variant=m_settings.value("variant",PetController::variants(m_kind).first()).toString();
    if(!PetController::variants(m_kind).contains(m_variant))m_variant=PetController::variants(m_kind).first();
    m_motion=m_settings.value("motion",true).toBool();
    m_sizePercent=qBound(50,m_settings.value("sizePercent",100).toInt(),200);
    m_server.setSocketOptions(QLocalServer::UserAccessOption);
    connect(&m_server,&QLocalServer::newConnection,this,[this]{
        while(m_server.hasPendingConnections()) {
            auto *socket=m_server.nextPendingConnection();
            auto bytes=std::make_shared<QByteArray>();
            QTimer::singleShot(2000,socket,&QLocalSocket::abort);
            connect(socket,&QLocalSocket::disconnected,socket,&QObject::deleteLater);
            connect(socket,&QLocalSocket::readyRead,this,[this,socket,bytes]{
                *bytes+=socket->readAll();
                if(bytes->size()>4096){socket->abort();return;}
                if(!bytes->endsWith('\n')||socket->property("done").toBool())return;
                socket->setProperty("done",true);
                const auto request=QJsonDocument::fromJson(*bytes).object();
                const auto op=request["op"].toString();
                const auto size=request["sizePercent"];
                const bool validSize=size.isUndefined() || (size.isDouble() && size.toDouble()==size.toInt()
                    && size.toInt()>=50 && size.toInt()<=200);
                if(op=="configure" && validSize && PetController::variants(request["kind"].toString()).contains(request["variant"].toString()) && request["motion"].isBool()) {
                    m_kind=request["kind"].toString();m_variant=request["variant"].toString();m_motion=request["motion"].toBool();
                    if(!size.isUndefined())m_sizePercent=size.toInt();
                    if(m_motion&&!wayland())m_cursor.start();else m_cursor.stop();
                    m_desktopActivity.setEnabled(m_trackDesktop&&m_ready&&m_motion);
                    resizeWindow();save();emit changed();
                } else if(op=="play")emit play();
                else if(op=="recenter")resetPosition();
                else if(op=="quit")stop();
                QJsonObject state{{"ready",m_ready},{"kind",m_kind},{"variant",m_variant},{"motion",m_motion},
                                  {"sizePercent",m_sizePercent},{"miniChat",true},{"activityEvents",1},{"scottOnly",true},{"localization",1},{"pid",QString::number(QCoreApplication::applicationPid())}};
                socket->write(QJsonDocument(state).toJson(QJsonDocument::Compact)+'\n');
                socket->flush();socket->disconnectFromServer();
            });
        }
    });
    m_position.setSingleShot(true);m_position.setInterval(500);
    connect(&m_position,&QTimer::timeout,this,&DesktopPetService::savePosition);
    m_cursor.setInterval(60);
    m_activityPoll.setInterval(2000);
    connect(&m_activityPoll,&QTimer::timeout,this,[this]{readActivity();});
    connect(&m_activityWatcher,&QFileSystemWatcher::directoryChanged,this,[this]{readActivity();});
    connect(&m_desktopActivity,&DesktopActivity::applicationOpened,this,&DesktopPetService::applicationOpened);
    connect(&m_cursor,&QTimer::timeout,this,[this]{
        // Wayland deliberately provides no desktop-wide pointer tracking.
        // Its local pointer events still animate the eyes while hovering.
        if(!m_window || !m_motion || m_menuOpen || wayland())return;
        pointerMoved(m_window->mapFromGlobal(QCursor::pos()));
    });
}

bool DesktopPetService::start() {
    if(QFileInfo(m_root).isSymLink() || !QDir().mkpath(m_root) || !m_lock.tryLock(0))return false;
    QLocalServer::removeServer(PetController::serverName(m_root));
    if(!m_server.listen(PetController::serverName(m_root)))return false;
    m_settings.setValue("enabled",true);save();
    readActivity(true); // Never replay the previous process's action at startup.
    m_activityWatcher.addPath(m_root);m_activityPoll.start();
    return true;
}

void DesktopPetService::readActivity(bool seed) {
    const QFileInfo info(m_root+"/activity.json");
    if(info.isSymLink() || !info.isFile() || info.size()>1024)return;
    QFile file(info.absoluteFilePath());if(!file.open(QIODevice::ReadOnly))return;
    const auto bytes=file.read(1025);if(bytes.size()>1024)return;
    const auto data=QJsonDocument::fromJson(bytes).object();
    const auto id=data["id"].toString();
    static const QRegularExpression identifier("^[a-f0-9]{32}$");
    if(data["version"].toInt()!=1 || data["event"].toString()!="application_opened" || !identifier.match(id).hasMatch())return;
    if(id==m_lastActivity)return;
    m_lastActivity=id;
    const double created=data["created_ms"].toDouble(-1);
    const double age=QDateTime::currentMSecsSinceEpoch()-created;
    if(seed || !m_ready || !m_motion || !std::isfinite(created) || std::floor(created)!=created || age<0 || age>10000)return;
    emit applicationOpened();
}

void DesktopPetService::attach(QQuickWindow *window) {
    m_window=window;m_ready=true;
    resizeWindow();
    if(!wayland() && QGuiApplication::primaryScreen()) {
        auto *screen=QGuiApplication::primaryScreen();
        const auto area=screen->availableGeometry();
        const auto point=m_settings.value("position",QPoint(area.right()-window->width()-24,area.bottom()-window->height()-24)).toPoint();
        if(auto *saved=QGuiApplication::screenAt(point))screen=saved;
        window->setPosition(fit(point,window->size(),screen->geometry()));
    }
    connect(window,&QWindow::xChanged,&m_position,qOverload<>(&QTimer::start));
    connect(window,&QWindow::yChanged,&m_position,qOverload<>(&QTimer::start));
    connect(qGuiApp,&QGuiApplication::screenRemoved,this,[this]{QTimer::singleShot(0,this,&DesktopPetService::recoverLostWindow);});
    if(m_motion&&!wayland())m_cursor.start();
    m_desktopActivity.setEnabled(m_trackDesktop&&m_motion);
}

bool DesktopPetService::canReposition()const { return !wayland(); }

void DesktopPetService::save() {
    m_settings.setValue("kind",m_kind);m_settings.setValue("variant",m_variant);
    m_settings.setValue("motion",m_motion);m_settings.setValue("sizePercent",m_sizePercent);
    m_settings.sync();QFile::setPermissions(m_settings.fileName(),QFile::ReadOwner|QFile::WriteOwner);
}

void DesktopPetService::savePosition() {
    if(m_window && !wayland()) {
        m_settings.setValue("position",m_window->position());m_settings.sync();
    }
}

void DesktopPetService::resizeWindow() {
    if(!m_window)return;
    auto *screen=m_window->screen();
    if(auto *at=QGuiApplication::screenAt(m_window->geometry().center()))screen=at;
    if(!screen)screen=QGuiApplication::primaryScreen();
    if(!screen)return;
    const auto area=screen->geometry();
    const qreal scale=qMin(m_sizePercent/100.0,qMin(area.width()/280.0,area.height()/260.0));
    const QSize size(qMax(1,qRound(280*scale)),qMax(1,qRound(260*scale)));
    if(size!=m_window->size()) {
        const QPoint anchor(m_window->x()+(m_window->width()-size.width())/2,m_window->y()+m_window->height()-size.height());
        m_window->resize(size);
        if(!wayland())m_window->setPosition(fit(anchor,size,area));
    }
    updateMask();
}

void DesktopPetService::updateMask() {
    if(!m_window || wayland())return;
    const qreal scale=m_window->width()/280.0;
    m_window->setMask(m_menuOpen ? QRegion() : QRegion(QRectF(24*scale,0,232*scale,250*scale).toAlignedRect()));
}

void DesktopPetService::resetPosition() {
    if(!m_window || wayland())return;
    auto *screen=QGuiApplication::screenAt(QCursor::pos());
    if(!screen)screen=QGuiApplication::primaryScreen();
    if(!screen)return;
    const auto area=screen->availableGeometry();
    m_window->setPosition(fit(QPoint(area.right()-m_window->width()-24,area.bottom()-m_window->height()-24),m_window->size(),area));
    savePosition();
}

void DesktopPetService::recoverLostWindow() {
    if(!m_window || wayland())return;
    for(auto *screen:QGuiApplication::screens())if(screen->geometry().intersects(m_window->geometry()))return;
    resetPosition();
}

void DesktopPetService::beginDrag(QPointF local) {
    if(!m_window)return;
    m_pointerDown=true;m_pressGlobal=m_window->mapToGlobal(local.toPoint());m_pressPosition=m_window->position();
}

void DesktopPetService::updateDrag(QPointF local) {
    pointerMoved(local);
    if(!m_window || !m_pointerDown)return;
    const auto delta=m_window->mapToGlobal(local.toPoint())-m_pressGlobal;
    if(!m_dragging && delta.manhattanLength()<QApplication::startDragDistance())return;
    if(!m_dragging) {
        m_dragging=true;emit dragChanged();
        if(wayland())m_window->startSystemMove();
    }
    // Desktop coordinates are logical pixels and may be negative on another
    // monitor. Do not snap to the work area or animate coordinates during drag.
    if(!wayland())m_window->setPosition(m_pressPosition+delta);
}

bool DesktopPetService::endDrag() {
    const bool moved=m_dragging;
    m_pointerDown=false;m_dragging=false;
    if(moved){emit dragChanged();recoverLostWindow();savePosition();}
    return moved;
}

void DesktopPetService::pointerMoved(QPointF local) {
    if(!m_window || !m_motion || m_menuOpen)return;
    const qreal width=qMax(1,m_window->width()),height=qMax(1,m_window->height());
    const QPointF gaze(qBound(-1.0,(local.x()-width*0.5)/(width*0.9),1.0),
                       qBound(-1.0,(local.y()-height*0.4)/(height*0.9),1.0));
    if((gaze-m_gaze).manhattanLength()<0.015)return;
    m_gaze=gaze;emit gazeChanged();
}

void DesktopPetService::menuOpen(bool open) { m_menuOpen=open;updateMask(); }
QPointF DesktopPetService::chatPosition(qreal width,qreal height) const {
    if(!m_window)return {};
    if(wayland())return {(m_window->width()-width)/2, -height+12};
    auto *screen=m_window->screen();if(!screen)screen=QGuiApplication::primaryScreen();
    if(!screen)return {};
    const auto area=screen->availableGeometry();
    QPoint desired(m_window->x()+(m_window->width()-qRound(width))/2,m_window->y()-qRound(height)+12);
    if(desired.y()<area.top()+8)desired.setY(m_window->y()+m_window->height()-12);
    return fit(desired,QSize(qRound(width),qRound(height)),area)-m_window->position();
}
void DesktopPetService::setSizePercent(int value) {
    value=qBound(50,value,200);
    if(value==m_sizePercent)return;
    endDrag();m_sizePercent=value;resizeWindow();save();emit changed();
}
void DesktopPetService::toggleMotion() { m_motion=!m_motion;if(m_motion&&!wayland())m_cursor.start();else m_cursor.stop();m_desktopActivity.setEnabled(m_trackDesktop&&m_motion);save();emit changed(); }
void DesktopPetService::stop() {
    savePosition();m_settings.setValue("enabled",false);m_settings.sync();
    QTimer::singleShot(60,qApp,&QCoreApplication::quit);
}
