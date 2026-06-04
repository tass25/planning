import { useConversionStore } from "@/store/conversion-store";
import { StatusBadge } from "@/components/ui/status-badge";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import { usePageTitle } from "@/lib/hooks";
import { EmptyState } from "@/components/EmptyState";
import { FileCode, Search, GitCompare, X, ArrowUp, ArrowDown, Minus, Clock, Award, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Conversion } from "@/types";

export default function HistoryPage() {
  usePageTitle("History");
  const conversions = useConversionStore((s) => s.conversions);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [runtimeFilter, setRuntimeFilter] = useState<string>("all");
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [showCompare, setShowCompare] = useState(false);

  const toggleCompare = (id: string) => {
    setCompareIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 2 ? [...prev, id] : [prev[1], id]
    );
  };

  const compareA = conversions.find((c) => c.id === compareIds[0]);
  const compareB = conversions.find((c) => c.id === compareIds[1]);

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
      <div className="flex items-center gap-3 flex-wrap">
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
        <div className="ml-auto flex items-center gap-2">
          {compareIds.length > 0 && (
            <button onClick={() => setCompareIds([])} className="text-xs text-muted-foreground hover:text-foreground transition-colors">
              Clear selection
            </button>
          )}
          <Button
            variant="outline"
            size="sm"
            disabled={compareIds.length < 2}
            onClick={() => setShowCompare(true)}
            className={cn("gap-1.5", compareIds.length === 2 && "border-accent text-accent")}
          >
            <GitCompare className="w-3.5 h-3.5" />
            Compare{compareIds.length > 0 && ` (${compareIds.length}/2)`}
          </Button>
        </div>
      </div>

      {/* Table (desktop) / Cards (mobile) */}
      <div className="glass-panel overflow-hidden">
        {/* Desktop table */}
        <table className="w-full hidden md:table">
          <thead>
            <tr className="border-b border-border">
              <th className="w-10 px-3 py-3"><GitCompare className="w-3.5 h-3.5 text-muted-foreground" /></th>
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
              <tr key={c.id} className={cn("hover:bg-muted/20 transition-colors", compareIds.includes(c.id) && "bg-accent/5")}>
                <td className="px-3 py-3">
                  <button onClick={() => toggleCompare(c.id)} className={cn(
                    "w-5 h-5 rounded border-2 flex items-center justify-center transition-all",
                    compareIds.includes(c.id) ? "border-accent bg-accent text-accent-foreground" : "border-border hover:border-accent/50"
                  )}>
                    {compareIds.includes(c.id) && <span className="text-[10px] font-bold">{compareIds.indexOf(c.id) + 1}</span>}
                  </button>
                </td>
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

        {/* Mobile cards */}
        <div className="md:hidden divide-y divide-border">
          {filtered.map((c) => (
            <div key={c.id} className={cn("flex items-center px-4 py-3 hover:bg-muted/20 transition-colors", compareIds.includes(c.id) && "bg-accent/5")}>
              <button onClick={() => toggleCompare(c.id)} className={cn(
                "w-5 h-5 rounded border-2 flex items-center justify-center transition-all flex-shrink-0 mr-3",
                compareIds.includes(c.id) ? "border-accent bg-accent text-accent-foreground" : "border-border"
              )}>
                {compareIds.includes(c.id) && <span className="text-[10px] font-bold">{compareIds.indexOf(c.id) + 1}</span>}
              </button>
              <Link to={`/workspace/${c.id}`} className="flex items-center justify-between flex-1 min-w-0">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{c.fileName}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <StatusBadge status={c.status} />
                    <span className="text-[10px] text-muted-foreground">{new Date(c.createdAt).toLocaleDateString()}</span>
                    {c.duration > 0 && <span className="text-[10px] text-muted-foreground font-mono">{c.duration}s</span>}
                  </div>
                </div>
                {c.accuracy > 0 && <span className="text-xs font-semibold text-success ml-3">{c.accuracy}%</span>}
              </Link>
            </div>
          ))}
        </div>
        {filtered.length === 0 && conversions.length === 0 && (
          <EmptyState icon={FileCode} title="No conversions yet" description="Upload and convert your first SAS file to see your conversion history here." actionLabel="Start Converting" actionHref="/conversions" />
        )}
        {filtered.length === 0 && conversions.length > 0 && (
          <EmptyState icon={Search} title="No matches" description="No conversions match your current filters. Try adjusting your selection." />
        )}
      </div>
      {/* Comparison Panel */}
      <AnimatePresence>
        {showCompare && compareA && compareB && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="glass-panel p-6 space-y-5"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <GitCompare className="w-5 h-5 text-accent" /> Comparison
              </h2>
              <button onClick={() => setShowCompare(false)} className="text-muted-foreground hover:text-foreground transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Side-by-side header */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-muted/30 rounded-lg p-4 border border-border">
                <p className="text-xs text-muted-foreground mb-1">Conversion A</p>
                <p className="text-sm font-semibold text-foreground truncate">{compareA.fileName}</p>
                <div className="flex items-center gap-2 mt-1.5">
                  <StatusBadge status={compareA.status} />
                  <span className="text-[10px] text-muted-foreground">{new Date(compareA.createdAt).toLocaleDateString()}</span>
                </div>
              </div>
              <div className="bg-muted/30 rounded-lg p-4 border border-border">
                <p className="text-xs text-muted-foreground mb-1">Conversion B</p>
                <p className="text-sm font-semibold text-foreground truncate">{compareB.fileName}</p>
                <div className="flex items-center gap-2 mt-1.5">
                  <StatusBadge status={compareB.status} />
                  <span className="text-[10px] text-muted-foreground">{new Date(compareB.createdAt).toLocaleDateString()}</span>
                </div>
              </div>
            </div>

            {/* Metrics comparison */}
            <div className="grid grid-cols-3 gap-4">
              {(() => {
                const metrics: { label: string; icon: typeof Award; a: string; b: string; diff: number; unit: string }[] = [
                  {
                    label: "Accuracy",
                    icon: Award,
                    a: compareA.accuracy > 0 ? `${compareA.accuracy}%` : "—",
                    b: compareB.accuracy > 0 ? `${compareB.accuracy}%` : "—",
                    diff: compareB.accuracy - compareA.accuracy,
                    unit: "pp",
                  },
                  {
                    label: "Duration",
                    icon: Clock,
                    a: compareA.duration > 0 ? `${compareA.duration}s` : "—",
                    b: compareB.duration > 0 ? `${compareB.duration}s` : "—",
                    diff: compareA.duration - compareB.duration,
                    unit: "s faster",
                  },
                  {
                    label: "Stages Passed",
                    icon: Zap,
                    a: `${compareA.stages.filter((s) => s.status === "completed").length}/${compareA.stages.length}`,
                    b: `${compareB.stages.filter((s) => s.status === "completed").length}/${compareB.stages.length}`,
                    diff: compareB.stages.filter((s) => s.status === "completed").length - compareA.stages.filter((s) => s.status === "completed").length,
                    unit: "",
                  },
                ];
                return metrics.map((m) => (
                  <div key={m.label} className="glass-panel p-4 text-center">
                    <m.icon className="w-4 h-4 text-muted-foreground mx-auto mb-2" />
                    <p className="text-[10px] text-muted-foreground mb-2">{m.label}</p>
                    <div className="flex items-center justify-center gap-3">
                      <span className="text-sm font-bold text-foreground">{m.a}</span>
                      <span className="text-muted-foreground">→</span>
                      <span className="text-sm font-bold text-foreground">{m.b}</span>
                    </div>
                    {m.diff !== 0 && (
                      <div className={cn("flex items-center justify-center gap-1 mt-1.5 text-xs font-medium", m.diff > 0 ? "text-success" : "text-destructive")}>
                        {m.diff > 0 ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />}
                        {Math.abs(m.diff)}{m.unit}
                      </div>
                    )}
                    {m.diff === 0 && (
                      <div className="flex items-center justify-center gap-1 mt-1.5 text-xs text-muted-foreground">
                        <Minus className="w-3 h-3" /> Same
                      </div>
                    )}
                  </div>
                ));
              })()}
            </div>

            {/* Code line counts */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-muted/30 rounded-lg p-4 border border-border">
                <p className="text-xs text-muted-foreground mb-2">Output Size</p>
                <p className="text-lg font-bold text-foreground">{compareA.pythonCode?.split("\n").length || 0} <span className="text-xs font-normal text-muted-foreground">lines</span></p>
              </div>
              <div className="bg-muted/30 rounded-lg p-4 border border-border">
                <p className="text-xs text-muted-foreground mb-2">Output Size</p>
                <p className="text-lg font-bold text-foreground">{compareB.pythonCode?.split("\n").length || 0} <span className="text-xs font-normal text-muted-foreground">lines</span></p>
              </div>
            </div>

            <div className="flex justify-center gap-3">
              <Link to={`/workspace/${compareA.id}`}>
                <Button variant="outline" size="sm" className="gap-1.5">Open A in Workspace</Button>
              </Link>
              <Link to={`/workspace/${compareB.id}`}>
                <Button variant="outline" size="sm" className="gap-1.5">Open B in Workspace</Button>
              </Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
