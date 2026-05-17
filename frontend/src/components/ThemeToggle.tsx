import { Moon, Sun, Palette } from "lucide-react";
import { useThemeStore } from "@/store/theme-store";
import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";

const AESTHETICS = [
  { id: "aurora" as const, label: "Aurora", color: "#d49530" },
  { id: "editorial" as const, label: "Editorial", color: "#4a6a4a" },
  { id: "slate" as const, label: "Slate", color: "#2b4a6f" },
];

export function ThemeToggle() {
  const { theme, aesthetic, toggle, setAesthetic } = useThemeStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative flex items-center gap-1">
      {/* Aesthetic switcher */}
      <button
        onClick={() => setOpen(!open)}
        className="p-2 rounded-lg hover:bg-muted/50 transition-colors text-muted-foreground hover:text-foreground"
        title="Change theme"
      >
        <Palette className="w-4 h-4" />
      </button>

      {/* Light/dark toggle */}
      <button
        onClick={toggle}
        className="p-2 rounded-lg hover:bg-muted/50 transition-colors text-muted-foreground hover:text-foreground"
        title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      >
        {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
      </button>

      {/* Popover */}
      {open && (
        <div className="absolute top-full right-0 mt-2 w-44 bg-card border border-border rounded-lg shadow-lg z-50 p-1.5 animate-fade-in">
          {AESTHETICS.map((a) => (
            <button
              key={a.id}
              onClick={() => { setAesthetic(a.id); setOpen(false); }}
              className={cn(
                "flex items-center gap-2.5 w-full px-3 py-2 rounded-md text-xs transition-colors",
                aesthetic === a.id
                  ? "bg-accent/10 text-accent font-medium"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/30"
              )}
            >
              <span className="w-3 h-3 rounded-full flex-shrink-0 border border-black/10" style={{ background: a.color }} />
              {a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
