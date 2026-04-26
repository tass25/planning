import { useParams, Link } from "react-router-dom";
import { useConversionStore } from "@/store/conversion-store";
import { StatusBadge, RiskBadge } from "@/components/ui/status-badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Download, ArrowLeft, GitCompare, FileText, AlertTriangle, CheckCircle, Code2 } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useEffect, useState, useMemo, useRef } from "react";
import { api, getToken } from "@/lib/api";
import type { Partition } from "@/types";

const stageLabels: Record<string, string> = {
  file_process: "File Processing",
  sas_partition: "SAS Partitioning",
  strategy_select: "Dependency Resolution",
  translate: "LLM Translation",
  validate: "Syntax Validation",
  repair: "CEGAR Repair",
  merge: "Module Assembly",
  finalize: "Finalization",
};

// ── GitHub-style side-by-side diff view ──────────────────────────────────────
// Renders SAS (left, red tint) and Python (right, green tint) line-by-line.
// We pad the shorter side with empty lines so the two columns always have the
// same height and line numbers stay aligned visually.

function DiffView({ sasCode, pythonCode, fileName }: { sasCode: string; pythonCode: string; fileName: string }) {
  const sasLines = sasCode.split("\n");
  const pyLines = pythonCode.split("\n");
  const maxLines = Math.max(sasLines.length, pyLines.length);

  return (
    <div className="border border-border rounded-lg overflow-hidden bg-card">
      {/* Header bar */}
      <div className="grid grid-cols-2 border-b border-border text-xs font-medium">
        <div className="flex items-center gap-2 px-3 py-2 bg-red-500/5 border-r border-border text-red-400">
          <Code2 className="w-3.5 h-3.5" />
          <span>{fileName}</span>
          <span className="ml-auto text-muted-foreground font-mono">{sasLines.length} lines</span>
        </div>
        <div className="flex items-center gap-2 px-3 py-2 bg-green-500/5 text-green-400">
          <Code2 className="w-3.5 h-3.5" />
          <span>{fileName.replace(".sas", ".py")}</span>
          <span className="ml-auto text-muted-foreground font-mono">{pyLines.length} lines</span>
        </div>
      </div>

      {/* Code panes */}
      <div className="grid grid-cols-2 max-h-[600px] overflow-auto">
        {/* SAS side */}
        <div className="border-r border-border font-mono text-xs leading-5">
          {Array.from({ length: maxLines }, (_, i) => {
            const line = sasLines[i] ?? "";
            return (
              <div key={`sas-${i}`} className="flex hover:bg-muted/30 transition-colors group">
                <span className="w-10 flex-shrink-0 text-right pr-2 py-px text-muted-foreground/40 select-none border-r border-border bg-muted/20 group-hover:text-muted-foreground/60">
                  {i < sasLines.length ? i + 1 : ""}
                </span>
                <span className={cn(
                  "flex-1 px-3 py-px whitespace-pre",
                  i < sasLines.length ? "text-foreground/80 bg-red-500/[0.03]" : ""
                )}>
                  {line}
                </span>
              </div>
            );
          })}
        </div>

        {/* Python side */}
        <div className="font-mono text-xs leading-5">
          {Array.from({ length: maxLines }, (_, i) => {
            const line = pyLines[i] ?? "";
            return (
              <div key={`py-${i}`} className="flex hover:bg-muted/30 transition-colors group">
                <span className="w-10 flex-shrink-0 text-right pr-2 py-px text-muted-foreground/40 select-none border-r border-border bg-muted/20 group-hover:text-muted-foreground/60">
                  {i < pyLines.length ? i + 1 : ""}
                </span>
                <span className={cn(
                  "flex-1 px-3 py-px whitespace-pre",
                  i < pyLines.length ? "text-foreground/80 bg-green-500/[0.03]" : ""
                )}>
                  {line}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Workspace Page ───────────────────────────────────────────────────────────

export default function WorkspacePage() {
  const { conversionId } = useParams();
  const conversions = useConversionStore((s) => s.conversions);
  const conversion = conversions.find((c) => c.id === conversionId) || conversions[0];
  const hasBothCodes = !!(conversion?.sasCode && conversion?.pythonCode);
  const [diffMode, setDiffMode] = useState(true);
  const [partitions, setPartitions] = useState<Partition[]>([]);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // correction form state
  const [corrCode, setCorrCode] = useState("");
  const [corrExplanation, setCorrExplanation] = useState("");
  const [corrCategory, setCorrCategory] = useState("");
  const [corrSubmitting, setCorrSubmitting] = useState(false);

  // Load partitions once we have a conversion — failure is silent because
  // the partitions tab is informational and not required for the main flow
  useEffect(() => { if (conversion) api.get<Partition[]>(`/conversions/${conversion.id}/partitions`).then(setPartitions).catch(() => {}); }, [conversion]);

  const showToast = (msg: string, ok: boolean) => {
    setToast({ msg, ok });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 4000);
  };

  // We use raw fetch instead of api.get() here because we need the full
  // Response object to read the Content-Disposition header (for the filename)
  // and to convert the body to a Blob for the anchor download trick
  const downloadFile = async (ext: string) => {
    if (!conversion) return;
    const token = getToken();
    try {
      const res = await fetch(`/api/conversions/${conversion.id}/download/${ext}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) { showToast(`Download failed (${res.status})`, false); return; }
      const blob = await res.blob();
      const cd = res.headers.get("content-disposition");
      const filename = cd?.match(/filename=(.+)/)?.[1] || `download.${ext}`;
      // Programmatic download: create a temporary anchor, click it, then clean up
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
    } catch {
      showToast("Download failed — network error", false);
    }
  };

  const handleSubmitCorrection = async () => {
    if (!conversion || !corrCode.trim()) return;
    setCorrSubmitting(true);
    try {
      await api.post(`/conversions/${conversion.id}/corrections`, {
        correctedCode: corrCode,
        explanation: corrExplanation,
        category: corrCategory || "Syntax Error",
      });
      setCorrCode(""); setCorrExplanation(""); setCorrCategory("");
      showToast("Correction submitted — thank you!", true);
    } catch {
      showToast("Failed to submit correction", false);
    } finally {
      setCorrSubmitting(false);
    }
  };

  if (!conversion) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <p className="text-muted-foreground">No conversion selected</p>
          <Link to="/conversions" className="text-accent text-sm hover:underline mt-2 block">Start a new conversion</Link>
        </div>
      </div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/history" className="p-1.5 rounded-lg hover:bg-muted/50 transition-colors text-muted-foreground">
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <h1 className="text-xl font-bold text-foreground">{conversion.fileName}</h1>
            <div className="flex items-center gap-3 mt-1">
              <StatusBadge status={conversion.status} />
              <span className="text-xs text-muted-foreground font-mono">{conversion.runtime}</span>
              {conversion.accuracy > 0 && <span className="text-xs text-success font-medium">{conversion.accuracy}% accuracy</span>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setDiffMode(!diffMode)} className={cn("border-border text-muted-foreground hover:text-foreground", diffMode && "border-accent text-accent")}>
            <GitCompare className="w-3.5 h-3.5 mr-1.5" />
            {diffMode ? "Diff View" : "Code View"}
          </Button>
          <Button size="sm" className="bg-accent text-accent-foreground hover:bg-accent/90" onClick={() => downloadFile("py")}>
            <Download className="w-3.5 h-3.5 mr-1.5" />
            Download .py
          </Button>
        </div>
      </div>

      {/* Pipeline Progress */}
      <div className="glass-panel p-5">
        <h2 className="text-sm font-semibold text-foreground mb-4">Pipeline Progress</h2>
        <div className="flex items-center gap-1">
          {conversion.stages.map((stage, i) => (
            <div key={stage.stage} className="flex-1 flex flex-col items-center">
              <div className={cn(
                "w-full h-2 rounded-full transition-all duration-500",
                stage.status === "completed" ? "bg-success" :
                stage.status === "running" ? "bg-accent animate-pulse-glow" :
                stage.status === "failed" ? "bg-destructive" : "bg-muted"
              )} />
              <span className="text-[10px] text-muted-foreground mt-2 text-center leading-tight">{stageLabels[stage.stage]}</span>
              {stage.description && <span className="text-[9px] text-muted-foreground/70 text-center leading-tight max-w-[100px] truncate" title={stage.description}>{stage.description}</span>}
              {stage.latency && <span className="text-[10px] text-muted-foreground font-mono">{(stage.latency / 1000).toFixed(1)}s</span>}
              {stage.retryCount > 0 && <span className="text-[10px] text-warning">retry: {stage.retryCount}</span>}
              {stage.warnings.length > 0 && <AlertTriangle className="w-3 h-3 text-warning mt-0.5" />}
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="code" className="space-y-4">
        <TabsList className="bg-muted/50 border border-border">
          <TabsTrigger value="code" className="data-[state=active]:bg-card data-[state=active]:text-foreground">Converted Code</TabsTrigger>
          <TabsTrigger value="validation" className="data-[state=active]:bg-card data-[state=active]:text-foreground">Validation Report</TabsTrigger>
          <TabsTrigger value="merge" className="data-[state=active]:bg-card data-[state=active]:text-foreground">Merge Report</TabsTrigger>
          <TabsTrigger value="partitions" className="data-[state=active]:bg-card data-[state=active]:text-foreground">Partitions</TabsTrigger>
        </TabsList>

        <TabsContent value="code">
          {diffMode && hasBothCodes ? (
            <DiffView sasCode={conversion.sasCode!} pythonCode={conversion.pythonCode!} fileName={conversion.fileName} />
          ) : diffMode && !hasBothCodes ? (
            <div className="glass-panel p-6 text-center text-muted-foreground text-sm">
              Diff view requires both SAS and Python code to be available.
            </div>
          ) : (
            <div className="glass-panel p-4">
              {conversion.pythonCode ? (
                <pre className="text-xs font-mono text-foreground/80 whitespace-pre-wrap overflow-auto max-h-[600px] leading-relaxed">{conversion.pythonCode}</pre>
              ) : conversion.status === "running" || conversion.status === "queued" ? (
                <div className="flex items-center gap-2 py-8 justify-center text-muted-foreground">
                  <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                  <span className="text-sm">Pipeline is running — code will appear when complete...</span>
                </div>
              ) : conversion.status === "failed" ? (
                <div className="flex items-center gap-2 py-8 justify-center text-destructive">
                  <AlertTriangle className="w-4 h-4" />
                  <span className="text-sm">Conversion failed — no output generated</span>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground py-8 text-center">No converted code available</p>
              )}
            </div>
          )}
        </TabsContent>

        <TabsContent value="validation">
          <div className="glass-panel p-5">
            {conversion.validationReport ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-success">
                  <CheckCircle className="w-4 h-4" />
                  <span className="text-sm font-medium">Validation Passed</span>
                </div>
                <pre className="text-xs font-mono text-muted-foreground whitespace-pre-wrap">{conversion.validationReport}</pre>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No validation report available</p>
            )}
          </div>
        </TabsContent>

        <TabsContent value="merge">
          <div className="glass-panel p-5">
            {conversion.mergeReport ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-success">
                  <FileText className="w-4 h-4" />
                  <span className="text-sm font-medium">Merge Complete</span>
                </div>
                <pre className="text-xs font-mono text-muted-foreground whitespace-pre-wrap">{conversion.mergeReport}</pre>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No merge report available</p>
            )}
          </div>
        </TabsContent>

        <TabsContent value="partitions">
          <div className="space-y-3">
            {partitions.map((p) => (
              <div key={p.id} className="glass-panel p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-foreground">Partition {p.id}</span>
                    <RiskBadge level={p.riskLevel} />
                  </div>
                  <span className="text-xs text-muted-foreground font-mono">{p.strategy}</span>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <span className="text-[10px] font-medium text-muted-foreground block mb-1">SAS Block</span>
                    <pre className="text-xs font-mono text-foreground/70 bg-muted/30 rounded p-2 whitespace-pre-wrap">{p.sasBlock}</pre>
                  </div>
                  <div>
                    <span className="text-[10px] font-medium text-muted-foreground block mb-1">Translated</span>
                    <pre className="text-xs font-mono text-foreground/70 bg-muted/30 rounded p-2 whitespace-pre-wrap">{p.translatedCode}</pre>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </TabsContent>
      </Tabs>

      {/* Download Options */}
      <div className="glass-panel p-5">
        <h2 className="text-sm font-semibold text-foreground mb-3">Download Options</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: "Python Files", ext: "py", icon: "🐍" },
            { label: "HTML Report", ext: "html", icon: "📄" },
            { label: "Markdown Report", ext: "md", icon: "📝" },
            { label: "Full Bundle", ext: "zip", icon: "📦" },
          ].map((d) => (
            <button
              key={d.ext}
              onClick={() => downloadFile(d.ext)}
              className="flex items-center gap-2 p-3 rounded-lg border border-border hover:border-accent/50 hover:bg-accent/5 transition-all text-sm text-muted-foreground hover:text-foreground"
            >
              <span>{d.icon}</span>
              <span>{d.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Submit Correction */}
      <div className="glass-panel p-5">
        <h2 className="text-sm font-semibold text-foreground mb-3">Submit Correction</h2>
        <div className="space-y-3">
          <textarea
            value={corrCode}
            onChange={(e) => setCorrCode(e.target.value)}
            placeholder="Corrected code..."
            className="w-full h-24 bg-muted/30 border border-border rounded-lg p-3 text-sm font-mono text-foreground placeholder:text-muted-foreground resize-none focus:outline-none focus:border-accent transition-colors"
          />
          <div className="grid grid-cols-2 gap-3">
            <input
              value={corrExplanation}
              onChange={(e) => setCorrExplanation(e.target.value)}
              placeholder="Explanation..."
              className="bg-muted/30 border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-accent transition-colors"
            />
            <select
              value={corrCategory}
              onChange={(e) => setCorrCategory(e.target.value)}
              className="bg-muted/30 border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent transition-colors"
            >
              <option value="">Category...</option>
              <option>Syntax Error</option>
              <option>Logic Error</option>
              <option>Missing Function</option>
              <option>Data Type Issue</option>
            </select>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="border-border text-muted-foreground hover:text-foreground"
            onClick={handleSubmitCorrection}
            disabled={corrSubmitting || !corrCode.trim()}
          >
            {corrSubmitting ? "Submitting…" : "Submit Correction"}
          </Button>
        </div>
      </div>

      {/* Toast notification */}
      {toast && (
        <div className={`fixed bottom-6 right-6 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium transition-all ${toast.ok ? "bg-green-600 text-white" : "bg-red-600 text-white"}`}>
          {toast.msg}
        </div>
      )}
    </motion.div>
  );
}
