import { useConversionStore } from "@/store/conversion-store";
import { StatusBadge } from "@/components/ui/status-badge";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useState } from "react";
import { cn } from "@/lib/utils";

export default function HistoryPage() {
  const conversions = useConversionStore((s) => s.conversions);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [runtimeFilter, setRuntimeFilter] = useState<string>("all");

  const filtered = conversions.filter((c) => {
    if (statusFilter !== "all" && c.status !== statusFilter) return false;
    if (runtimeFilter !== "all" && c.runtime !== runtimeFilter) return false;
    return true;
  });

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Conversion History</h1>
        <p className="text-sm text-muted-foreground mt-1">{conversions.length} total conversions</p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1 bg-muted/30 rounded-lg p-1">
          {["all", "completed", "running", "failed", "partial"].map((s) => (
            <button key={s} onClick={() => setStatusFilter(s)} className={cn(
              "px-3 py-1 rounded-md text-xs font-medium transition-colors capitalize",
              statusFilter === s ? "bg-card text-foreground" : "text-muted-foreground hover:text-foreground"
            )}>{s}</button>
          ))}
        </div>
        <div className="flex items-center gap-1 bg-muted/30 rounded-lg p-1">
          {["all", "python"].map((r) => (
            <button key={r} onClick={() => setRuntimeFilter(r)} className={cn(
              "px-3 py-1 rounded-md text-xs font-medium transition-colors capitalize",
              runtimeFilter === r ? "bg-card text-foreground" : "text-muted-foreground hover:text-foreground"
            )}>{r}</button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="glass-panel overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">File Name</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Date</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Runtime</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Status</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Duration</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Accuracy</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filtered.map((c) => (
              <tr key={c.id} className="hover:bg-muted/20 transition-colors">
                <td className="px-4 py-3">
                  <Link to={`/workspace/${c.id}`} className="text-sm font-medium text-foreground hover:text-accent transition-colors">{c.fileName}</Link>
                </td>
                <td className="px-4 py-3 text-xs text-muted-foreground">{new Date(c.createdAt).toLocaleDateString()}</td>
                <td className="px-4 py-3"><span className="text-xs font-mono text-muted-foreground">{c.runtime}</span></td>
                <td className="px-4 py-3"><StatusBadge status={c.status} /></td>
                <td className="px-4 py-3 text-xs text-muted-foreground font-mono">{c.duration > 0 ? `${c.duration}s` : "—"}</td>
                <td className="px-4 py-3 text-xs font-medium">{c.accuracy > 0 ? <span className="text-success">{c.accuracy}%</span> : <span className="text-muted-foreground">—</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="text-center py-12 text-sm text-muted-foreground">No conversions match your filters</div>
        )}
      </div>
    </motion.div>
  );
}
