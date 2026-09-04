use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::time::Duration;

/// Найти директорию backend/ (где лежит main.py), поднимаясь вверх от
/// расположения exe. В dev-сборке exe лежит в ScottAI/src-tauri/target/debug/,
/// а backend/ — на 4 уровня выше (в корне репозитория neyro/).
/// Можно переопределить переменной окружения SCOTT_BACKEND_DIR.
fn find_backend_dir() -> Option<PathBuf> {
    if let Ok(dir) = std::env::var("SCOTT_BACKEND_DIR") {
        let p = PathBuf::from(dir);
        if p.join("main.py").exists() {
            return Some(p);
        }
    }

    let exe = std::env::current_exe().ok()?;
    let mut dir = exe.parent()?.to_path_buf();

    for _ in 0..8 {
        let candidate = dir.join("backend");
        if candidate.join("main.py").exists() {
            return Some(candidate);
        }
        dir = dir.parent()?.to_path_buf();
    }
    None
}

pub fn backend_already_running() -> bool {
    TcpStream::connect_timeout(&"127.0.0.1:8000".parse().unwrap(), Duration::from_millis(300)).is_ok()
}

/// Запустить `python main.py` из backend/, если он ещё не поднят на :8000.
/// Возвращает handle на дочерний процесс (для остановки при выходе) —
/// None, если backend уже был запущен извне, или если что-то пошло не так
/// (в этом случае приложение всё равно продолжает работать — просто без
/// автозапуска, как раньше, когда backend нужно было включать вручную).
pub fn spawn_backend() -> Option<Child> {
    if backend_already_running() {
        println!("[backend] уже отвечает на :8000 — автозапуск пропущен");
        return None;
    }

    let Some(backend_dir) = find_backend_dir() else {
        eprintln!("[backend] не нашёл backend/main.py рядом с приложением — запустите backend вручную");
        return None;
    };

    let log_path = backend_dir
        .parent()
        .unwrap_or(&backend_dir)
        .join("backend_autostart.log");

    let mut cmd = Command::new("python");
    cmd.arg("main.py").current_dir(&backend_dir);

    if let Ok(log_file) = std::fs::File::create(&log_path) {
        if let Ok(stdout_file) = log_file.try_clone() {
            cmd.stdout(Stdio::from(stdout_file));
        }
        cmd.stderr(Stdio::from(log_file));
    } else {
        cmd.stdout(Stdio::null()).stderr(Stdio::null());
    }

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    match cmd.spawn() {
        Ok(child) => {
            println!(
                "[backend] автозапуск: python main.py (pid {}), лог: {}",
                child.id(),
                log_path.display()
            );
            Some(child)
        }
        Err(e) => {
            eprintln!("[backend] не удалось запустить python main.py: {e}");
            None
        }
    }
}

/// Остановить процесс backend, запущенный нами при старте — вызывается при
/// выходе из приложения. Backend, запущенный пользователем вручную заранее
/// (spawn_backend() тогда вернул None), не трогаем.
pub fn stop_backend(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}
