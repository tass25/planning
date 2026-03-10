import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { PipelineConfig } from "@/types";

export default function PipelineConfigPage() {
  const [config, setConfig] = useState<PipelineConfig>({ maxRetries: 3, timeout: 300, checkpointInterval: 60 });
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.get("/admin/pipeline-config").then((data) => setConfig(data)).catch(() => {});
  }, []);

  const handleSave = async () => {
    try {
      await api.put("/admin/pipeline-config", config);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch { /* toast error */ }
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Pipeline Configuration</h1>
        <p className="text-sm text-muted-foreground mt-1">Adjust pipeline execution parameters</p>
      </div>

      <div className="glass-panel p-6 max-w-lg space-y-5">
        {[
          { key: "maxRetries" as const, label: "Max Retries", desc: "Maximum retry attempts per stage", min: 0, max: 10 },
          { key: "timeout" as const, label: "Timeout (seconds)", desc: "Maximum time per stage", min: 30, max: 900 },
          { key: "checkpointInterval" as const, label: "Checkpoint Interval (seconds)", desc: "How often to save progress", min: 10, max: 300 },
        ].map((field) => (
          <div key={field.key}>
            <label className="text-sm font-medium text-foreground block mb-1">{field.label}</label>
            <p className="text-xs text-muted-foreground mb-2">{field.desc}</p>
            <input
              type="number"
              min={field.min}
              max={field.max}
              value={config[field.key]}
              onChange={(e) => setConfig({ ...config, [field.key]: parseInt(e.target.value) || 0 })}
              className="w-full bg-muted/30 border border-border rounded-lg px-3 py-2 text-sm font-mono text-foreground focus:outline-none focus:border-accent transition-colors"
            />
          </div>
        ))}
        <Button onClick={handleSave} className="bg-accent text-accent-foreground hover:bg-accent/90">
          {saved ? "✓ Saved" : "Save Configuration"}
        </Button>
      </div>
    </motion.div>
  );
}
