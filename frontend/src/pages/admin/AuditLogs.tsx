import { StatusBadge } from "@/components/ui/status-badge";
import { motion } from "framer-motion";
import { useEffect, useState, useMemo } from "react";
import { api } from "@/lib/api";
import type { AuditLog } from "@/types";
import { usePageTitle } from "@/lib/hooks";
import { Search } from "lucide-react";

export default function AuditLogsPage() {
  usePageTitle("Audit Logs");
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [modelFilter, setModelFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    api.get<AuditLog[]>("/admin/audit-logs").then(setAuditLogs).catch(() => {});
  }, []);

  const models = useMemo(() => {
    const unique = [...new Set(auditLogs.map((l) => l.model))].sort();
    return ["all", ...unique];
  }, [auditLogs]);

  const filtered = useMemo(() => {
    return auditLogs.filter((log) => {
      const matchesModel = modelFilter === "all" || log.model === modelFilter;
      const matchesStatus =
        statusFilter === "all" ||
        (statusFilter === "success" && log.success) ||
        (statusFilter === "failed" && !log.success);
      const matchesSearch = !search || log.promptHash.toLowerCase().includes(search.toLowerCase());
      return matchesModel && matchesStatus && matchesSearch;
    });
  }, [auditLogs, modelFilter, statusFilter, search]);

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">LLM Audit Logs</h1>
        <p className="text-sm text-muted-foreground mt-1">{filtered.length} of {auditLogs.length} entries</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search by prompt hash..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-border bg-card text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
        </div>
        <select
          value={modelFilter}
          onChange={(e) => setModelFilter(e.target.value)}
          className="px-3 py-2 text-sm rounded-lg border border-border bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-accent/40"
        >
          {models.map((m) => (
            <option key={m} value={m}>{m === "all" ? "All Models" : m}</option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 text-sm rounded-lg border border-border bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-accent/40"
        >
          <option value="all">All Statuses</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {/* Table */}
      <div className="glass-panel overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Model</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Latency</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Cost</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Prompt Hash</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Status</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Timestamp</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filtered.map((log) => (
              <tr key={log.id} className="hover:bg-muted/20 transition-colors">
                <td className="px-4 py-3 text-sm font-mono text-foreground">{log.model}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground font-mono">{log.latency}ms</td>
                <td className="px-4 py-3 text-xs text-muted-foreground font-mono">${log.cost.toFixed(4)}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground font-mono">{log.promptHash}</td>
                <td className="px-4 py-3"><StatusBadge status={log.success ? "completed" : "failed"} /></td>
                <td className="px-4 py-3 text-xs text-muted-foreground">{new Date(log.timestamp).toLocaleString()}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="text-center text-sm text-muted-foreground py-8">
                  No logs match your filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}
