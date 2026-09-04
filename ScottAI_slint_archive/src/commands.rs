//! Небольшие чистые функции, используемые при связывании Slint UI и Rust-состояния:
//! конвертация типов темы и работа с цветом акцента.

use slint::Color;

use crate::config::themes::AppStyle as ConfigAppStyle;
use crate::AppStyle as SlintAppStyle;

pub fn slint_style_to_config(style: SlintAppStyle) -> ConfigAppStyle {
    match style {
        SlintAppStyle::Classic => ConfigAppStyle::Classic,
        SlintAppStyle::Glass => ConfigAppStyle::Glass,
        SlintAppStyle::TerminalPro => ConfigAppStyle::TerminalPro,
    }
}

pub fn config_style_to_slint(style: ConfigAppStyle) -> SlintAppStyle {
    match style {
        ConfigAppStyle::Classic => SlintAppStyle::Classic,
        ConfigAppStyle::Glass => SlintAppStyle::Glass,
        ConfigAppStyle::TerminalPro => SlintAppStyle::TerminalPro,
    }
}

pub fn color_to_hex(color: Color) -> String {
    format!("#{:02x}{:02x}{:02x}", color.red(), color.green(), color.blue())
}

pub fn hex_to_color(hex: &str) -> Color {
    let hex = hex.trim_start_matches('#');
    if hex.len() != 6 {
        return Color::from_rgb_u8(59, 130, 246); // дефолтный синий акцент
    }
    let r = u8::from_str_radix(&hex[0..2], 16).unwrap_or(59);
    let g = u8::from_str_radix(&hex[2..4], 16).unwrap_or(130);
    let b = u8::from_str_radix(&hex[4..6], 16).unwrap_or(246);
    Color::from_rgb_u8(r, g, b)
}

pub fn current_time() -> String {
    chrono::Local::now().format("%H:%M").to_string()
}
