import { type LucideIcon } from "lucide-react";
import { motion } from "framer-motion";
import { useState } from "react";
import { useThemeStore } from "../store/useThemeStore";

interface StatCardProps {
  title: string;
  value: string;
  icon: LucideIcon;
  accentColor?: string;
}

export function StatCard({ title, value, icon: Icon, accentColor }: StatCardProps) {
  const themeAccent = useThemeStore((s) => s.accent);
  const isGlass = useThemeStore((s) => s.style === "glass");
  const color = accentColor ?? themeAccent;
  const [hovered, setHovered] = useState(false);

  return (
    <motion.div
      onHoverStart={() => setHovered(true)}
      onHoverEnd={() => setHovered(false)}
      whileHover={{ y: -3 }}
      transition={{ type: "spring", stiffness: 350, damping: 22 }}
      className="glass-panel relative flex h-[120px] w-[220px] shrink-0 overflow-hidden rounded-[var(--radius-md)] border transition-colors duration-200"
      style={{
        background: hovered ? "var(--bg-elevated)" : "var(--bg-surface)",
        borderColor: hovered ? color : "var(--border)",
        boxShadow: isGlass ? "none" : hovered ? `0 10px 22px var(--shadow)` : "0 4px 10px var(--shadow)",
      }}
    >
      <div className="absolute left-0 top-0 h-full w-1" style={{ background: color }} />
      <div className="flex flex-col justify-center gap-1.5 px-[18px] py-[18px]">
        <div className="flex items-center gap-2">
          <Icon size={16} color={color} strokeWidth={2} />
          <span className="text-[13px] font-semibold" style={{ color: "var(--text-secondary)" }}>
            {title}
          </span>
        </div>
        <span className="text-[28px] font-bold leading-none" style={{ color: "var(--text-primary)" }}>
          {value}
        </span>
      </div>
    </motion.div>
  );
}
