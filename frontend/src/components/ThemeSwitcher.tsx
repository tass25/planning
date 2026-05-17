import { useThemeStore } from "@/store/theme-store";
import { cn } from "@/lib/utils";
import { Sun, Moon, Check } from "lucide-react";

type Aesthetic = "aurora" | "editorial" | "slate";

const THEMES: {
  id: Aesthetic;
  name: string;
  desc: string;
  font: string;
  light: { bg: string; accent: string; secondary: string; fg: string };
  dark: { bg: string; accent: string; secondary: string; fg: string };
}[] = [
  {
    id: "aurora",
    name: "Aurora",
    desc: "Warm amber + lavender, glass surfaces",
    font: "Inter",
    light: { bg: "#f7f3eb", accent: "#d49530", secondary: "#7c66d4", fg: "#1a1b26" },
    dark:  { bg: "#0e0f17", accent: "#e2a648", secondary: "#a78bfa", fg: "#ece8df" },
  },
  {
    id: "editorial",
    name: "Editorial",
    desc: "Paper-ink feel, serif type, sage + plum",
    font: "Newsreader",
    light: { bg: "#efece4", accent: "#4a6a4a", secondary: "#6b3c5a", fg: "#14171a" },
    dark:  { bg: "#0e1014", accent: "#88b08c", secondary: "#c79bba", fg: "#ebe7d8" },
  },
  {
    id: "slate",
    name: "Slate",
    desc: "Technical, dense, blue-steel + teal",
    font: "IBM Plex Sans",
    light: { bg: "#eef1f5", accent: "#2b4a6f", secondary: "#0f8a6a", fg: "#0c1623" },
    dark:  { bg: "#0a0f17", accent: "#6ba3d0", secondary: "#2dd4a8", fg: "#e6ebf2" },
  },
];

export function ThemeSwitcher() {
  const { theme, aesthetic, setTheme, setAesthetic } = useThemeStore();

  return (
    <div className="space-y-5">
      {/* Mode toggle */}
      <div className="flex items-center gap-3">
        <span className="text-xs font-medium text-muted-foreground w-14">Mode</span>
        <div className="flex bg-muted/30 border border-border rounded-lg p-0.5 gap-0.5">
          {(["light", "dark"] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setTheme(mode)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all",
                theme === mode
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {mode === "light" ? <Sun className="w-3 h-3" /> : <Moon className="w-3 h-3" />}
              {mode === "light" ? "Light" : "Dark"}
            </button>
          ))}
        </div>
      </div>

      {/* Aesthetic cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {THEMES.map((t) => {
          const active = aesthetic === t.id;
          const colors = theme === "dark" ? t.dark : t.light;
          return (
            <button
              key={t.id}
              onClick={() => setAesthetic(t.id)}
              className={cn(
                "relative text-left p-3 rounded-xl border transition-all group",
                active
                  ? "border-accent ring-1 ring-accent/30"
                  : "border-border hover:border-accent/30"
              )}
            >
              {active && (
                <div className="absolute top-2 right-2 w-5 h-5 rounded-full bg-accent flex items-center justify-center">
                  <Check className="w-3 h-3 text-accent-foreground" />
                </div>
              )}

              {/* Color preview */}
              <div
                className="w-full h-16 rounded-lg mb-3 relative overflow-hidden"
                style={{ background: colors.bg }}
              >
                <div className="absolute top-2 left-2 right-2 h-3 rounded" style={{ background: colors.accent, opacity: 0.8 }} />
                <div className="absolute top-7 left-2 w-12 h-2 rounded" style={{ background: colors.fg, opacity: 0.2 }} />
                <div className="absolute top-7 right-2 w-8 h-2 rounded" style={{ background: colors.secondary, opacity: 0.6 }} />
                <div className="absolute bottom-2 left-2 right-2 flex gap-1">
                  <div className="h-2 flex-1 rounded" style={{ background: colors.accent, opacity: 0.3 }} />
                  <div className="h-2 flex-1 rounded" style={{ background: colors.secondary, opacity: 0.3 }} />
                  <div className="h-2 flex-1 rounded" style={{ background: colors.fg, opacity: 0.1 }} />
                </div>
              </div>

              <div className="flex items-center gap-2 mb-0.5">
                <h3 className="text-sm font-semibold text-foreground">{t.name}</h3>
                <span className="text-[10px] text-muted-foreground font-mono">{t.font}</span>
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">{t.desc}</p>

              {/* Color dots */}
              <div className="flex items-center gap-1.5 mt-2">
                <span className="w-3 h-3 rounded-full border border-black/10" style={{ background: colors.accent }} />
                <span className="w-3 h-3 rounded-full border border-black/10" style={{ background: colors.secondary }} />
                <span className="w-3 h-3 rounded-full border border-black/10" style={{ background: colors.bg }} />
                <span className="w-3 h-3 rounded-full border border-black/10" style={{ background: colors.fg }} />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
