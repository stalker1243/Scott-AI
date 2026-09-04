use crate::config::settings::Settings;
use crate::network::api::BackendClient;
use crate::utils::system_info::SystemInfo;

/// Общее состояние приложения, живущее на UI-потоке за `Rc<RefCell<...>>`.
/// `BackendClient` дёшево клонируется (внутри `Arc`) для передачи в spawned-таски tokio.
pub struct AppState {
    pub settings: Settings,
    pub backend: BackendClient,
    pub sysinfo: SystemInfo,
}

impl AppState {
    pub fn new(settings: Settings) -> Self {
        let backend = BackendClient::new(settings.backend_url.clone());
        Self {
            settings,
            backend,
            sysinfo: SystemInfo::new(),
        }
    }
}
