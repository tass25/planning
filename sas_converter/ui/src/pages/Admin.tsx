import { StatCard } from "@/components/ui/stat-card";
import { useConversionStore } from "@/store/conversion-store";
import { FileCode, CheckCircle, AlertTriangle, XCircle, Clock } from "lucide-react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";

const adminLinks = [
  { label: "Audit Logs", path: "/admin/audit-logs", desc: "LLM call history and costs" },
  { label: "System Health", path: "/admin/system-health", desc: "Infrastructure monitoring" },
  { label: "User Management", path: "/admin/users", desc: "Manage user accounts" },
  { label: "Pipeline Config", path: "/admin/pipeline-config", desc: "Pipeline settings" },
  { label: "File Registry", path: "/admin/file-registry", desc: "File dependencies & lineage" },
  { label: "KB Management", path: "/admin/kb-management", desc: "Knowledge base admin" },
  { label: "KB Changelog", path: "/admin/kb-changelog", desc: "KB mutation history" },
];

export default function AdminPage() {
  const conversions = useConversionStore((s) => s.conversions);
  const total = conversions.length;
  const completed = conversions.filter((c) => c.status === "completed").length;
  const partial = conversions.filter((c) => c.status === "partial").length;
  const failed = conversions.filter((c) => c.status === "failed").length;
  const avgLatency = conversions.filter((c) => c.duration > 0).reduce((a, c) => a + c.duration, 0) / (completed + partial + failed || 1);

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Admin Dashboard</h1>
        <p className="text-sm text-muted-foreground mt-1">System overview and management</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard title="Total Conversions" value={total} icon={FileCode} variant="accent" />
        <StatCard title="Success Rate" value={total ? `${((completed / total) * 100).toFixed(0)}%` : "—"} icon={CheckCircle} variant="success" />
        <StatCard title="Partial Rate" value={total ? `${((partial / total) * 100).toFixed(0)}%` : "—"} icon={AlertTriangle} />
        <StatCard title="Failure Rate" value={total ? `${((failed / total) * 100).toFixed(0)}%` : "—"} icon={XCircle} variant="destructive" />
        <StatCard title="Avg Latency" value={`${avgLatency.toFixed(1)}s`} icon={Clock} variant="secondary" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {adminLinks.map((link) => (
          <Link key={link.path} to={link.path} className="glass-panel p-5 hover:border-accent/30 hover:glow-accent transition-all duration-300 group">
            <h3 className="text-sm font-semibold text-foreground group-hover:text-accent transition-colors">{link.label}</h3>
            <p className="text-xs text-muted-foreground mt-1">{link.desc}</p>
          </Link>
        ))}
      </div>
    </motion.div>
  );
}
