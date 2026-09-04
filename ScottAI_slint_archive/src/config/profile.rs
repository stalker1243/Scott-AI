use serde::{Deserialize, Serialize};

/// Локальный профиль пользователя (пока хранится только на диске рядом с настройками;
/// вход через сторонние сервисы — задел на будущее, см. ui/pages/profile.slint).
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Profile {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub bio: String,
}
