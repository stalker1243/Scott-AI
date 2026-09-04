/// Инициализирует консольное логирование через `tracing`.
/// Уровень по умолчанию — `info`, переопределяется переменной окружения `RUST_LOG`.
pub fn init() {
    let filter = std::env::var("RUST_LOG").unwrap_or_else(|_| "info".to_string());

    let _ = tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::new(filter))
        .try_init();
}
