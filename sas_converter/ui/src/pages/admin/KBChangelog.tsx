import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { KBChangelogEntry } from "@/types";

const actionColors: Record<string, string> = {
  add: "bg-success/15 text-success border-success/20",
  edit: "bg-accent/15 text-accent border-accent/20",
  rollback: "bg-warning/15 text-warning border-warning/20",
  delete: "bg-destructive/15 text-destructive border-destructive/20",
};

export default function KBChangelogPage() {
  const [changelog, setChangelog] = useState<KBChangelogEntry[]>([]);
  useEffect(() => { api.get<KBChangelogEntry[]>("/kb/changelog").then(setChangelog).catch(() => {}); }, []);

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">KB Changelog</h1>
        <p className="text-sm text-muted-foreground mt-1">Knowledge base mutation history</p>
      </div>

      <div className="space-y-0 relative">
        <div className="absolute left-[19px] top-0 bottom-0 w-px bg-border" />
        {changelog.map((entry) => (
          <div key={entry.id} className="flex gap-4 pb-6 relative">
            <div className={cn("w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 border text-xs font-medium z-10", actionColors[entry.action])}>
              {entry.action[0].toUpperCase()}
            </div>
            <div className="pt-1.5">
              <p className="text-sm text-foreground">{entry.description}</p>
              <div className="flex items-center gap-3 mt-1">
                <span className="text-xs text-muted-foreground">{entry.user}</span>
                <span className="text-xs text-muted-foreground">{new Date(entry.timestamp).toLocaleString()}</span>
                <span className={cn("text-xs px-1.5 py-0.5 rounded border capitalize", actionColors[entry.action])}>{entry.action}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
