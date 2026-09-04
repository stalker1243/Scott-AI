use sysinfo::System;

/// Живые метрики системы, собираемые локально (без обращения к backend) —
/// мгновенный отклик для карточек на главной странице.
pub struct SystemInfo {
    sys: System,
}

#[derive(Debug, Clone)]
pub struct Snapshot {
    pub cpu_percent: f32,
    pub ram_percent: f32,
    pub process_count: usize,
}

impl SystemInfo {
    pub fn new() -> Self {
        let mut sys = System::new_all();
        sys.refresh_all();
        Self { sys }
    }

    pub fn snapshot(&mut self) -> Snapshot {
        self.sys.refresh_cpu_usage();
        self.sys.refresh_memory();
        self.sys.refresh_processes(sysinfo::ProcessesToUpdate::All, true);

        let cpu_percent = if self.sys.cpus().is_empty() {
            0.0
        } else {
            self.sys.cpus().iter().map(|c| c.cpu_usage()).sum::<f32>() / self.sys.cpus().len() as f32
        };

        let total_mem = self.sys.total_memory().max(1);
        let used_mem = self.sys.used_memory();
        let ram_percent = (used_mem as f64 / total_mem as f64 * 100.0) as f32;

        Snapshot {
            cpu_percent,
            ram_percent,
            process_count: self.sys.processes().len(),
        }
    }
}

impl Default for SystemInfo {
    fn default() -> Self {
        Self::new()
    }
}
