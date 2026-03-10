import { StatusBadge } from "@/components/ui/status-badge";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AuditLog } from "@/types";

export default function AuditLogsPage() {
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  useEffect(() => { api.get<AuditLog[]>("/admin/audit-logs").then(setAuditLogs).catch(() => {}); }, []);

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">LLM Audit Logs</h1>
        <p className="text-sm text-muted-foreground mt-1">{auditLogs.length} log entries</p>
      </div>

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
            {auditLogs.map((log) => (
              <tr key={log.id} className="hover:bg-muted/20 transition-colors">
                <td className="px-4 py-3 text-sm font-mono text-foreground">{log.model}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground font-mono">{log.latency}ms</td>
                <td className="px-4 py-3 text-xs text-muted-foreground font-mono">${log.cost.toFixed(4)}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground font-mono">{log.promptHash}</td>
                <td className="px-4 py-3"><StatusBadge status={log.success ? "completed" : "failed"} /></td>
                <td className="px-4 py-3 text-xs text-muted-foreground">{new Date(log.timestamp).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}
