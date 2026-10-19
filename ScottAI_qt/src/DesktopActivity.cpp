#include "DesktopActivity.h"
#include <QCoreApplication>
#include <QGuiApplication>
#include <QtConcurrent/QtConcurrentRun>
#include <cstdlib>
#include <cstring>
#ifdef Q_OS_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <dwmapi.h>
#elif defined(SCOTT_HAVE_XCB)
#include <xcb/xcb.h>
#endif

DesktopActivity::DesktopActivity(QObject *parent,Sampler sampler,int interval)
    :QObject(parent),m_sampler(sampler?sampler:visibleApplications),m_custom(bool(sampler)) {
    m_timer.setInterval(qMax(20,interval));
    connect(&m_timer,&QTimer::timeout,this,&DesktopActivity::scan);
    connect(&m_scan,&QFutureWatcher<Snapshot>::finished,this,[this]{
        if(!m_enabled || m_scanGeneration!=m_generation)return;
        const auto current=m_scan.result();
        const bool opened=!m_seed && !(current-m_known).isEmpty();
        m_known=current;m_seed=false;
        if(opened && (!m_cooldown.isValid() || m_cooldown.elapsed()>=2000)){
            m_cooldown.start();emit applicationOpened();
        }
    });
}
DesktopActivity::~DesktopActivity(){m_timer.stop();m_scan.waitForFinished();}
bool DesktopActivity::supported() const {
    if(m_custom)return true;
#ifdef Q_OS_WIN
    return QGuiApplication::platformName()=="windows";
#elif defined(SCOTT_HAVE_XCB)
    return QGuiApplication::platformName()=="xcb";
#else
    return false;
#endif
}
void DesktopActivity::setEnabled(bool enabled) {
    enabled=enabled&&supported();if(enabled==m_enabled)return;
    ++m_generation;m_enabled=enabled;m_seed=true;m_known.clear();m_cooldown.invalidate();
    if(enabled){scan();m_timer.start();}else m_timer.stop();
}
void DesktopActivity::scan(){
    if(!m_enabled || m_scan.isRunning())return;
    m_scanGeneration=m_generation;m_scan.setFuture(QtConcurrent::run(m_sampler));
}
DesktopActivity::Snapshot DesktopActivity::visibleApplications() {
    Snapshot result;
#ifdef Q_OS_WIN
    struct Context{Snapshot *result;DWORD own;};Context context{&result,GetCurrentProcessId()};
    EnumWindows([](HWND window,LPARAM parameter)->BOOL{
        auto *context=reinterpret_cast<Context *>(parameter);
        if(!IsWindowVisible(window) || GetWindow(window,GW_OWNER) || (GetWindowLongPtrW(window,GWL_EXSTYLE)&WS_EX_TOOLWINDOW))return TRUE;
        DWORD cloaked=0;if(SUCCEEDED(DwmGetWindowAttribute(window,DWMWA_CLOAKED,&cloaked,sizeof(cloaked))) && cloaked)return TRUE;
        RECT bounds{};if(!GetWindowRect(window,&bounds) || bounds.right<=bounds.left || bounds.bottom<=bounds.top)return TRUE;
        wchar_t name[128]{};GetClassNameW(window,name,128);
        if(!wcscmp(name,L"Progman") || !wcscmp(name,L"WorkerW") || !wcscmp(name,L"Shell_TrayWnd") || !wcscmp(name,L"Shell_SecondaryTrayWnd"))return TRUE;
        DWORD pid=0;GetWindowThreadProcessId(window,&pid);
        if(pid && pid!=context->own)context->result->insert(reinterpret_cast<quintptr>(window));
        return TRUE;
    },reinterpret_cast<LPARAM>(&context));
#elif defined(SCOTT_HAVE_XCB)
    int screenNumber=0;auto *connection=xcb_connect(nullptr,&screenNumber);
    if(!connection || xcb_connection_has_error(connection)){if(connection)xcb_disconnect(connection);return result;}
    auto screens=xcb_setup_roots_iterator(xcb_get_setup(connection));
    while(screenNumber-- && screens.rem)xcb_screen_next(&screens);
    if(!screens.rem){xcb_disconnect(connection);return result;}
    const auto root=screens.data->root;
    auto atom=[&](const char *name){auto *reply=xcb_intern_atom_reply(connection,xcb_intern_atom(connection,0,quint16(strlen(name)),name),nullptr);const auto value=reply?reply->atom:xcb_atom_t(0);free(reply);return value;};
    const auto pidAtom=atom("_NET_WM_PID"),clientsAtom=atom("_NET_CLIENT_LIST"),typeAtom=atom("_NET_WM_WINDOW_TYPE"),normalAtom=atom("_NET_WM_WINDOW_TYPE_NORMAL"),dialogAtom=atom("_NET_WM_WINDOW_TYPE_DIALOG");
    QList<xcb_window_t> windows;
    auto *clients=xcb_get_property_reply(connection,xcb_get_property(connection,0,root,clientsAtom,XCB_ATOM_WINDOW,0,2048),nullptr);
    if(clients && clients->format==32){const auto *ids=static_cast<xcb_window_t *>(xcb_get_property_value(clients));for(int n=0;n<xcb_get_property_value_length(clients)/4;++n)windows.append(ids[n]);}free(clients);
    if(windows.isEmpty()){
        auto *tree=xcb_query_tree_reply(connection,xcb_query_tree(connection,root),nullptr);
        if(tree){const auto *ids=xcb_query_tree_children(tree);for(int n=0;n<xcb_query_tree_children_length(tree);++n)windows.append(ids[n]);}free(tree);
    }
    struct Request{xcb_window_t window;xcb_get_window_attributes_cookie_t attributes;xcb_get_property_cookie_t pid,type;};
    QList<Request> pending;
    for(auto window:windows)pending.append({window,xcb_get_window_attributes(connection,window),xcb_get_property(connection,0,window,pidAtom,XCB_ATOM_CARDINAL,0,1),xcb_get_property(connection,0,window,typeAtom,XCB_ATOM_ATOM,0,8)});
    for(const auto &request:pending){
        auto *attributes=xcb_get_window_attributes_reply(connection,request.attributes,nullptr);
        auto *pid=xcb_get_property_reply(connection,request.pid,nullptr);
        auto *type=xcb_get_property_reply(connection,request.type,nullptr);
        bool normal=!type || !xcb_get_property_value_length(type);
        if(type && type->format==32){const auto *atoms=static_cast<xcb_atom_t *>(xcb_get_property_value(type));for(int n=0;n<xcb_get_property_value_length(type)/4;++n)normal|=atoms[n]==normalAtom || atoms[n]==dialogAtom;}
        if(attributes && attributes->map_state==XCB_MAP_STATE_VIEWABLE && !attributes->override_redirect && normal && pid && pid->format==32 && xcb_get_property_value_length(pid)==4){
            const auto value=*static_cast<const quint32 *>(xcb_get_property_value(pid));if(value && value!=QCoreApplication::applicationPid())result.insert(request.window);
        }
        free(attributes);free(pid);free(type);
    }
    xcb_disconnect(connection);
#endif
    return result;
}
