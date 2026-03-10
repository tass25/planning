import { create } from "zustand";

interface ThemeState {
  theme: "light" | "dark";
  toggle: () => void;
  setTheme: (theme: "light" | "dark") => void;
}

export const useThemeStore = create<ThemeState>((set) => {
  const stored = typeof window !== "undefined" ? localStorage.getItem("codara-theme") as "light" | "dark" | null : null;
  const initial = stored || "dark";
  if (typeof document !== "undefined") {
    document.documentElement.classList.toggle("dark", initial === "dark");
  }
  return {
    theme: initial,
    toggle: () =>
      set((s) => {
        const next = s.theme === "dark" ? "light" : "dark";
        document.documentElement.classList.toggle("dark", next === "dark");
        localStorage.setItem("codara-theme", next);
        return { theme: next };
      }),
    setTheme: (theme) =>
      set(() => {
        document.documentElement.classList.toggle("dark", theme === "dark");
        localStorage.setItem("codara-theme", theme);
        return { theme };
      }),
  };
});
