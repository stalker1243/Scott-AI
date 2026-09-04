use directories::ProjectDirs;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

use super::profile::Profile;
use super::themes::AppStyle;

fn default_true() -> bool {
    true
}

fn default_accent() -> String {
    "#3b82f6".to_string()
}

fn default_backend_url() -> String {
    "http://127.0.0.1:8000".to_string()
}

fn default_glass_opacity() -> f32 {
    0.35
}

/// Настройки лаунчера, персистентно хранимые в `settings.toml` внутри
/// пользовательской конфиг-директории (НЕ рядом с exe/папкой проекта).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Settings {
    #[serde(default)]
    pub style: AppStyle,
    #[serde(default = "default_true")]
    pub dark_mode: bool,
    #[serde(default = "default_accent")]
    pub accent_color: String,
    #[serde(default = "default_backend_url")]
    pub backend_url: String,
    /// Уровень прозрачности стиля Glass (0.0 — максимально прозрачно, 1.0 — почти
    /// непрозрачно). Влияет и на тонирующий слой в Slint, и на альфу нативного
    /// acrylic-блюра окна (см. apply_native_blur в src/app.rs).
    #[serde(default = "default_glass_opacity")]
    pub glass_opacity: f32,
    #[serde(default)]
    pub profile: Profile,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            style: AppStyle::default(),
            dark_mode: true,
            accent_color: default_accent(),
            backend_url: default_backend_url(),
            glass_opacity: default_glass_opacity(),
            profile: Profile::default(),
        }
    }
}

impl Settings {
    fn config_dir() -> Option<PathBuf> {
        ProjectDirs::from("pro", "Lutushev", "ScottAI").map(|d| d.config_dir().to_path_buf())
    }

    fn config_file() -> Option<PathBuf> {
        Self::config_dir().map(|d| d.join("settings.toml"))
    }

    pub fn load() -> Self {
        if let Some(file) = Self::config_file() {
            if let Ok(text) = std::fs::read_to_string(&file) {
                match toml::from_str::<Settings>(&text) {
                    Ok(settings) => return settings,
                    Err(err) => {
                        tracing::warn!("Не удалось разобрать settings.toml ({err}), используются значения по умолчанию");
                    }
                }
            }
        }
        Settings::default()
    }

    pub fn save(&self) -> anyhow::Result<()> {
        let Some(dir) = Self::config_dir() else {
            anyhow::bail!("Не удалось определить директорию конфигурации");
        };
        std::fs::create_dir_all(&dir)?;
        let file = dir.join("settings.toml");
        let text = toml::to_string_pretty(self)?;
        std::fs::write(file, text)?;
        Ok(())
    }
}
