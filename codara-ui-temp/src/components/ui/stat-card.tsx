import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  trend?: { value: number; positive: boolean };
  variant?: "default" | "accent" | "secondary" | "success" | "destructive";
  className?: string;
}

const variantStyles = {
  default: "from-card to-card",
  accent: "from-accent/10 to-card",
  secondary: "from-secondary/10 to-card",
  success: "from-success/10 to-card",
  destructive: "from-destructive/10 to-card",
};

export function StatCard({ title, value, subtitle, icon: Icon, trend, variant = "default", className }: StatCardProps) {
  return (
    <div className={cn("glass-panel p-5 bg-gradient-to-br", variantStyles[variant], className)}>
      <div className="flex items-start justify-between mb-3">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{title}</span>
        <Icon className="w-4 h-4 text-muted-foreground" />
      </div>
      <div className="flex items-end gap-2">
        <span className="text-2xl font-bold text-foreground">{value}</span>
        {trend && (
          <span className={cn("text-xs font-medium mb-0.5", trend.positive ? "text-success" : "text-destructive")}>
            {trend.positive ? "+" : ""}{trend.value}%
          </span>
        )}
      </div>
      {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
    </div>
  );
}
