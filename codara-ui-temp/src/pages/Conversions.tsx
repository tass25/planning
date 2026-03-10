import { useState, useCallback } from "react";
import { useConversionStore } from "@/store/conversion-store";
import { StatusBadge } from "@/components/ui/status-badge";
import { Upload, FileCode, X, Play, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import type { SasFile, RiskLevel } from "@/types";

export default function ConversionsPage() {
  const { uploadedFiles, addFiles, removeFile, config, setConfig, startConversion } = useConversionStore();
  const [isDragging, setIsDragging] = useState(false);
  const [isRunning, setIsRunning] = useState(false);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files).filter((f) => f.name.endsWith(".sas"));
    const sasFiles: SasFile[] = files.map((f) => ({
      id: `file-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      name: f.name,
      size: f.size,
      modules: ["DATA Step", "PROC SQL", "Macro"].slice(0, Math.floor(Math.random() * 3) + 1),
      estimatedComplexity: (["low", "medium", "high"] as RiskLevel[])[Math.floor(Math.random() * 3)],
      uploadedAt: new Date().toISOString(),
    }));
    addFiles(sasFiles);
  }, [addFiles]);

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const sasFiles: SasFile[] = files.map((f) => ({
      id: `file-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      name: f.name,
      size: f.size,
      modules: ["DATA Step", "PROC SQL"].slice(0, Math.floor(Math.random() * 2) + 1),
      estimatedComplexity: (["low", "medium", "high"] as RiskLevel[])[Math.floor(Math.random() * 3)],
      uploadedAt: new Date().toISOString(),
    }));
    addFiles(sasFiles);
  };

  const handleStart = () => {
    if (uploadedFiles.length === 0) return;
    setIsRunning(true);
    startConversion(uploadedFiles.map((f) => f.id));
    setTimeout(() => setIsRunning(false), 1500);
  };

  const complexityColors: Record<RiskLevel, string> = {
    low: "text-success",
    medium: "text-warning",
    high: "text-destructive",
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">New Conversion</h1>
        <p className="text-sm text-muted-foreground mt-1">Upload SAS files and configure your conversion pipeline</p>
      </div>

      {/* Upload Zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={cn(
          "glass-panel border-2 border-dashed p-10 text-center transition-all duration-300 cursor-pointer",
          isDragging ? "border-accent bg-accent/5 glow-accent" : "border-border hover:border-muted-foreground"
        )}
      >
        <input type="file" accept=".sas" multiple onChange={handleFileInput} className="hidden" id="file-upload" />
        <label htmlFor="file-upload" className="cursor-pointer">
          <Upload className={cn("w-10 h-10 mx-auto mb-3 transition-colors", isDragging ? "text-accent" : "text-muted-foreground")} />
          <p className="text-sm font-medium text-foreground">Drop .sas files here or click to browse</p>
          <p className="text-xs text-muted-foreground mt-1">Supports multiple files • Max 100MB per file</p>
        </label>
      </div>

      {/* Uploaded Files */}
      <AnimatePresence>
        {uploadedFiles.length > 0 && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="glass-panel divide-y divide-border overflow-hidden">
            {uploadedFiles.map((file) => (
              <div key={file.id} className="flex items-center justify-between px-4 py-3">
                <div className="flex items-center gap-3">
                  <FileCode className="w-4 h-4 text-accent" />
                  <div>
                    <p className="text-sm font-medium text-foreground">{file.name}</p>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(1)} KB</span>
                      <span className="text-xs text-muted-foreground">{file.modules.join(", ")}</span>
                      <span className={cn("text-xs font-medium capitalize", complexityColors[file.estimatedComplexity])}>{file.estimatedComplexity} complexity</span>
                    </div>
                  </div>
                </div>
                <button onClick={() => removeFile(file.id)} className="p-1 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors">
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Config */}
      <div className="glass-panel p-5">
        <div className="flex items-center gap-2 mb-4">
          <Settings2 className="w-4 h-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold text-foreground">Configuration</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-2">Target Runtime</label>
            <div className="flex gap-2">
              {(["python", "pyspark"] as const).map((r) => (
                <button key={r} onClick={() => setConfig({ targetRuntime: r })} className={cn(
                  "flex-1 py-2 px-3 rounded-lg text-sm font-medium border transition-all",
                  config.targetRuntime === r ? "border-accent bg-accent/10 text-accent" : "border-border text-muted-foreground hover:border-muted-foreground"
                )}>
                  {r === "python" ? "Python" : "PySpark"}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-2">Test Coverage</label>
            <div className="flex gap-2">
              {(["full", "structural_only"] as const).map((t) => (
                <button key={t} onClick={() => setConfig({ testCoverage: t })} className={cn(
                  "flex-1 py-2 px-3 rounded-lg text-sm font-medium border transition-all",
                  config.testCoverage === t ? "border-accent bg-accent/10 text-accent" : "border-border text-muted-foreground hover:border-muted-foreground"
                )}>
                  {t === "full" ? "Full" : "Structural Only"}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Start Button */}
      <Button onClick={handleStart} disabled={uploadedFiles.length === 0 || isRunning} className="w-full py-6 text-base font-semibold bg-gradient-to-r from-accent to-secondary text-accent-foreground hover:opacity-90 transition-opacity glow-accent">
        <Play className="w-4 h-4 mr-2" />
        {isRunning ? "Starting Pipeline..." : "Start Conversion"}
      </Button>
    </motion.div>
  );
}
