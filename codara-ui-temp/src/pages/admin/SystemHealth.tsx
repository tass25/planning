import { mockSystemServices } from "@/lib/mock/data";
import { cn } from "@/lib/utils";
import { motion } from "framer-motion";
import { Circle } from "lucide-react";

const statusColors = {
  online: "text-success fill-success",
  degraded: "text-warning fill-warning",
  offline: "text-destructive fill-destructive",
};

export default function SystemHealthPage() {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">System Health</h1>
        <p className="text-sm text-muted-foreground mt-1">Infrastructure monitoring</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {mockSystemServices.map((service) => (
          <div key={service.name} className="glass-panel p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-foreground">{service.name}</h3>
              <div className="flex items-center gap-1.5">
                <Circle className={cn("w-2.5 h-2.5", statusColors[service.status])} />
                <span className={cn("text-xs font-medium capitalize", statusColors[service.status].split(" ")[0])}>{service.status}</span>
              </div>
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">Latency</span>
                <span className="text-foreground font-mono">{service.latency}ms</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">Uptime</span>
                <span className="text-foreground font-mono">{service.uptime}%</span>
              </div>
              <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                <div className={cn("h-full rounded-full transition-all", service.status === "online" ? "bg-success" : service.status === "degraded" ? "bg-warning" : "bg-destructive")} style={{ width: `${service.uptime}%` }} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
