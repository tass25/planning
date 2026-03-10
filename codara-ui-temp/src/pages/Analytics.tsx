import { mockAnalytics, failureModes } from "@/lib/mock/data";
import { motion } from "framer-motion";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell } from "recharts";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";

const COLORS = [
  "hsl(var(--chart-accent))",
  "hsl(var(--chart-secondary))",
  "hsl(var(--chart-success))",
  "hsl(var(--chart-destructive))",
  "hsl(var(--chart-muted))",
];

const tooltipStyle = {
  background: "hsl(var(--card))",
  border: "1px solid hsl(var(--border))",
  borderRadius: 8,
  fontSize: 12,
  color: "hsl(var(--foreground))",
};

const tickStyle = { fontSize: 10, fill: "hsl(var(--chart-muted))" };

export default function AnalyticsPage() {
  const handleExport = (format: "csv" | "json") => {
    const data = format === "json" ? JSON.stringify(mockAnalytics, null, 2) : "date,conversions,successRate,avgLatency,failures\n" + mockAnalytics.map((d) => `${d.date},${d.conversions},${d.successRate},${d.avgLatency},${d.failures}`).join("\n");
    const blob = new Blob([data], { type: format === "json" ? "application/json" : "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `analytics.${format}`; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Analytics</h1>
          <p className="text-sm text-muted-foreground mt-1">Platform performance and conversion metrics</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => handleExport("csv")} className="border-border text-muted-foreground hover:text-foreground">
            <Download className="w-3.5 h-3.5 mr-1.5" />CSV
          </Button>
          <Button variant="outline" size="sm" onClick={() => handleExport("json")} className="border-border text-muted-foreground hover:text-foreground">
            <Download className="w-3.5 h-3.5 mr-1.5" />JSON
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-panel p-5">
          <h2 className="text-sm font-semibold text-foreground mb-4">Success Rate Over Time</h2>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={mockAnalytics}>
              <defs>
                <linearGradient id="colorSuccess" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(var(--chart-success))" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="hsl(var(--chart-success))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={tickStyle} tickFormatter={(v) => v.slice(5)} axisLine={false} tickLine={false} />
              <YAxis domain={[70, 100]} tick={tickStyle} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Area type="monotone" dataKey="successRate" stroke="hsl(var(--chart-success))" fill="url(#colorSuccess)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="glass-panel p-5">
          <h2 className="text-sm font-semibold text-foreground mb-4">Failure Mode Distribution</h2>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={failureModes} cx="50%" cy="50%" innerRadius={60} outerRadius={90} paddingAngle={3} dataKey="value">
                {failureModes.map((_, i) => <Cell key={i} fill={COLORS[i]} />)}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-3 mt-2 justify-center">
            {failureModes.map((f, i) => (
              <div key={f.name} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS[i] }} />{f.name}
              </div>
            ))}
          </div>
        </div>

        <div className="glass-panel p-5">
          <h2 className="text-sm font-semibold text-foreground mb-4">Average Latency (seconds)</h2>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={mockAnalytics.slice(-14)}>
              <XAxis dataKey="date" tick={tickStyle} tickFormatter={(v) => v.slice(5)} axisLine={false} tickLine={false} />
              <YAxis tick={tickStyle} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="avgLatency" fill="hsl(var(--chart-secondary))" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="glass-panel p-5">
          <h2 className="text-sm font-semibold text-foreground mb-4">CodeBLEU Score (Simulated)</h2>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={mockAnalytics.map((d) => ({ ...d, codeBLEU: (d.successRate * 0.95 + Math.random() * 3).toFixed(1) }))}>
              <defs>
                <linearGradient id="colorBleu" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(var(--chart-accent))" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="hsl(var(--chart-accent))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={tickStyle} tickFormatter={(v) => v.slice(5)} axisLine={false} tickLine={false} />
              <YAxis domain={[70, 100]} tick={tickStyle} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Area type="monotone" dataKey="codeBLEU" stroke="hsl(var(--chart-accent))" fill="url(#colorBleu)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </motion.div>
  );
}