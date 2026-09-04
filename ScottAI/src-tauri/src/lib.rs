use std::process::Child;
use std::sync::Mutex;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{Manager, RunEvent, WindowEvent};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

mod backend_process;
mod os_commands;

/// Хранит handle на backend, если мы его сами запустили при старте —
/// нужно, чтобы корректно остановить его при выходе из приложения.
struct BackendHandle(Mutex<Option<Child>>);

/// Перезапустить backend вручную из интерфейса — на случай, если Python-процесс
/// упал во время сессии (автозапуск в setup() срабатывает только один раз, при
/// старте приложения). Останавливает уже отслеживаемый процесс (если он наш) и
/// запускает заново; если backend уже отвечает на :8000 — просто сообщает об этом.
#[tauri::command]
fn restart_backend(state: tauri::State<BackendHandle>) -> Result<String, String> {
    let mut guard = state.0.lock().unwrap();
    if let Some(mut child) = guard.take() {
        backend_process::stop_backend(&mut child);
        // Дать порту время освободиться перед повторным запуском.
        std::thread::sleep(std::time::Duration::from_millis(300));
    }

    match backend_process::spawn_backend() {
        Some(child) => {
            *guard = Some(child);
            Ok("Backend перезапущен".to_string())
        }
        None if backend_process::backend_already_running() => {
            Ok("Backend уже отвечает — перезапуск не потребовался".to_string())
        }
        None => Err("Не удалось запустить backend — см. backend_autostart.log".to_string()),
    }
}

fn toggle_main_window(app: &tauri::AppHandle) {
    let Some(window) = app.get_webview_window("main") else { return };
    let is_visible = window.is_visible().unwrap_or(false);
    if is_visible {
        let _ = window.hide();
    } else {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _shortcut, event| {
                    if event.state() == ShortcutState::Pressed {
                        toggle_main_window(app);
                    }
                })
                .build(),
        )
        .invoke_handler(tauri::generate_handler![
            os_commands::list_processes,
            os_commands::kill_process,
            os_commands::take_screenshot,
            os_commands::open_terminal,
            os_commands::set_volume,
            os_commands::type_text,
            os_commands::click_at,
            os_commands::windows_search,
            os_commands::delete_file,
            restart_backend,
        ])
        .manage(BackendHandle(Mutex::new(None)))
        .setup(|app| {
            // Автозапуск backend (python main.py), если он ещё не поднят на :8000.
            // Останавливается при выходе — см. RunEvent::Exit ниже.
            let backend_child = backend_process::spawn_backend();
            *app.state::<BackendHandle>().0.lock().unwrap() = backend_child;

            // Глобальный хоткей: Ctrl+Shift+Space — показать/скрыть окно из любого места.
            let shortcut = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::Space);
            app.global_shortcut().register(shortcut)?;

            // Системный трей: показать/скрыть + выход. Закрытие окна крестиком тоже
            // сворачивает в трей вместо выхода (обработчик window-events ниже).
            let toggle_item = MenuItem::with_id(app, "toggle", "Показать / скрыть Scott", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Выход", true, None::<&str>)?;
            let tray_menu = Menu::with_items(app, &[&toggle_item, &quit_item])?;

            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("ScottAI")
                .menu(&tray_menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "toggle" => toggle_main_window(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let tauri::tray::TrayIconEvent::Click {
                        button: tauri::tray::MouseButton::Left,
                        button_state: tauri::tray::MouseButtonState::Up,
                        ..
                    } = event
                    {
                        toggle_main_window(tray.app_handle());
                    }
                })
                .build(app)?;

            if let Some(window) = app.get_webview_window("main") {
                let window_for_close = window.clone();
                window.on_window_event(move |event| {
                    if let WindowEvent::CloseRequested { api, .. } = event {
                        api.prevent_close();
                        let _ = window_for_close.hide();
                    }
                });
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            // Останавливаем backend, который сами запустили при старте —
            // при любом варианте выхода (трей "Выход", Cmd+Q и т.п.).
            if let RunEvent::Exit = event {
                if let Some(mut child) = app_handle.state::<BackendHandle>().0.lock().unwrap().take() {
                    backend_process::stop_backend(&mut child);
                }
            }
        });
}
