import { create } from "zustand";

type Mode = "light" | "dark";
type Aesthetic = "aurora" | "editorial" | "slate";

interface ThemeState {
  theme: Mode;
  aesthetic: Aesthetic;
  toggle: () => void;
  setTheme: (theme: Mode) => void;
  setAesthetic: (aesthetic: Aesthetic) => void;
}

function applyMode(mode: Mode) {
  document.documentElement.classList.toggle("dark", mode === "dark");
  localStorage.setItem("codara-theme", mode);
}

function applyAesthetic(aesthetic: Aesthetic) {
  if (aesthetic === "aurora") {
    document.documentElement.removeAttribute("data-aesthetic");
  } else {
    document.documentElement.setAttribute("data-aesthetic", aesthetic);
  }
  localStorage.setItem("codara-aesthetic", aesthetic);
}

export const useThemeStore = create<ThemeState>((set) => {
  const storedMode = typeof window !== "undefined" ? localStorage.getItem("codara-theme") as Mode | null : null;
  const storedAesthetic = typeof window !== "undefined" ? localStorage.getItem("codara-aesthetic") as Aesthetic | null : null;
  const initialMode = storedMode || "dark";
  const initialAesthetic = storedAesthetic || "aurora";

  if (typeof document !== "undefined") {
    applyMode(initialMode);
    applyAesthetic(initialAesthetic);
  }

  return {
    theme: initialMode,
    aesthetic: initialAesthetic,
    toggle: () =>
      set((s) => {
        const next: Mode = s.theme === "dark" ? "light" : "dark";
        applyMode(next);
        return { theme: next };
      }),
    setTheme: (theme) =>
      set(() => {
        applyMode(theme);
        return { theme };
      }),
    setAesthetic: (aesthetic) =>
      set(() => {
        applyAesthetic(aesthetic);
        return { aesthetic };
      }),
  };
});
