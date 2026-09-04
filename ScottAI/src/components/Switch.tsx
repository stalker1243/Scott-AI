import { motion } from "framer-motion";
import { useThemeStore } from "../store/useThemeStore";

interface SwitchProps {
  checked: boolean;
  onToggle: (v: boolean) => void;
}

export function Switch({ checked, onToggle }: SwitchProps) {
  const accent = useThemeStore((s) => s.accent);

  return (
    <motion.button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onToggle(!checked)}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      transition={{ type: "spring", stiffness: 500, damping: 28 }}
      className="relative h-[26px] w-[50px] shrink-0 rounded-full border transition-colors duration-200"
      style={{
        background: checked ? accent : "var(--bg-elevated)",
        borderColor: checked ? accent : "var(--border)",
      }}
    >
      <motion.span
        layout
        transition={{ type: "spring", stiffness: 600, damping: 32 }}
        className="absolute top-[3px] h-5 w-5 rounded-full bg-white shadow-md"
        style={{ left: checked ? "calc(100% - 23px)" : "3px" }}
      />
    </motion.button>
  );
}
