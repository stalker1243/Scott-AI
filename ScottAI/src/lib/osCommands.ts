import { invoke } from "@tauri-apps/api/core";

export interface ProcessInfo {
  pid: number;
  name: string;
  cpu_percent: number;
  memory_mb: number;
}

export const os = {
  listProcesses: () => invoke<ProcessInfo[]>("list_processes"),
  killProcess: (pid: number) => invoke<void>("kill_process", { pid }),
  takeScreenshot: () => invoke<string>("take_screenshot"),
  openTerminal: () => invoke<void>("open_terminal"),
  setVolume: (action: "up" | "down" | "mute") => invoke<void>("set_volume", { action }),
  typeText: (text: string) => invoke<void>("type_text", { text }),
  clickAt: (x: number, y: number) => invoke<void>("click_at", { x, y }),
  windowsSearch: (query: string) => invoke<void>("windows_search", { query }),
  deleteFile: (path: string) => invoke<void>("delete_file", { path }),
  restartBackend: () => invoke<string>("restart_backend"),
};
