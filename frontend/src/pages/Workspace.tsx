import { useParams, Link, useNavigate } from "react-router-dom";
import { useConversionStore } from "@/store/conversion-store";
import { StatusBadge, RiskBadge } from "@/components/ui/status-badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Download, ArrowLeft, GitCompare, FileText, AlertTriangle, CheckCircle, Code2, Copy, Check, Award, BarChart3, Shield, Zap, ChevronLeft, ChevronRight } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useEffect, useState, useMemo, useRef } from "react";
import { usePageTitle } from "@/lib/hooks";
import { api, getToken } from "@/lib/api";
import Editor from "@monaco-editor/react";
import { useThemeStore } from "@/store/theme-store";
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
  return (
    <div className="border border-border rounded-lg overflow-hidden bg-card">
      {/* Header bar */}
      <div className="grid grid-cols-2 border-b border-border text-xs font-medium">
        <div className="flex items-center gap-2 px-3 py-2 bg-red-500/5 border-r border-border text-red-400 min-w-0">
          <Code2 className="w-3.5 h-3.5 flex-shrink-0" />
          <span className="truncate">{fileName}</span>
        </div>
        <div className="flex items-center gap-2 px-3 py-2 bg-green-500/5 text-green-400 min-w-0">
          <Code2 className="w-3.5 h-3.5 flex-shrink-0" />
          <span className="truncate">{fileName.replace(".sas", ".py")}</span>
        </div>
      </div>

      {/* Code panes — grid locks 50/50, text wraps within each side */}
      <div className="grid grid-cols-2 max-h-[600px]">
        <div className="overflow-y-auto border-r border-border min-w-0 bg-red-500/[0.02]">
          <pre className="text-xs font-mono text-foreground/80 whitespace-pre-wrap break-words p-3 leading-relaxed">{sasCode}</pre>
        </div>
        <div className="overflow-y-auto min-w-0 bg-green-500/[0.02]">
          <pre className="text-xs font-mono text-foreground/80 whitespace-pre-wrap break-words p-3 leading-relaxed">{pythonCode}</pre>
        </div>
      </div>
    </div>
  );
}

// ── Workspace Page ───────────────────────────────────────────────────────────

export default function WorkspacePage() {
  const { conversionId } = useParams();
  const navigate = useNavigate();
  const conversions = useConversionStore((s) => s.conversions);
  const conversion = conversions.find((c) => c.id === conversionId) || conversions[0];
  usePageTitle(conversion?.fileName ? `Workspace: ${conversion.fileName}` : "Workspace");
  const scrollRef = useRef<HTMLDivElement>(null);
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
  const [copied, setCopied] = useState(false);
  const isDark = useThemeStore((s) => s.theme === "dark");

  const copyToClipboard = async () => {
    if (!conversion?.pythonCode) return;
    await navigator.clipboard.writeText(conversion.pythonCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

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
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6 overflow-hidden">
      {/* File Selector — shown when multiple conversions exist */}
      {conversions.length > 1 && (
        <div className="relative">
          <div className="flex items-center gap-1">
            <button
              onClick={() => scrollRef.current?.scrollBy({ left: -200, behavior: "smooth" })}
              className="p-1 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <div ref={scrollRef} className="flex-1 flex items-center gap-1 overflow-x-auto scrollbar-hide py-1">
              {conversions.map((c) => (
                <button
                  key={c.id}
                  onClick={() => navigate(`/workspace/${c.id}`)}
                  className={cn(
                    "flex items-center gap-2 px-3 py-2 rounded-lg text-sm whitespace-nowrap transition-all flex-shrink-0 border",
                    c.id === conversion?.id
                      ? "bg-accent/10 border-accent/40 text-accent font-medium"
                      : "bg-card border-border text-muted-foreground hover:text-foreground hover:border-accent/20"
                  )}
                >
                  <Code2 className="w-3.5 h-3.5" />
                  <span>{c.fileName}</span>
                  <StatusBadge status={c.status} />
                </button>
              ))}
            </div>
            <button
              onClick={() => scrollRef.current?.scrollBy({ left: 200, behavior: "smooth" })}
              className="p-1 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

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
          <Button variant="outline" size="sm" onClick={copyToClipboard} className="border-border text-muted-foreground hover:text-foreground">
            {copied ? <Check className="w-3.5 h-3.5 mr-1.5 text-success" /> : <Copy className="w-3.5 h-3.5 mr-1.5" />}
            {copied ? "Copied!" : "Copy Code"}
          </Button>
          <Button size="sm" className="bg-accent text-accent-foreground hover:bg-accent/90" onClick={() => downloadFile("py")}>
            <Download className="w-3.5 h-3.5 mr-1.5" />
            Download .py
          </Button>
        </div>
      </div>

      {/* Pipeline Visualization */}
      <div className="glass-panel p-5">
        <h2 className="text-sm font-semibold text-foreground mb-5">Pipeline</h2>
        <div className="flex items-start gap-0 overflow-x-auto pb-2">
          {conversion.stages.map((stage, i) => {
            const isCompleted = stage.status === "completed";
            const isRunning = stage.status === "running";
            const isFailed = stage.status === "failed";
            const nodeColor = isCompleted ? "border-success bg-success/10 text-success" :
              isRunning ? "border-accent bg-accent/10 text-accent" :
              isFailed ? "border-destructive bg-destructive/10 text-destructive" :
              "border-border bg-muted/30 text-muted-foreground";
            const lineColor = isCompleted ? "bg-success" : "bg-border";

            return (
              <div key={stage.stage} className="flex items-start flex-shrink-0" style={{ minWidth: i < conversion.stages.length - 1 ? 140 : 100 }}>
                <div className="flex flex-col items-center">
                  <motion.div
                    initial={false}
                    animate={isRunning ? { scale: [1, 1.1, 1] } : { scale: 1 }}
                    transition={isRunning ? { repeat: Infinity, duration: 1.5 } : {}}
                    className={cn("w-10 h-10 rounded-xl border-2 flex items-center justify-center transition-all duration-500", nodeColor)}
                  >
                    {isCompleted ? <CheckCircle className="w-4 h-4" /> :
                     isRunning ? <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" /> :
                     isFailed ? <AlertTriangle className="w-4 h-4" /> :
                     <span className="text-[10px] font-bold">{i + 1}</span>}
                  </motion.div>
                  <span className="text-[10px] font-medium mt-2 text-center leading-tight max-w-[90px]">
                    {stageLabels[stage.stage] || stage.stage}
                  </span>
                  {stage.latency ? (
                    <span className="text-[9px] text-muted-foreground font-mono mt-0.5">{(stage.latency / 1000).toFixed(1)}s</span>
                  ) : null}
                  {stage.retryCount > 0 && <span className="text-[9px] text-warning mt-0.5">retry {stage.retryCount}</span>}
                </div>
                {i < conversion.stages.length - 1 && (
                  <div className="flex items-center h-10 flex-1 px-1">
                    <div className={cn("h-0.5 w-full rounded-full transition-all duration-500", lineColor)} />
                    <div className={cn("w-0 h-0 border-t-[4px] border-t-transparent border-b-[4px] border-b-transparent border-l-[6px] transition-all duration-500", isCompleted ? "border-l-success" : "border-l-border")} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="code" className="space-y-4">
        <TabsList className="bg-muted/50 border border-border">
          <TabsTrigger value="code" className="data-[state=active]:bg-card data-[state=active]:text-foreground">Converted Code</TabsTrigger>
          <TabsTrigger value="report-card" className="data-[state=active]:bg-card data-[state=active]:text-foreground">Report Card</TabsTrigger>
          <TabsTrigger value="validation" className="data-[state=active]:bg-card data-[state=active]:text-foreground">Validation</TabsTrigger>
          <TabsTrigger value="merge" className="data-[state=active]:bg-card data-[state=active]:text-foreground">Merge</TabsTrigger>
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

        <TabsContent value="report-card">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <div className="glass-panel p-3 flex items-center gap-3">
              <Award className="w-5 h-5 text-accent flex-shrink-0" />
              <div>
                <p className="text-lg font-bold text-foreground leading-tight">{conversion.accuracy > 0 ? `${conversion.accuracy}%` : "—"}</p>
                <p className="text-[10px] text-muted-foreground">Accuracy</p>
              </div>
            </div>
            <div className="glass-panel p-3 flex items-center gap-3">
              <BarChart3 className="w-5 h-5 text-secondary flex-shrink-0" />
              <div>
                <p className="text-lg font-bold text-foreground leading-tight">{partitions.length || "—"}</p>
                <p className="text-[10px] text-muted-foreground">Partitions</p>
              </div>
            </div>
            <div className="glass-panel p-3 flex items-center gap-3">
              <Zap className="w-5 h-5 text-warning flex-shrink-0" />
              <div>
                <p className="text-lg font-bold text-foreground leading-tight">{conversion.duration > 0 ? `${conversion.duration}s` : "—"}</p>
                <p className="text-[10px] text-muted-foreground">Duration</p>
              </div>
            </div>
            <div className="glass-panel p-3 flex items-center gap-3">
              <Shield className="w-5 h-5 text-success flex-shrink-0" />
              <div>
                <p className="text-lg font-bold text-foreground leading-tight">{conversion.stages.filter((s) => s.status === "completed").length}/{conversion.stages.length}</p>
                <p className="text-[10px] text-muted-foreground">Stages</p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="glass-panel p-4">
              <h3 className="text-xs font-semibold text-foreground mb-2">Risk Distribution</h3>
              {partitions.length > 0 ? (
                <div className="space-y-1.5">
                  {["LOW", "MODERATE", "HIGH", "UNCERTAIN"].map((level) => {
                    const count = partitions.filter((p) => p.riskLevel === level).length;
                    const pct = (count / partitions.length) * 100;
                    if (count === 0) return null;
                    const colors: Record<string, string> = { LOW: "bg-success", MODERATE: "bg-warning", HIGH: "bg-destructive", UNCERTAIN: "bg-muted-foreground" };
                    return (
                      <div key={level} className="flex items-center gap-2">
                        <span className="text-[10px] text-muted-foreground w-20">{level}</span>
                        <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                          <div className={cn("h-full rounded-full", colors[level])} style={{ width: `${pct}%` }} />
                        </div>
                        <span className="text-[10px] font-mono text-muted-foreground w-6 text-right">{count}</span>
                      </div>
                    );
                  })}
                </div>
              ) : <p className="text-[10px] text-muted-foreground">No partition data available</p>}
            </div>

            <div className="glass-panel p-4">
              <h3 className="text-xs font-semibold text-foreground mb-2">Pipeline Performance</h3>
              <div className="space-y-1.5">
                {conversion.stages.filter((s) => s.latency).map((s) => (
                  <div key={s.stage} className="flex items-center gap-2">
                    <span className="text-[10px] text-muted-foreground w-28 truncate">{stageLabels[s.stage] || s.stage}</span>
                    <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                      <div className="h-full rounded-full bg-accent" style={{ width: `${Math.min(100, ((s.latency || 0) / Math.max(...conversion.stages.map((st) => st.latency || 1))) * 100)}%` }} />
                    </div>
                    <span className="text-[10px] font-mono text-muted-foreground w-10 text-right">{((s.latency || 0) / 1000).toFixed(1)}s</span>
                  </div>
                ))}
                {conversion.stages.filter((s) => s.latency).length === 0 && (
                  <p className="text-[10px] text-muted-foreground">No latency data yet</p>
                )}
              </div>
            </div>

            <div className="glass-panel p-4 md:col-span-2">
              <h3 className="text-xs font-semibold text-foreground mb-2">Summary</h3>
              <div className="grid grid-cols-4 gap-3 text-center">
                <div>
                  <p className="text-sm font-bold text-foreground">{conversion.sasCode?.split("\n").length || 0}</p>
                  <p className="text-[10px] text-muted-foreground">SAS Lines</p>
                </div>
                <div>
                  <p className="text-sm font-bold text-foreground">{conversion.pythonCode?.split("\n").length || 0}</p>
                  <p className="text-[10px] text-muted-foreground">Python Lines</p>
                </div>
                <div>
                  <p className="text-sm font-bold text-foreground">{conversion.stages.reduce((a, s) => a + s.retryCount, 0)}</p>
                  <p className="text-[10px] text-muted-foreground">Retries</p>
                </div>
                <div>
                  <p className="text-sm font-bold text-foreground">{conversion.stages.reduce((a, s) => a + s.warnings.length, 0)}</p>
                  <p className="text-[10px] text-muted-foreground">Warnings</p>
                </div>
              </div>
            </div>
          </div>
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
          <div className="border border-border rounded-lg overflow-hidden">
            <Editor
              height="200px"
              defaultLanguage="python"
              value={corrCode}
              onChange={(v) => setCorrCode(v || "")}
              theme={isDark ? "vs-dark" : "light"}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                lineNumbers: "on",
                scrollBeyondLastLine: false,
                wordWrap: "on",
                padding: { top: 8 },
                renderLineHighlight: "gutter",
                overviewRulerLanes: 0,
                hideCursorInOverviewRuler: true,
                scrollbar: { verticalScrollbarSize: 6 },
              }}
            />
          </div>
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
