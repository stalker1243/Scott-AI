use std::cell::RefCell;
use std::rc::Rc;
use std::time::Duration;

use slint::{Color, ComponentHandle, Model, ModelRc, SharedString, VecModel};
use tokio::runtime::Runtime;

use crate::commands::{color_to_hex, config_style_to_slint, current_time, hex_to_color, slint_style_to_config};
use crate::config::settings::Settings;
use crate::state::AppState;
use crate::{AppPage, AppStyle, AppWindow, ChatMessage, Theme};

pub fn run(rt: Runtime) -> anyhow::Result<()> {
    let settings = Settings::load();
    let app = AppWindow::new()?;

    apply_settings_to_ui(&app, &settings);

    let state = Rc::new(RefCell::new(AppState::new(settings)));

    seed_chat(&app);

    // window_vibrancy требует уже показанное окно с валидным native handle —
    // на момент AppWindow::new() окно ещё не отрисовано, поэтому применяем
    // блюр чуть позже, одним тактом event loop.
    {
        let app_weak = app.as_weak();
        let initial_style = state.borrow().settings.style;
        let initial_opacity = state.borrow().settings.glass_opacity;
        let timer = slint::Timer::default();
        timer.start(slint::TimerMode::SingleShot, Duration::from_millis(50), move || {
            if let Some(app) = app_weak.upgrade() {
                apply_native_blur(&app, initial_style, initial_opacity);
            }
        });
        std::mem::forget(timer);
    }

    wire_theme(&app, state.clone());
    wire_profile(&app, state.clone());
    wire_chat(&app, state.clone(), &rt);
    wire_health_polling(&app, state.clone(), &rt);
    wire_system_info_polling(&app, state.clone());

    app.run()?;
    Ok(())
}

fn apply_settings_to_ui(app: &AppWindow, settings: &Settings) {
    let theme = app.global::<Theme>();
    theme.set_style(config_style_to_slint(settings.style));
    theme.set_dark_mode(settings.dark_mode);
    theme.set_accent(hex_to_color(&settings.accent_color));
    theme.set_glass_opacity(settings.glass_opacity);

    app.set_backend_url(SharedString::from(settings.backend_url.clone()));
    app.set_profile_name(SharedString::from(settings.profile.name.clone()));
    app.set_profile_bio(SharedString::from(settings.profile.bio.clone()));
}

fn seed_chat(app: &AppWindow) {
    let messages = vec![ChatMessage {
        from_user: false,
        text: "Привет! Я Scott. Нажмите «Запустить Scott» на главной или просто напишите мне здесь.".into(),
        time: current_time().into(),
        has_image: false,
        image: Default::default(),
    }];
    app.set_chat_messages(ModelRc::new(VecModel::from(messages)));
}

/// Применяет нативный acrylic-блюр окна (Windows/macOS) для стиля Glass —
/// логика перенесена из прежнего прототипа rust_launcher (см. docs/reference).
///
/// `glass_opacity` (0.0–1.0, из Settings/Theme.glass-opacity) управляет альфой
/// тонирующего цвета acrylic — чем выше значение, тем менее прозрачно окно. Диапазон
/// альфы намеренно не доходит до 0/255, чтобы блюр не отключался полностью и не
/// превращался в полностью непрозрачную заливку на любом уровне слайдера.
fn apply_native_blur(app: &AppWindow, style: crate::config::themes::AppStyle, glass_opacity: f32) {
    use crate::config::themes::AppStyle as ConfigAppStyle;

    let is_glass = matches!(style, ConfigAppStyle::Glass);
    let tint_alpha = (15.0 + glass_opacity.clamp(0.0, 1.0) * 220.0).round() as u8;

    #[cfg(target_os = "windows")]
    {
        let handle = app.window().window_handle();
        if is_glass {
            match window_vibrancy::apply_acrylic(&handle, Some((11, 18, 32, tint_alpha))) {
                Ok(()) => tracing::debug!(tint_alpha, "apply_acrylic: OK"),
                Err(err) => tracing::warn!(?err, "apply_acrylic failed"),
            }
        } else {
            let _ = window_vibrancy::clear_acrylic(&handle);
        }
    }

    #[cfg(target_os = "macos")]
    {
        let handle = app.window().window_handle();
        if is_glass {
            let _ = window_vibrancy::apply_vibrancy(
                &handle,
                window_vibrancy::NSVisualEffectMaterial::HudWindow,
                None,
                None,
            );
        } else {
            let _ = window_vibrancy::clear_vibrancy(&handle);
        }
    }

    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    {
        let _ = (is_glass, tint_alpha);
    }
}

fn wire_theme(app: &AppWindow, state: Rc<RefCell<AppState>>) {
    {
        let app_weak = app.as_weak();
        let state = state.clone();
        app.on_style_selected(move |style: AppStyle| {
            let Some(app) = app_weak.upgrade() else { return };
            let config_style = slint_style_to_config(style);
            tracing::debug!(?config_style, "style selected");

            app.global::<Theme>().set_style(style);

            let mut s = state.borrow_mut();
            s.settings.style = config_style;
            apply_native_blur(&app, config_style, s.settings.glass_opacity);
            if let Err(err) = s.settings.save() {
                tracing::warn!("Не удалось сохранить настройки: {err}");
            }
        });
    }

    {
        let state = state.clone();
        app.on_dark_mode_toggled(move |value: bool| {
            tracing::debug!(value, "dark mode toggled");
            let mut s = state.borrow_mut();
            s.settings.dark_mode = value;
            if let Err(err) = s.settings.save() {
                tracing::warn!("Не удалось сохранить настройки: {err}");
            }
        });
    }

    {
        let state = state.clone();
        app.on_accent_selected(move |color: Color| {
            tracing::debug!("accent selected");
            let mut s = state.borrow_mut();
            s.settings.accent_color = color_to_hex(color);
            if let Err(err) = s.settings.save() {
                tracing::warn!("Не удалось сохранить настройки: {err}");
            }
        });
    }

    {
        let app_weak = app.as_weak();
        let state = state.clone();
        // Слайдер прозрачности шлёт changed() на каждое движение курсора во время
        // перетаскивания — визуальный отклик (тема + нативный acrylic) применяем сразу,
        // а запись settings.toml на диск откладываем на 250ms тишины после последнего
        // изменения, чтобы не долбить диск на каждый пиксель драга.
        let save_timer: Rc<RefCell<Option<slint::Timer>>> = Rc::new(RefCell::new(None));
        app.on_glass_opacity_changed(move |value: f32| {
            let Some(app) = app_weak.upgrade() else { return };
            let value = value.clamp(0.0, 1.0);

            app.global::<Theme>().set_glass_opacity(value);

            let style = {
                let mut s = state.borrow_mut();
                s.settings.glass_opacity = value;
                s.settings.style
            };
            apply_native_blur(&app, style, value);

            let state = state.clone();
            let timer = slint::Timer::default();
            timer.start(slint::TimerMode::SingleShot, Duration::from_millis(250), move || {
                if let Err(err) = state.borrow().settings.save() {
                    tracing::warn!("Не удалось сохранить настройки: {err}");
                }
            });
            *save_timer.borrow_mut() = Some(timer);
        });
    }
}

fn wire_profile(app: &AppWindow, state: Rc<RefCell<AppState>>) {
    let app_weak = app.as_weak();
    app.on_save_profile(move || {
        let Some(app) = app_weak.upgrade() else { return };

        let mut s = state.borrow_mut();
        s.settings.profile.name = app.get_profile_name().to_string();
        s.settings.profile.bio = app.get_profile_bio().to_string();
        if let Err(err) = s.settings.save() {
            tracing::warn!("Не удалось сохранить профиль: {err}");
        }
        drop(s);

        app.set_profile_saved_recently(true);
        let app_weak2 = app.as_weak();
        slint::Timer::single_shot(Duration::from_secs(2), move || {
            if let Some(app) = app_weak2.upgrade() {
                app.set_profile_saved_recently(false);
            }
        });
    });
}

fn wire_chat(app: &AppWindow, state: Rc<RefCell<AppState>>, rt: &Runtime) {
    let rt_handle = rt.handle().clone();

    // ---- Навигация с главной страницы ----
    {
        let app_weak = app.as_weak();
        app.on_launch_assistant(move || {
            let Some(app) = app_weak.upgrade() else { return };
            app.set_current_page(AppPage::Chat);
        });
    }

    // ---- Быстрые команды с главной ----
    {
        let app_weak = app.as_weak();
        app.on_quick_command(move |text: SharedString| {
            let Some(app) = app_weak.upgrade() else { return };
            app.set_current_page(AppPage::Chat);
            app.set_chat_draft(text);
            app.invoke_send_message();
        });
    }

    // ---- Новый чат ----
    {
        let app_weak = app.as_weak();
        app.on_new_chat(move || {
            let Some(app) = app_weak.upgrade() else { return };
            app.set_chat_messages(ModelRc::new(VecModel::from(Vec::<ChatMessage>::new())));
        });
    }

    // ---- Прикрепление изображения ----
    {
        let app_weak = app.as_weak();
        app.on_attach_image(move || {
            let Some(app) = app_weak.upgrade() else { return };

            let picked = rfd::FileDialog::new()
                .add_filter("Изображения", &["png", "jpg", "jpeg", "bmp", "gif"])
                .pick_file();

            let Some(path) = picked else { return };

            match slint::Image::load_from_path(&path) {
                Ok(image) => {
                    app.set_pending_image(image);
                    app.set_has_pending_image(true);
                    app.set_pending_image_name(SharedString::from(
                        path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default(),
                    ));
                }
                Err(err) => tracing::warn!("Не удалось загрузить изображение: {err}"),
            }
        });
    }

    {
        let app_weak = app.as_weak();
        app.on_clear_pending_image(move || {
            let Some(app) = app_weak.upgrade() else { return };
            app.set_has_pending_image(false);
            app.set_pending_image_name(SharedString::default());
        });
    }

    // ---- Голосовой ввод: пока не реализован (Этап 3 плана) ----
    app.on_start_voice_input(move || {
        tracing::info!("Голосовой ввод ещё не реализован — см. Этап 3 плана пересборки");
    });

    // ---- Отправка сообщения ----
    {
        let app_weak = app.as_weak();
        app.on_send_message(move || {
            let Some(app) = app_weak.upgrade() else { return };

            let text = app.get_chat_draft().to_string();
            let has_image = app.get_has_pending_image();
            if text.trim().is_empty() && !has_image {
                return;
            }

            let image = app.get_pending_image();

            push_message(
                &app,
                ChatMessage {
                    from_user: true,
                    text: SharedString::from(text.clone()),
                    time: SharedString::from(current_time()),
                    has_image,
                    image: image.clone(),
                },
            );

            app.set_chat_draft(SharedString::default());
            app.set_has_pending_image(false);
            app.set_pending_image_name(SharedString::default());

            if has_image && text.trim().is_empty() {
                push_message(
                    &app,
                    ChatMessage {
                        from_user: false,
                        text: "Изображение получено — Scott пока не умеет их анализировать (эта возможность появится, когда backend получит поддержку зрения).".into(),
                        time: SharedString::from(current_time()),
                        has_image: false,
                        image: Default::default(),
                    },
                );
                return;
            }

            let client = state.borrow().backend.clone();
            app.set_chat_sending(true);

            let app_weak2 = app.as_weak();
            rt_handle.spawn(async move {
                let result = client.ask(&text).await;
                let _ = slint::invoke_from_event_loop(move || {
                    let Some(app) = app_weak2.upgrade() else { return };
                    app.set_chat_sending(false);

                    let reply = match result {
                        Ok(answer) if !answer.trim().is_empty() => answer,
                        Ok(_) => "Scott не дал ответа.".to_string(),
                        Err(err) => format!("Не удалось получить ответ от Scott: {err}"),
                    };

                    push_message(
                        &app,
                        ChatMessage {
                            from_user: false,
                            text: SharedString::from(reply),
                            time: SharedString::from(current_time()),
                            has_image: false,
                            image: Default::default(),
                        },
                    );
                });
            });
        });
    }
}

fn push_message(app: &AppWindow, message: ChatMessage) {
    let messages = app.get_chat_messages();
    let model = messages
        .as_any()
        .downcast_ref::<VecModel<ChatMessage>>()
        .expect("chat-messages должен быть VecModel");
    model.push(message);
}

fn check_health_once(app: &AppWindow, state: &Rc<RefCell<AppState>>, rt_handle: &tokio::runtime::Handle) {
    let client = state.borrow().backend.clone();
    let app_weak = app.as_weak();
    rt_handle.spawn(async move {
        let online = client.health().await.is_ok();
        let _ = slint::invoke_from_event_loop(move || {
            if let Some(app) = app_weak.upgrade() {
                app.set_backend_online(online);
            }
        });
    });
}

fn wire_health_polling(app: &AppWindow, state: Rc<RefCell<AppState>>, rt: &Runtime) {
    let rt_handle = rt.handle().clone();

    // Первая проверка сразу при старте, не дожидаясь первого тика таймера.
    check_health_once(app, &state, &rt_handle);

    let app_weak = app.as_weak();
    let timer = slint::Timer::default();
    timer.start(slint::TimerMode::Repeated, Duration::from_secs(4), move || {
        let Some(app) = app_weak.upgrade() else { return };
        check_health_once(&app, &state, &rt_handle);
    });
    std::mem::forget(timer);
}

fn wire_system_info_polling(app: &AppWindow, state: Rc<RefCell<AppState>>) {
    let app_weak = app.as_weak();
    let timer = slint::Timer::default();
    timer.start(slint::TimerMode::Repeated, Duration::from_millis(1500), move || {
        let Some(app) = app_weak.upgrade() else { return };
        let snapshot = state.borrow_mut().sysinfo.snapshot();

        app.set_cpu_usage(SharedString::from(format!("{:.0}%", snapshot.cpu_percent)));
        app.set_ram_usage(SharedString::from(format!("{:.0}%", snapshot.ram_percent)));
        app.set_process_count(SharedString::from(snapshot.process_count.to_string()));
    });
    std::mem::forget(timer);
}
