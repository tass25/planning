import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
}

export function EmptyState({ icon: Icon, title, description, actionLabel, actionHref, onAction }: EmptyStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col items-center justify-center py-20 px-6 text-center"
    >
      <div className="w-20 h-20 rounded-2xl bg-muted/50 border border-border/50 flex items-center justify-center mb-6">
        <Icon className="w-9 h-9 text-muted-foreground/40" />
      </div>
      <h3 className="text-lg font-semibold text-foreground mb-2">{title}</h3>
      <p className="text-sm text-muted-foreground max-w-sm leading-relaxed">{description}</p>
      {actionLabel && (actionHref ? (
        <Link to={actionHref} className="mt-6">
          <Button size="sm" className="bg-accent text-accent-foreground hover:bg-accent/90">{actionLabel}</Button>
        </Link>
      ) : onAction ? (
        <Button size="sm" className="mt-6 bg-accent text-accent-foreground hover:bg-accent/90" onClick={onAction}>{actionLabel}</Button>
      ) : null)}
    </motion.div>
  );
}
