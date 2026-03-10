import { StatusBadge } from "@/components/ui/status-badge";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { FileRegistryEntry } from "@/types";

export default function FileRegistryPage() {
  const [fileRegistry, setFileRegistry] = useState<FileRegistryEntry[]>([]);
  useEffect(() => { api.get<FileRegistryEntry[]>("/admin/file-registry").then(setFileRegistry).catch(() => {}); }, []);

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">File Registry</h1>
        <p className="text-sm text-muted-foreground mt-1">File dependencies and lineage tracking</p>
      </div>

      <div className="space-y-3">
        {fileRegistry.map((file) => (
          <div key={file.id} className="glass-panel p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-medium text-foreground font-mono">{file.fileName}</span>
              <StatusBadge status={file.status} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <span className="text-[10px] font-medium text-muted-foreground block mb-1">Dependencies</span>
                {file.dependencies.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {file.dependencies.map((d) => (
                      <span key={d} className="text-xs bg-muted/50 text-muted-foreground px-2 py-0.5 rounded font-mono">{d}</span>
                    ))}
                  </div>
                ) : <span className="text-xs text-muted-foreground">None</span>}
              </div>
              <div>
                <span className="text-[10px] font-medium text-muted-foreground block mb-1">Lineage</span>
                {file.lineage.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {file.lineage.map((l) => (
                      <span key={l} className="text-xs bg-accent/10 text-accent px-2 py-0.5 rounded font-mono">{l}</span>
                    ))}
                  </div>
                ) : <span className="text-xs text-muted-foreground">None</span>}
              </div>
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
