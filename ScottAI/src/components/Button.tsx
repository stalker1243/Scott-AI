import { type LucideIcon } from "lucide-react";
import { motion } from "framer-motion";
import { useThemeStore } from "../store/useThemeStore";

interface AccentButtonProps {
  text: string;
  icon?: LucideIcon;
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
}

export function AccentButton({ text, icon: Icon, onClick, disabled, className = "" }: AccentButtonProps) {
  const accent = useThemeStore((s) => s.accent);

  return (
    <motion.button
      type="button"
      onClick={onClick}
      disabled={disabled}
      whileHover={disabled ? undefined : { scale: 1.025, y: -1 }}
      whileTap={{ scale: disabled ? 1 : 0.96 }}
      transition={{ type: "spring", stiffness: 500, damping: 28 }}
      className={`flex h-14 items-center justify-center gap-2.5 rounded-[var(--radius-md)] px-6 font-semibold text-white shadow-lg disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      style={{
        backgroundColor: accent,
        boxShadow: disabled ? "none" : `0 8px 20px -6px ${accent}80`,
      }}
    >
      {Icon && <Icon size={18} strokeWidth={2} />}
      <span>{text}</span>
    </motion.button>
  );
}

interface GhostButtonProps {
  text?: string;
  icon?: LucideIcon;
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
  /** Тумблер-состояние (например, идёт запись) — подсвечивается цветом акцента/danger и фоном. */
  active?: boolean;
  /** Деструктивное действие — постоянно окрашено в danger, независимо от active. */
  danger?: boolean;
}

export function GhostButton({ text, icon: Icon, onClick, disabled, className = "", active, danger }: GhostButtonProps) {
  const accent = useThemeStore((s) => s.accent);
  const activeColor = danger ? "var(--danger)" : accent;
  const highlighted = active || danger;

  return (
    <motion.button
      type="button"
      onClick={onClick}
      disabled={disabled}
      whileTap={{ scale: disabled ? 1 : 0.94 }}
      whileHover={disabled ? undefined : { borderColor: activeColor, scale: 1.03, backgroundColor: "var(--bg-elevated)" }}
      transition={{ type: "spring", stiffness: 500, damping: 30 }}
      className={`flex h-11 items-center justify-center gap-2 rounded-[var(--radius-sm)] border px-4 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-40 ${className}`}
      style={{
        borderColor: highlighted ? activeColor : "var(--border)",
        color: disabled ? "var(--text-muted)" : highlighted ? activeColor : "var(--text-primary)",
        background: active ? "var(--bg-elevated)" : "transparent",
      }}
    >
      {Icon && <Icon size={16} strokeWidth={2} />}
      {text && <span>{text}</span>}
    </motion.button>
  );
}
