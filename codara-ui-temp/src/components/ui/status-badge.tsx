import { cn } from "@/lib/utils";
import type { ConversionStatus, RiskLevel, StageStatus } from "@/types";

interface StatusBadgeProps {
  status: ConversionStatus | StageStatus;
  className?: string;
}

const statusStyles: Record<string, string> = {
  completed: "bg-success/15 text-success border-success/20",
  running: "bg-accent/15 text-accent border-accent/20",
  pending: "bg-muted text-muted-foreground border-border",
  failed: "bg-destructive/15 text-destructive border-destructive/20",
  partial: "bg-warning/15 text-warning border-warning/20",
  queued: "bg-muted text-muted-foreground border-border",
  skipped: "bg-muted text-muted-foreground border-border",
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border", statusStyles[status] || statusStyles.pending, className)}>
      {status === "running" && <span className="w-1.5 h-1.5 rounded-full bg-current mr-1.5 animate-pulse-glow" />}
      {status}
    </span>
  );
}

interface RiskBadgeProps {
  level: RiskLevel;
  className?: string;
}

const riskStyles: Record<RiskLevel, string> = {
  low: "bg-success/15 text-success border-success/20",
  medium: "bg-warning/15 text-warning border-warning/20",
  high: "bg-destructive/15 text-destructive border-destructive/20",
};

export function RiskBadge({ level, className }: RiskBadgeProps) {
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border capitalize", riskStyles[level], className)}>
      {level}
    </span>
  );
}
