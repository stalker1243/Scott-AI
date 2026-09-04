use base64::{engine::general_purpose, Engine as _};
use enigo::{Enigo, Keyboard, Mouse, Settings};
use enigo::{Button, Coordinate, Direction, Key};
use serde::Serialize;
use sysinfo::System;

#[derive(Serialize)]
pub struct ProcessInfo {
    pid: u32,
    name: String,
    cpu_percent: f32,
    memory_mb: u64,
}

/// Список процессов, отсортированный по потреблению CPU (топ-50) — локально
/// через `sysinfo`, без обращения к backend (мгновенный отклик).
#[tauri::command]
pub fn list_processes() -> Vec<ProcessInfo> {
    let mut sys = System::new_all();
    sys.refresh_all();
    // Второй проход нужен psutil-подобным библиотекам для корректного CPU% —
    // sysinfo делает то же самое: разница между двумя замерами.
    std::thread::sleep(std::time::Duration::from_millis(120));
    sys.refresh_cpu_usage();
    sys.refresh_processes(sysinfo::ProcessesToUpdate::All, true);

    let mut processes: Vec<ProcessInfo> = sys
        .processes()
        .values()
        .map(|p| ProcessInfo {
            pid: p.pid().as_u32(),
            name: p.name().to_string_lossy().to_string(),
            cpu_percent: p.cpu_usage(),
            memory_mb: p.memory() / 1024 / 1024,
        })
        .collect();

    processes.sort_by(|a, b| b.cpu_percent.partial_cmp(&a.cpu_percent).unwrap_or(std::cmp::Ordering::Equal));
    processes.truncate(50);
    processes
}

#[tauri::command]
pub fn kill_process(pid: u32) -> Result<(), String> {
    let mut sys = System::new_all();
    sys.refresh_processes(sysinfo::ProcessesToUpdate::All, true);
    let target = sysinfo::Pid::from_u32(pid);
    match sys.process(target) {
        Some(process) => {
            if process.kill() {
                Ok(())
            } else {
                Err("Не удалось завершить процесс (недостаточно прав?)".to_string())
            }
        }
        None => Err("Процесс не найден".to_string()),
    }
}

/// Скриншот основного монитора — возвращается как data URL (base64 PNG),
/// чтобы фронтенд мог сразу показать превью без записи на диск.
#[tauri::command]
pub fn take_screenshot() -> Result<String, String> {
    let monitors = xcap::Monitor::all().map_err(|e| e.to_string())?;
    let monitor = monitors
        .into_iter()
        .find(|m| m.is_primary().unwrap_or(false))
        .ok_or_else(|| "Не найден основной монитор".to_string())?;

    let image = monitor.capture_image().map_err(|e| e.to_string())?;

    let mut png_bytes: Vec<u8> = Vec::new();
    image
        .write_to(&mut std::io::Cursor::new(&mut png_bytes), image::ImageFormat::Png)
        .map_err(|e| e.to_string())?;

    Ok(format!("data:image/png;base64,{}", general_purpose::STANDARD.encode(&png_bytes)))
}

/// Открыть нативный терминал (Windows Terminal, либо cmd как фолбэк).
#[tauri::command]
pub fn open_terminal() -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        if std::process::Command::new("wt.exe").spawn().is_ok() {
            return Ok(());
        }
        std::process::Command::new("cmd.exe")
            .arg("/K")
            .spawn()
            .map(|_| ())
            .map_err(|e| e.to_string())
    }
    #[cfg(not(target_os = "windows"))]
    {
        Err("Открытие терминала пока реализовано только для Windows".to_string())
    }
}

#[tauri::command]
pub fn set_volume(action: String) -> Result<(), String> {
    let mut enigo = Enigo::new(&Settings::default()).map_err(|e| e.to_string())?;
    let key = match action.as_str() {
        "up" => Key::VolumeUp,
        "down" => Key::VolumeDown,
        "mute" => Key::VolumeMute,
        _ => return Err("Неизвестное действие громкости".to_string()),
    };
    enigo.key(key, Direction::Click).map_err(|e| e.to_string())
}

/// Напечатать текст в текущем активном окне (курсор должен быть в поле ввода).
#[tauri::command]
pub fn type_text(text: String) -> Result<(), String> {
    let mut enigo = Enigo::new(&Settings::default()).map_err(|e| e.to_string())?;
    enigo.text(&text).map_err(|e| e.to_string())
}

/// Переместить курсор в абсолютные координаты экрана и кликнуть левой кнопкой.
#[tauri::command]
pub fn click_at(x: i32, y: i32) -> Result<(), String> {
    let mut enigo = Enigo::new(&Settings::default()).map_err(|e| e.to_string())?;
    enigo.move_mouse(x, y, Coordinate::Abs).map_err(|e| e.to_string())?;
    enigo.button(Button::Left, Direction::Click).map_err(|e| e.to_string())
}

/// Открыть поиск Windows (клавиша Win) и ввести запрос — не выполняет его сам,
/// пользователь довершает Enter'ом. Это НЕ поисковой запрос в интернете,
/// а системный поиск (приложения/файлы/веб через встроенный виджет).
#[tauri::command]
pub fn windows_search(query: String) -> Result<(), String> {
    let mut enigo = Enigo::new(&Settings::default()).map_err(|e| e.to_string())?;
    enigo.key(Key::Meta, Direction::Click).map_err(|e| e.to_string())?;
    std::thread::sleep(std::time::Duration::from_millis(400));
    enigo.text(&query).map_err(|e| e.to_string())
}

/// Удалить файл — ВСЕГДА в Корзину (не безвозвратно), чтобы действие можно
/// было отменить. Подтверждение у пользователя запрашивается на фронтенде
/// ДО вызова этой команды — сюда попадает только уже подтверждённый путь.
#[tauri::command]
pub fn delete_file(path: String) -> Result<(), String> {
    trash::delete(&path).map_err(|e| e.to_string())
}
