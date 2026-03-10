import { useParams, Link } from "react-router-dom";
import { useConversionStore } from "@/store/conversion-store";
import { StatusBadge, RiskBadge } from "@/components/ui/status-badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Download, ArrowLeft, GitCompare, FileText, AlertTriangle, CheckCircle } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { mockPartitions } from "@/lib/mock/data";
import { useState } from "react";

const stageLabels: Record<string, string> = {
  file_process: "File Processing",
  sas_partition: "SAS Partitioning",
  strategy_select: "Strategy Selection",
  translate: "Translation",
  validate: "Validation",
  repair: "Repair",
  merge: "Merge",
  finalize: "Finalization",
};

export default function WorkspacePage() {
  const { conversionId } = useParams();
  const conversions = useConversionStore((s) => s.conversions);
  const conversion = conversions.find((c) => c.id === conversionId) || conversions[0];
  const [diffMode, setDiffMode] = useState(false);

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
          <Button variant="outline" size="sm" onClick={() => setDiffMode(!diffMode)} className="border-border text-muted-foreground hover:text-foreground">
            <GitCompare className="w-3.5 h-3.5 mr-1.5" />
            {diffMode ? "Code View" : "Diff View"}
          </Button>
          <Button size="sm" className="bg-accent text-accent-foreground hover:bg-accent/90">
            <Download className="w-3.5 h-3.5 mr-1.5" />
            Download
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
          {diffMode ? (
            <div className="grid grid-cols-2 gap-4">
              <div className="glass-panel p-4">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xs font-medium text-destructive bg-destructive/10 px-2 py-0.5 rounded">SAS (Original)</span>
                </div>
                <pre className="text-xs font-mono text-foreground/80 whitespace-pre-wrap overflow-auto max-h-[500px] leading-relaxed">{conversion.sasCode || "No source code available"}</pre>
              </div>
              <div className="glass-panel p-4">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xs font-medium text-success bg-success/10 px-2 py-0.5 rounded">Python (Converted)</span>
                </div>
                <pre className="text-xs font-mono text-foreground/80 whitespace-pre-wrap overflow-auto max-h-[500px] leading-relaxed">{conversion.pythonCode || "No converted code available"}</pre>
              </div>
            </div>
          ) : (
            <div className="glass-panel p-4">
              <pre className="text-xs font-mono text-foreground/80 whitespace-pre-wrap overflow-auto max-h-[600px] leading-relaxed">{conversion.pythonCode || "Conversion in progress..."}</pre>
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
            {mockPartitions.map((p) => (
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
            { label: "Python Files", ext: ".py", icon: "🐍" },
            { label: "HTML Report", ext: ".html", icon: "📄" },
            { label: "Markdown Report", ext: ".md", icon: "📝" },
            { label: "Full Bundle", ext: ".zip", icon: "📦" },
          ].map((d) => (
            <button key={d.ext} className="flex items-center gap-2 p-3 rounded-lg border border-border hover:border-accent/50 hover:bg-accent/5 transition-all text-sm text-muted-foreground hover:text-foreground">
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
          <textarea placeholder="Corrected code..." className="w-full h-24 bg-muted/30 border border-border rounded-lg p-3 text-sm font-mono text-foreground placeholder:text-muted-foreground resize-none focus:outline-none focus:border-accent transition-colors" />
          <div className="grid grid-cols-2 gap-3">
            <input placeholder="Explanation..." className="bg-muted/30 border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-accent transition-colors" />
            <select className="bg-muted/30 border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent transition-colors">
              <option value="">Category...</option>
              <option>Syntax Error</option>
              <option>Logic Error</option>
              <option>Missing Function</option>
              <option>Data Type Issue</option>
            </select>
          </div>
          <Button variant="outline" size="sm" className="border-border text-muted-foreground hover:text-foreground">Submit Correction</Button>
        </div>
      </div>
    </motion.div>
  );
}
