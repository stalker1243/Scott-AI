import { Home, MessageCircle, Settings, User, Cpu, Ear, Zap, BarChart3, type LucideIcon } from "lucide-react";
import { motion } from "framer-motion";
import { useThemeStore } from "../store/useThemeStore";
import { useSystemStore } from "../store/useSystemStore";
import { useDeviceStore } from "../store/useDeviceStore";
import { useChatStore } from "../store/useChatStore";
import type { Page } from "../App";

const NAV_ITEMS: { page: Page; label: string; icon: LucideIcon }[] = [
  { page: "home", label: "Главная", icon: Home },
  { page: "chat", label: "Чат", icon: MessageCircle },
  { page: "system", label: "Система", icon: Cpu },
  { page: "automation", label: "Автоматизация", icon: Zap },
  { page: "analytics", label: "Аналитика", icon: BarChart3 },
  { page: "settings", label: "Настройки", icon: Settings },
  { page: "profile", label: "Профиль", icon: User },
];

interface SidebarProps {
  page: Page;
  onSelect: (page: Page) => void;
}

export function Sidebar({ page, onSelect }: SidebarProps) {
  const accent = useThemeStore((s) => s.accent);
  const backendOnline = useSystemStore((s) => s.backendOnline);
  const handsFreeEnabled = useDeviceStore((s) => s.handsFreeEnabled);
  const handsFreeStatus = useChatStore((s) => s.handsFreeStatus);

  return (
    <div
      className="glass-panel flex h-full w-24 shrink-0 flex-col items-center border-r py-[22px]"
      style={{ background: "var(--bg-sidebar)", borderColor: "var(--border)" }}
    >
      <div
        className="flex h-[52px] w-[52px] items-center justify-center rounded-[var(--radius-md)] text-2xl font-bold text-white"
        style={{ background: accent, boxShadow: `0 6px 16px -4px ${accent}80` }}
      >
        S
      </div>

      <nav className="mt-6 flex w-full flex-1 flex-col gap-2 overflow-y-auto px-2">
        {NAV_ITEMS.map(({ page: itemPage, label, icon: Icon }) => {
          const active = page === itemPage;
          return (
            <motion.button
              key={itemPage}
              type="button"
              onClick={() => onSelect(itemPage)}
              whileHover={{ scale: 1.06, background: "var(--bg-elevated)" }}
              whileTap={{ scale: 0.94 }}
              transition={{ type: "spring", stiffness: 500, damping: 28 }}
              className="relative flex h-14 shrink-0 flex-col items-center justify-center gap-1 rounded-[var(--radius-sm)]"
              style={{ background: active ? "var(--bg-elevated)" : "transparent" }}
            >
              {active && (
                <motion.span
                  layoutId="nav-indicator"
                  className="absolute left-0 h-7 w-[3px] rounded-full"
                  style={{ background: accent }}
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
              <Icon size={20} color={active ? accent : "var(--text-secondary)"} strokeWidth={2} />
              <span className="text-[10px] font-semibold" style={{ color: active ? accent : "var(--text-muted)" }}>
                {label}
              </span>
            </motion.button>
          );
        })}
      </nav>

      {handsFreeEnabled && (
        <motion.div
          title={
            handsFreeStatus === "awaiting-command"
              ? "Слышу вас — говорите команду"
              : handsFreeStatus === "processing"
                ? "Распознаю..."
                : "Голос без рук: слушаю «Скотт»"
          }
          animate={handsFreeStatus !== "idle" ? { scale: [1, 1.15, 1] } : { scale: 1 }}
          transition={{ duration: 1.6, repeat: handsFreeStatus !== "idle" ? Infinity : 0, ease: "easeInOut" }}
          className="mb-2.5 flex h-7 w-7 items-center justify-center rounded-full"
          style={{
            background: handsFreeStatus === "idle" ? "var(--bg-elevated)" : `${accent}26`,
            color: handsFreeStatus === "idle" ? "var(--text-muted)" : accent,
          }}
        >
          <Ear size={14} strokeWidth={2} />
        </motion.div>
      )}

      <div
        className="h-2.5 w-2.5 rounded-full transition-colors"
        style={{
          background: backendOnline ? "var(--success)" : "var(--danger)",
          boxShadow: backendOnline ? "0 0 8px var(--success)" : "none",
        }}
      />
    </div>
  );
}
