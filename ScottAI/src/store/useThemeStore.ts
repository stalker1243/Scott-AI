import { create } from "zustand";

export type AppStyle = "classic" | "glass" | "terminal";

interface ThemeState {
  style: AppStyle;
  darkMode: boolean;
  accent: string;
  glassOpacity: number;
  setStyle: (style: AppStyle) => void;
  setDarkMode: (v: boolean) => void;
  setAccent: (hex: string) => void;
  setGlassOpacity: (v: number) => void;
  hydrate: (partial: Partial<Omit<ThemeState, "hydrate" | "setStyle" | "setDarkMode" | "setAccent" | "setGlassOpacity">>) => void;
}

export const useThemeStore = create<ThemeState>((set) => ({
  style: "classic",
  darkMode: true,
  accent: "#3b82f6",
  glassOpacity: 0.35,
  setStyle: (style) => set({ style }),
  setDarkMode: (darkMode) => set({ darkMode }),
  setAccent: (accent) => set({ accent }),
  setGlassOpacity: (glassOpacity) => set({ glassOpacity }),
  hydrate: (partial) => set(partial),
}));
