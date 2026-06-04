import { StatusBadge } from "@/components/ui/status-badge";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useEffect, useState, useMemo } from "react";
import { api } from "@/lib/api";
import type { Conversion } from "@/types";
import { usePageTitle } from "@/lib/hooks";
import { Search, Code2, ChevronDown, ChevronUp, X } from "lucide-react";

function DiffView({ sasCode, pythonCode, fileName }: { sasCode: string; pythonCode: string; fileName: string }) {
  return (
    <div className="border border-border rounded-lg overflow-hidden bg-card">
      <div className="grid grid-cols-2 border-b border-border text-xs font-medium">
        <div className="flex items-center gap-2 px-3 py-2 bg-red-500/5 border-r border-border text-red-400 min-w-0">
          <Code2 className="w-3.5 h-3.5 flex-shrink-0" />
          <span className="truncate">{fileName}</span>
        </div>
        <div className="flex items-center gap-2 px-3 py-2 bg-green-500/5 text-green-400 min-w-0">
          <Code2 className="w-3.5 h-3.5 flex-shrink-0" />
          <span className="truncate">{fileName.replace(".sas", ".py")}</span>
        </div>
      </div>
      <div className="grid grid-cols-2 max-h-[500px]">
        <div className="overflow-y-auto border-r border-border min-w-0 bg-red-500/[0.02]">
          <pre className="text-xs font-mono text-foreground/80 whitespace-pre-wrap break-words p-3 leading-relaxed">{sasCode}</pre>
        </div>
        <div className="overflow-y-auto min-w-0 bg-green-500/[0.02]">
          <pre className="text-xs font-mono text-foreground/80 whitespace-pre-wrap break-words p-3 leading-relaxed">{pythonCode}</pre>
        </div>
      </div>
    </div>
  );
}

export default function AdminConversionsPage() {
  usePageTitle("Conversions");
  const [conversions, setConversions] = useState<Conversion[]>([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    api.get<Conversion[]>("/conversions").then((data) => setConversions(data ?? [])).catch(() => {});
  }, []);

  const filtered = useMemo(() => conversions.filter((c) => {
    const q = search.toLowerCase();
    if (q && !c.fileName.toLowerCase().includes(q) && !c.id.toLowerCase().includes(q)) return false;
    if (statusFilter !== "all" && c.status !== statusFilter) return false;
    return true;
  }), [conversions, search, statusFilter]);

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6 overflow-hidden">
      <div>
        <h1 className="text-2xl font-bold text-foreground">All Conversions</h1>
        <p className="text-sm text-muted-foreground mt-1">{filtered.length} of {conversions.length} conversions</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search by filename or ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-border bg-card text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
        </div>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="px-3 py-2 text-sm rounded-lg border border-border bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-accent/40">
          <option value="all">All Statuses</option>
          <option value="completed">Completed</option>
          <option value="running">Running</option>
          <option value="queued">Queued</option>
          <option value="partial">Partial</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {/* Table */}
      <div className="glass-panel overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">File</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Status</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Accuracy</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Duration</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Date</th>
              <th className="text-right text-xs font-medium text-muted-foreground px-4 py-3">Code</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filtered.map((conv) => (
              <tr key={conv.id} className="group">
                <td colSpan={6} className="p-0">
                  {/* Row */}
                  <div
                    className={cn("flex items-center hover:bg-muted/20 transition-colors cursor-pointer", expandedId === conv.id && "bg-muted/10")}
                    onClick={() => setExpandedId(expandedId === conv.id ? null : conv.id)}
                  >
                    <div className="px-4 py-3 flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{conv.fileName}</p>
                      <p className="text-[10px] text-muted-foreground font-mono">{conv.id}</p>
                    </div>
                    <div className="px-4 py-3 w-28"><StatusBadge status={conv.status} /></div>
                    <div className="px-4 py-3 w-24 text-sm text-foreground font-mono">{conv.accuracy > 0 ? `${conv.accuracy}%` : "—"}</div>
                    <div className="px-4 py-3 w-24 text-xs text-muted-foreground font-mono">{conv.duration > 0 ? `${conv.duration.toFixed(1)}s` : "—"}</div>
                    <div className="px-4 py-3 w-36 text-xs text-muted-foreground">{new Date(conv.createdAt).toLocaleString()}</div>
                    <div className="px-4 py-3 w-16 text-right">
                      {conv.sasCode && conv.pythonCode ? (
                        expandedId === conv.id
                          ? <ChevronUp className="w-4 h-4 text-accent inline-block" />
                          : <ChevronDown className="w-4 h-4 text-muted-foreground inline-block" />
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </div>
                  </div>

                  {/* Expanded diff view */}
                  {expandedId === conv.id && conv.sasCode && conv.pythonCode && (
                    <div className="px-4 pb-4">
                      <DiffView sasCode={conv.sasCode} pythonCode={conv.pythonCode} fileName={conv.fileName} />
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={6} className="text-center text-sm text-muted-foreground py-8">No conversions match your filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}
