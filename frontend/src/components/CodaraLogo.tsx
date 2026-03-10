import { cn } from "@/lib/utils";

interface CodaraLogoProps {
  size?: "sm" | "md" | "lg" | "xl";
  showText?: boolean;
  variant?: "default" | "light";
  className?: string;
}

export function CodaraLogo({ size = "md", showText = true, variant = "default", className }: CodaraLogoProps) {
  const sizes = {
    sm: { icon: "w-7 h-7", text: "text-base", gap: "gap-2" },
    md: { icon: "w-9 h-9", text: "text-xl", gap: "gap-2.5" },
    lg: { icon: "w-11 h-11", text: "text-2xl", gap: "gap-3" },
    xl: { icon: "w-14 h-14", text: "text-3xl", gap: "gap-3.5" },
  };
  const s = sizes[size];

  const textColor = variant === "light" ? "text-white" : "text-foreground";
  const subtextColor = variant === "light" ? "text-white/70" : "text-accent";

  return (
    <div className={cn("flex items-center", s.gap, className)}>
      <div className={cn("relative flex-shrink-0", s.icon)}>
        <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
          {/* Background shield/diamond shape */}
          <rect x="4" y="4" width="40" height="40" rx="12" fill="url(#logo-bg)" />
          
          {/* Subtle inner glow */}
          <rect x="4" y="4" width="40" height="40" rx="12" fill="url(#logo-inner-glow)" />

          {/* Code bracket left < */}
          <path
            d="M18 16L10 24L18 32"
            stroke="white"
            strokeWidth="2.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity="0.95"
          />
          
          {/* Arrow / transform indicator → */}
          <path
            d="M22 24H36M32 19.5L37 24L32 28.5"
            stroke="white"
            strokeWidth="2.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity="0.95"
          />

          {/* Accent dot - pipeline node */}
          <circle cx="20" cy="24" r="2" fill="hsl(38, 92%, 50%)" />

          <defs>
            <linearGradient id="logo-bg" x1="4" y1="4" x2="44" y2="44" gradientUnits="userSpaceOnUse">
              <stop stopColor="hsl(250, 45%, 18%)" />
              <stop offset="0.4" stopColor="hsl(255, 50%, 22%)" />
              <stop offset="1" stopColor="hsl(270, 55%, 28%)" />
            </linearGradient>
            <radialGradient id="logo-inner-glow" cx="0.3" cy="0.3" r="0.8">
              <stop stopColor="hsl(270, 60%, 40%)" stopOpacity="0.3" />
              <stop offset="1" stopColor="transparent" stopOpacity="0" />
            </radialGradient>
          </defs>
        </svg>
      </div>
      {showText && (
        <div className="flex flex-col leading-none">
          <span className={cn("font-extrabold tracking-tight", s.text, textColor)}>
            cod<span className={subtextColor}>ara</span>
          </span>
          {(size === "lg" || size === "xl") && (
            <span className={cn("text-[10px] font-medium tracking-[0.2em] uppercase mt-0.5", variant === "light" ? "text-white/40" : "text-muted-foreground")}>
              SAS → Python
            </span>
          )}
        </div>
      )}
    </div>
  );
}
