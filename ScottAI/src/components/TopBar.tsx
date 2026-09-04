import { useState } from "react";
import { RotateCw } from "lucide-react";
import { useSystemStore } from "../store/useSystemStore";
import { os } from "../lib/osCommands";

const STATUS_LABEL: Record<string, string> = {
  starting: "ЗАПУСК...",
  online: "ONLINE",
  offline: "OFFLINE",
};

interface TopBarProps {
  subtitle: string;
}

export function TopBar({ subtitle }: TopBarProps) {
  const backendStatus = useSystemStore((s) => s.backendStatus);
  const [restarting, setRestarting] = useState(false);

  const statusColor =
    backendStatus === "online" ? "var(--success)" : backendStatus === "starting" ? "var(--warning)" : "var(--danger)";

  const handleRestart = async () => {
    setRestarting(true);
    try {
      await os.restartBackend();
    } catch (err) {
      console.error("[backend] restart failed:", err);
    } finally {
      setTimeout(() => setRestarting(false), 2000);
    }
  };

  return (
    <div
      className="glass-panel flex h-[72px] shrink-0 items-center justify-between border-b px-7"
      style={{ background: "var(--bg-topbar)", borderColor: "var(--border)" }}
    >
      <div className="flex flex-col">
        <span className="text-[26px] font-bold" style={{ color: "var(--text-primary)" }}>
          ScottAI
        </span>
        <span className="text-[13px]" style={{ color: "var(--text-secondary)" }}>
          {subtitle}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <span
          className="h-2.5 w-2.5 rounded-full transition-colors"
          style={{ background: statusColor, boxShadow: backendStatus === "online" ? `0 0 8px ${statusColor}` : "none" }}
        />
        <span className="text-[13px] font-bold transition-colors" style={{ color: statusColor }}>
          {STATUS_LABEL[backendStatus]}
        </span>

        {backendStatus === "offline" && (
          <button
            type="button"
            onClick={handleRestart}
            disabled={restarting}
            title="Перезапустить backend"
            className="flex h-7 w-7 items-center justify-center rounded disabled:opacity-40"
            style={{ color: "var(--text-secondary)", background: "var(--bg-elevated)" }}
          >
            <RotateCw size={13} className={restarting ? "animate-spin" : ""} />
          </button>
        )}
      </div>
    </div>
  );
}
