slint::include_modules!();

mod app;
mod commands;
mod config;
mod core;
mod network;
mod os;
mod state;
mod utils;

fn main() -> anyhow::Result<()> {
    utils::logger::init();

    let rt = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .worker_threads(2)
        .build()?;

    app::run(rt)
}
