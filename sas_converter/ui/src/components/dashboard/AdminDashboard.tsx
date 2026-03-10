import { StatCard } from "@/components/ui/stat-card";
import { useConversionStore } from "@/store/conversion-store";
import { useUserStore } from "@/store/user-store";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AnalyticsData, AuditLog, User, SystemService } from "@/types";
import { FileCode, CheckCircle, AlertTriangle, XCircle, Clock, Users, Activity, DollarSign, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from "recharts";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export default function AdminDashboard() {
  const conversions = useConversionStore((s) => s.conversions);
  const user = useUserStore((s) => s.currentUser);
  const [analytics, setAnalytics] = useState<AnalyticsData[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [services, setServices] = useState<SystemService[]>([]);

  useEffect(() => {
    api.get<AnalyticsData[]>("/analytics").then(setAnalytics).catch(() => {});
    api.get<AuditLog[]>("/admin/audit-logs").then(setAuditLogs).catch(() => {});
    api.get<User[]>("/admin/users").then(setUsers).catch(() => {});
    api.get<SystemService[]>("/admin/system-health").then(setServices).catch(() => {});
  }, []);

  const total = conversions.length;
  const completed = conversions.filter((c) => c.status === "completed").length;
  const partial = conversions.filter((c) => c.status === "partial").length;
  const failed = conversions.filter((c) => c.status === "failed").length;
  const avgLatency = conversions.filter((c) => c.duration > 0).reduce((a, c) => a + c.duration, 0) / (completed + partial + failed || 1);
  const totalCost = auditLogs.reduce((a, l) => a + l.cost, 0);

  const greeting = new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 18 ? "Good afternoon" : "Good evening";

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">{greeting}, {user?.name?.split(" ")[0] || "Admin"}</h1>
        <p className="text-sm text-muted-foreground mt-1">System overview and platform health</p>
      </div>

      {/* System Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard title="Total Conversions" value={total} icon={FileCode} trend={{ value: 18, positive: true }} variant="accent" />
        <StatCard title="Success Rate" value={`${total > 0 ? ((completed / total) * 100).toFixed(0) : 0}%`} icon={CheckCircle} variant="success" />
        <StatCard title="Failure Rate" value={`${total > 0 ? ((failed / total) * 100).toFixed(0) : 0}%`} icon={XCircle} variant="destructive" />
        <StatCard title="Avg Latency" value={`${avgLatency.toFixed(1)}s`} icon={Clock} />
        <StatCard title="LLM Costs" value={`$${totalCost.toFixed(2)}`} icon={DollarSign} variant="secondary" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Conversion Trends */}
        <div className="glass-panel p-5 lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-foreground">Platform Conversion Trends</h2>
            <Link to="/analytics" className="text-xs text-accent hover:underline flex items-center gap-1">Details <ArrowRight className="w-3 h-3" /></Link>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={analytics.slice(-14)}>
              <defs>
                <linearGradient id="adminColorConv" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(var(--chart-accent))" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="hsl(var(--chart-accent))" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="adminColorFail" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(var(--chart-destructive))" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="hsl(var(--chart-destructive))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "hsl(var(--chart-muted))" }} tickFormatter={(v) => v.slice(5)} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "hsl(var(--chart-muted))" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12, color: "hsl(var(--foreground))" }} />
              <Area type="monotone" dataKey="conversions" stroke="hsl(var(--chart-accent))" fill="url(#adminColorConv)" strokeWidth={2} />
              <Area type="monotone" dataKey="failures" stroke="hsl(var(--chart-destructive))" fill="url(#adminColorFail)" strokeWidth={1.5} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* System Health */}
        <div className="glass-panel p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-foreground">System Health</h2>
            <Link to="/admin/system-health" className="text-xs text-accent hover:underline flex items-center gap-1">View <ArrowRight className="w-3 h-3" /></Link>
          </div>
          <div className="space-y-3">
            {services.map((svc) => (
              <div key={svc.name} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={cn("w-2 h-2 rounded-full", svc.status === "online" ? "bg-success" : svc.status === "degraded" ? "bg-warning" : "bg-destructive")} />
                  <span className="text-sm text-foreground">{svc.name}</span>
                </div>
                <div className="text-right">
                  <span className="text-xs text-muted-foreground font-mono">{svc.latency}ms</span>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-5 pt-4 border-t border-border">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-muted-foreground flex items-center gap-1.5"><Users className="w-3 h-3" /> Active Users</span>
              <span className="text-sm font-semibold text-foreground">{users.filter((u) => u.status === "active").length}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground flex items-center gap-1.5"><Activity className="w-3 h-3" /> LLM Calls Today</span>
              <span className="text-sm font-semibold text-foreground">{auditLogs.length}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Latency Chart + Quick Admin Links */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-panel p-5">
          <h2 className="text-sm font-semibold text-foreground mb-4">Avg Latency (seconds)</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={analytics.slice(-10)}>
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "hsl(var(--chart-muted))" }} tickFormatter={(v) => v.slice(5)} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "hsl(var(--chart-muted))" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12, color: "hsl(var(--foreground))" }} />
              <Bar dataKey="avgLatency" fill="hsl(var(--chart-secondary))" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="glass-panel p-5">
          <h2 className="text-sm font-semibold text-foreground mb-4">Admin Quick Access</h2>
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: "Audit Logs", path: "/admin/audit-logs", desc: "LLM call history" },
              { label: "Users", path: "/admin/users", desc: "Manage accounts" },
              { label: "Pipeline Config", path: "/admin/pipeline-config", desc: "Retry & timeout settings" },
              { label: "KB Management", path: "/admin/kb-management", desc: "Translation patterns" },
              { label: "File Registry", path: "/admin/file-registry", desc: "File dependencies" },
              { label: "KB Changelog", path: "/admin/kb-changelog", desc: "Mutation history" },
            ].map((link) => (
              <Link key={link.path} to={link.path} className="p-3 rounded-lg border border-border hover:border-accent/30 hover:bg-muted/30 transition-all group">
                <h3 className="text-xs font-semibold text-foreground group-hover:text-accent transition-colors">{link.label}</h3>
                <p className="text-[10px] text-muted-foreground mt-0.5">{link.desc}</p>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  );
}