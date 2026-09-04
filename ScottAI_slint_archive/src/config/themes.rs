use serde::{Deserialize, Serialize};

/// Зеркало Slint-перечисления `AppStyle` (ui/theme.slint) на стороне Rust —
/// нужно отдельно, т.к. сгенерированный Slint-тип не реализует Serialize/Deserialize.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AppStyle {
    Classic,
    Glass,
    TerminalPro,
}

impl Default for AppStyle {
    fn default() -> Self {
        AppStyle::Classic
    }
}
