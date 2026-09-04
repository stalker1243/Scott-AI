import { type ChangeEvent, type KeyboardEvent } from "react";
import { useThemeStore } from "../store/useThemeStore";

interface InputProps {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  multiline?: boolean;
  password?: boolean;
  onEnter?: () => void;
  className?: string;
}

export function StyledInput({ value, onChange, placeholder, multiline, password, onEnter, className = "" }: InputProps) {
  const accent = useThemeStore((s) => s.accent);

  const handleKeyDown = (e: KeyboardEvent) => {
    if (!multiline && e.key === "Enter") onEnter?.();
  };

  const commonStyle = {
    background: "var(--bg-elevated)",
    color: "var(--text-primary)",
    borderColor: "var(--border)",
  };

  const commonClass = `w-full rounded-[var(--radius-sm)] border px-3.5 text-[15px] outline-none transition-colors ${className}`;

  if (multiline) {
    return (
      <textarea
        value={value}
        onChange={(e: ChangeEvent<HTMLTextAreaElement>) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`${commonClass} h-[120px] resize-none py-2.5`}
        style={commonStyle}
        onFocus={(e) => (e.currentTarget.style.borderColor = accent)}
        onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
      />
    );
  }

  return (
    <input
      type={password ? "password" : "text"}
      value={value}
      onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
      onKeyDown={handleKeyDown}
      placeholder={placeholder}
      className={`${commonClass} h-11`}
      style={commonStyle}
      onFocus={(e) => (e.currentTarget.style.borderColor = accent)}
      onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
    />
  );
}
