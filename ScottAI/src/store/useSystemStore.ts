import { create } from "zustand";

export type BackendStatus = "starting" | "online" | "offline";

interface SystemState {
  /** "starting" — ещё ни разу не ответил с момента запуска лаунчера;
   *  "online" — отвечает; "offline" — не отвечает (в т.ч. упал после того, как уже отвечал). */
  backendStatus: BackendStatus;
  backendOnline: boolean;
  /** Реальное состояние сетевого подключения (navigator.onLine) — Groq/DeepSeek/OpenAI
   *  недоступны без интернета, даже если backend/сам локальный компьютер в порядке. */
  hasInternet: boolean;
  cpuPercent: number | null;
  ramPercent: number | null;
  processCount: number | null;
  setStatus: (partial: Partial<Omit<SystemState, "setStatus">>) => void;
}

export const useSystemStore = create<SystemState>((set) => ({
  backendStatus: "starting",
  backendOnline: false,
  hasInternet: typeof navigator !== "undefined" ? navigator.onLine : true,
  cpuPercent: null,
  ramPercent: null,
  processCount: null,
  setStatus: (partial) => set(partial),
}));
