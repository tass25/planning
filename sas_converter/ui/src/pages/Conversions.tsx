import { useState, useCallback } from "react";
import { useConversionStore } from "@/store/conversion-store";
import { StatusBadge } from "@/components/ui/status-badge";
import { Upload, FileCode, X, Play, Settings2, CheckCircle2, Loader2, Circle, AlertCircle, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { Link } from "react-router-dom";
import type { RiskLevel, PipelineStage } from "@/types";

const STAGE_LABELS: Record<PipelineStage, string> = {
  file_process: "File Analysis",
  sas_partition: "Code Chunking",
  strategy_select: "Dependency Resolution",
  translate: "Data Lineage",
  validate: "Validation",
  repair: "Auto-Repair",
  merge: "Merge Output",
  finalize: "Finalization",
};

const STAGE_DEFAULTS: Record<PipelineStage, string> = {
  file_process: "Waiting to scan SAS files...",
  sas_partition: "Waiting to chunk code...",
  strategy_select: "Waiting to resolve dependencies...",
  translate: "Waiting to trace data lineage...",
  validate: "Waiting to validate output...",
  repair: "Waiting to check for issues...",
  merge: "Waiting to merge partitions...",
  finalize: "Waiting to package results...",
};

export default function ConversionsPage() {
  const { uploadedFiles, removeFile, config, setConfig, startConversion, uploadFiles, conversions, activeConversionId } = useConversionStore();
  const [isDragging, setIsDragging] = useState(false);
  const [isRunning, setIsRunning] = useState(false);

  const activeConversion = conversions.find((c) => c.id === activeConversionId);
  const showProgress = isRunning || (activeConversion && (activeConversion.status === "running" || activeConversion.status === "queued"));

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files).filter((f) => f.name.endsWith(".sas"));
    if (files.length > 0) await uploadFiles(files);
  }, [uploadFiles]);

  const handleFileInput = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) await uploadFiles(files);
  };

  const handleStart = async () => {
    if (uploadedFiles.length === 0) return;
    setIsRunning(true);
    await startConversion(uploadedFiles.map((f) => f.id));
  };

  // Compute progress
  const stages = activeConversion?.stages ?? [];
  const completedCount = stages.filter((s) => s.status === "completed").length;
  const totalStages = stages.length || 8;
  const progress = Math.round((completedCount / totalStages) * 100);
  const isComplete = activeConversion?.status === "completed";
  const isFailed = activeConversion?.status === "failed";

  if (isComplete || isFailed) {
    if (isRunning) setIsRunning(false);
  }

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

      {/* ── Progress Tracker ─────────────────────────────────── */}
      <AnimatePresence>
        {showProgress && activeConversion && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="glass-panel p-6 space-y-5"
          >
            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-foreground">
                  {isComplete ? "Conversion Complete" : isFailed ? "Conversion Failed" : "Converting..."}
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">{activeConversion.fileName}</p>
              </div>
              <div className={cn(
                "text-3xl font-black tabular-nums",
                isComplete ? "text-success" : isFailed ? "text-destructive" : "text-accent"
              )}>
                {progress}%
              </div>
            </div>

            {/* Progress Bar */}
            <div className="relative h-3 bg-muted/30 rounded-full overflow-hidden">
              <motion.div
                className={cn(
                  "absolute inset-y-0 left-0 rounded-full",
                  isComplete ? "bg-success" : isFailed ? "bg-destructive" : "bg-gradient-to-r from-accent to-secondary"
                )}
                initial={{ width: "0%" }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.5, ease: "easeOut" }}
              />
              {!isComplete && !isFailed && (
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-pulse" />
              )}
            </div>

            {/* Stage List */}
            <div className="space-y-1">
              {stages.map((stage, i) => {
                const label = STAGE_LABELS[stage.stage] || stage.stage;
                const desc = stage.description || STAGE_DEFAULTS[stage.stage] || "";
                const stageProgress = Math.round(((i + 1) / totalStages) * 100);

                return (
                  <motion.div
                    key={stage.stage}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05 }}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-300",
                      stage.status === "running" && "bg-accent/5 border border-accent/20",
                      stage.status === "completed" && "opacity-80",
                      stage.status === "pending" && "opacity-40",
                    )}
                  >
                    {/* Icon */}
                    <div className="flex-shrink-0">
                      {stage.status === "completed" && <CheckCircle2 className="w-4 h-4 text-success" />}
                      {stage.status === "running" && <Loader2 className="w-4 h-4 text-accent animate-spin" />}
                      {stage.status === "failed" && <AlertCircle className="w-4 h-4 text-destructive" />}
                      {stage.status === "pending" && <Circle className="w-4 h-4 text-muted-foreground/30" />}
                    </div>

                    {/* Label + description */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={cn(
                          "text-sm font-medium",
                          stage.status === "running" ? "text-accent" : stage.status === "completed" ? "text-foreground" : "text-muted-foreground"
                        )}>
                          {label}
                        </span>
                        <span className="text-[10px] font-mono text-muted-foreground/50">{stageProgress}%</span>
                      </div>
                      <p className={cn(
                        "text-xs truncate",
                        stage.status === "running" ? "text-accent/70" : "text-muted-foreground/60"
                      )}>
                        {desc}
                      </p>
                    </div>

                    {/* Latency */}
                    {stage.status === "completed" && stage.latency != null && (
                      <span className="text-[10px] font-mono text-muted-foreground/50 flex-shrink-0">
                        {stage.latency > 1000 ? `${(stage.latency / 1000).toFixed(1)}s` : `${stage.latency.toFixed(0)}ms`}
                      </span>
                    )}
                  </motion.div>
                );
              })}
            </div>

            {/* Completed actions */}
            {isComplete && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-3 pt-2">
                <Link to={`/workspace/${activeConversion.id}`}>
                  <Button size="sm" className="bg-accent text-accent-foreground hover:bg-accent/90">
                    View in Workspace <ArrowRight className="w-3 h-3 ml-1" />
                  </Button>
                </Link>
                <Button size="sm" variant="outline" onClick={() => { useConversionStore.getState().setActiveConversion(null); setIsRunning(false); }}>
                  New Conversion
                </Button>
              </motion.div>
            )}
            {isFailed && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="pt-2">
                <Button size="sm" variant="outline" onClick={() => { useConversionStore.getState().setActiveConversion(null); setIsRunning(false); }}>
                  Try Again
                </Button>
              </motion.div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Upload Zone (hidden during progress) ─────────────── */}
      {!showProgress && (
        <>
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
                      {t === "full" ? "Full" : "Structural"}
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
        </>
      )}
    </motion.div>
  );
}
