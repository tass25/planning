import { useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { usePageTitle } from "@/lib/hooks";
import { CodaraLogo } from "@/components/CodaraLogo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { ArrowLeft, ArrowRight, X, Database, Cpu, Shield, Cloud, GitBranch, Layers } from "lucide-react";
import { cn } from "@/lib/utils";

// ── Architecture data extracted from the report SVG ────────────────────────

const PIPELINE_NODES = [
  { id: 1, name: "file_process", label: "File Processing", sub: ["File Analysis", "Cross-file Registry"], color: "purple" },
  { id: 2, name: "streaming", label: "Streaming Parser", sub: ["FSM Tokenizer", "Async Queue"], color: "purple" },
  { id: 3, name: "chunking", label: "Chunking", sub: ["Boundary Detector", "Partition Builder"], color: "purple" },
  { id: 4, name: "raptor", label: "RAPTOR", sub: ["GMM Clustering", "Hierarchical Tree"], color: "purple" },
  { id: 5, name: "risk_routing", label: "Risk Routing", sub: ["14-feature ML Classifier", "Strategy Assignment"], color: "purple" },
  { id: 6, name: "persist_index", label: "Persist & Index", sub: ["NetworkX DAG", "SCC Detection"], color: "purple" },
  { id: 7, name: "translation", label: "Translation", sub: ["3-Tier RAG Context", "Code Generation"], color: "purple" },
  { id: 8, name: "merge", label: "Merge", sub: ["Import Consolidation", "HTML Report Gen"], color: "purple" },
];

const DATA_STORES = [
  { name: "SQLite", desc: "API database — users, conversions, stages", icon: "db", color: "emerald" },
  { name: "Redis", desc: "Pipeline state checkpoints (every 50 blocks)", icon: "cache", color: "emerald" },
  { name: "LanceDB", desc: "Vector KB — 768-dim Nomic embeddings, 330+ pairs", icon: "vector", color: "emerald" },
  { name: "DuckDB", desc: "OLAP audit logs — LLM calls, analytics", icon: "analytics", color: "emerald" },
];

const AI_PROVIDERS = [
  { name: "Ollama", desc: "Primary — minimax-m2.7:cloud", role: "primary" },
  { name: "Azure OpenAI", desc: "Fallback 1 — GPT-5.4-mini", role: "fallback" },
  { name: "Groq", desc: "Fallback 2 + Cross-verifier — LLaMA-3.3-70b", role: "fallback" },
  { name: "Nomic Embed", desc: "768-dim embeddings for RAG", role: "embedder" },
];

const VERIFICATION = [
  { name: "Z3 Solver", desc: "SMT formal proofs — 4 pattern encoders" },
  { name: "CDAIS", desc: "Constraint-driven AI synthesis testing" },
  { name: "Sandbox Exec", desc: "Multiprocessing isolation — exec() in sandbox" },
  { name: "Cross-Verify", desc: "Independent LLM second opinion (Groq)" },
];

const AZURE_SERVICES = [
  { name: "Key Vault", desc: "Secret management" },
  { name: "Managed Identity", desc: "RBAC authentication" },
  { name: "App Insights", desc: "OpenTelemetry traces" },
  { name: "Container Apps", desc: "Docker deployment" },
];

const EDGE_LABELS = [
  "FileMeta[], deps",
  "Token stream",
  "PartitionIR[]",
  "RAPTOR Tree",
  "risk_level, strategy",
  "SQLite + DAG Persisted",
  "ConversionResult[]",
  "Final .py + HTML Report",
];

type Section = "pipeline" | "data" | "ai" | "verification" | "azure" | null;

const SECTION_INFO: Record<string, { icon: typeof Layers; title: string; desc: string }> = {
  pipeline: { icon: Layers, title: "8-Node LangGraph Pipeline", desc: "State Machine - Asynchronous - Checkpointed. Each node is a composite agent (facade pattern) delegating to 1-4 specialist sub-agents." },
  data: { icon: Database, title: "Data Layer", desc: "Four specialized stores: SQLite for ACID writes, Redis for state checkpoints, LanceDB for vector search, DuckDB for OLAP analytics." },
  ai: { icon: Cpu, title: "AI & Embeddings", desc: "3-tier LLM fallback chain with circuit breakers and rate limiters. Nomic embeddings for RAG retrieval." },
  verification: { icon: Shield, title: "Verification Layer", desc: "Formal verification with Z3 SMT solver, sandboxed execution, and independent cross-verification." },
  azure: { icon: Cloud, title: "Azure Managed Services", desc: "Cloud-native deployment with managed identity, secret management, and observability." },
};

export default function ArchitecturePage() {
  usePageTitle("Architecture");
  const [activeSection, setActiveSection] = useState<Section>(null);
  const [hoveredNode, setHoveredNode] = useState<number | null>(null);

  return (
    <div className="min-h-screen bg-background">
      {/* Nav */}
      <nav className="border-b border-border/50 backdrop-blur-xl sticky top-0 z-50 bg-background/80">
        <div className="max-w-7xl mx-auto flex items-center justify-between px-6 h-16">
          <div className="flex items-center gap-4">
            <Link to="/"><CodaraLogo size="md" /></Link>
            <span className="text-[10px] font-semibold uppercase tracking-widest text-secondary bg-secondary/10 px-2 py-1 rounded">Architecture</span>
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Link to="/signup">
              <Button size="sm" className="bg-accent text-accent-foreground hover:bg-accent/90 gap-1.5">
                Sign Up <ArrowRight className="w-3.5 h-3.5" />
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
          <Link to="/" className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 mb-4">
            <ArrowLeft className="w-3 h-3" /> Back to Home
          </Link>
          <h1 className="text-3xl font-bold text-foreground">System Architecture</h1>
          <p className="text-sm text-muted-foreground mt-2 max-w-2xl">
            Codara's three-tier stack: React frontend, FastAPI backend, and an 8-node LangGraph pipeline with 3-tier RAG, Z3 formal verification, and multi-provider LLM fallback.
          </p>
        </motion.div>

        {/* Section selector */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="flex flex-wrap gap-2">
          {(["pipeline", "data", "ai", "verification", "azure"] as Section[]).map((s) => {
            if (!s) return null;
            const info = SECTION_INFO[s];
            return (
              <button
                key={s}
                onClick={() => setActiveSection(activeSection === s ? null : s)}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium border transition-all",
                  activeSection === s
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-border text-muted-foreground hover:text-foreground hover:border-muted-foreground"
                )}
              >
                <info.icon className="w-3.5 h-3.5" />
                {info.title.split(" ").slice(0, 2).join(" ")}
              </button>
            );
          })}
        </motion.div>

        {/* Section detail */}
        <AnimatePresence>
          {activeSection && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div className="glass-panel p-5 flex items-start gap-4">
                {(() => {
                  const info = SECTION_INFO[activeSection];
                  return (
                    <>
                      <div className="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center flex-shrink-0">
                        <info.icon className="w-5 h-5 text-accent" />
                      </div>
                      <div className="flex-1">
                        <h2 className="text-sm font-semibold text-foreground">{info.title}</h2>
                        <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{info.desc}</p>
                      </div>
                      <button onClick={() => setActiveSection(null)} className="text-muted-foreground hover:text-foreground">
                        <X className="w-4 h-4" />
                      </button>
                    </>
                  );
                })()}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── High-level flow ────────────────────────────────── */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
          <h2 className="text-lg font-semibold text-foreground mb-4">Request Flow</h2>
          <div className="flex items-center gap-0 overflow-x-auto pb-2">
            {[
              { label: "User", sub: "Browser", color: "bg-muted text-foreground border-border" },
              { label: "Frontend", sub: "React / Vite :5173", color: "bg-blue-500/10 text-blue-500 border-blue-500/20" },
              { label: "Backend", sub: "FastAPI :8000", color: "bg-blue-500/10 text-blue-500 border-blue-500/20" },
              { label: "Pipeline", sub: "LangGraph (8 nodes)", color: "bg-purple-500/10 text-purple-500 border-purple-500/20" },
              { label: "Output", sub: ".py + HTML Report", color: "bg-green-500/10 text-green-500 border-green-500/20" },
            ].map((item, i, arr) => (
              <div key={item.label} className="flex items-center flex-shrink-0">
                <div className={cn("px-5 py-3 rounded-xl border text-center min-w-[130px]", item.color)}>
                  <p className="text-sm font-semibold">{item.label}</p>
                  <p className="text-[10px] opacity-70 mt-0.5">{item.sub}</p>
                </div>
                {i < arr.length - 1 && (
                  <div className="flex items-center px-2">
                    <div className="w-8 h-0.5 bg-border" />
                    <div className="w-0 h-0 border-t-[4px] border-t-transparent border-b-[4px] border-b-transparent border-l-[6px] border-l-border" />
                  </div>
                )}
              </div>
            ))}
          </div>
        </motion.div>

        {/* ── 8-Node Pipeline ────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className={cn("glass-panel p-6 transition-all", activeSection === "pipeline" && "ring-2 ring-accent/30")}
        >
          <div className="flex items-center gap-2 mb-5">
            <Layers className="w-5 h-5 text-purple-500" />
            <h2 className="text-lg font-semibold text-foreground">8-Node LangGraph Pipeline</h2>
            <span className="text-[10px] text-muted-foreground ml-auto">State Machine &bull; Async &bull; Checkpointed</span>
          </div>

          {/* Pipeline snake layout: row 1 (1-4 left-to-right), row 2 (5-8 reversed) */}
          <div className="space-y-3">
            {/* Row 1: nodes 1-4 */}
            <div className="flex items-start gap-0 overflow-x-auto">
              {PIPELINE_NODES.slice(0, 4).map((node, i) => (
                <div key={node.id} className="flex items-start flex-shrink-0" style={{ minWidth: i < 3 ? 200 : 170 }}>
                  <motion.div
                    onMouseEnter={() => setHoveredNode(node.id)}
                    onMouseLeave={() => setHoveredNode(null)}
                    whileHover={{ scale: 1.03 }}
                    className={cn(
                      "rounded-xl border-2 p-4 bg-card transition-all cursor-default min-w-[160px]",
                      hoveredNode === node.id ? "border-purple-500 shadow-lg shadow-purple-500/10" : "border-purple-500/30"
                    )}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className="w-6 h-6 rounded-full bg-purple-500 text-white text-xs font-bold flex items-center justify-center">{node.id}</span>
                      <span className="text-xs font-bold text-purple-600 dark:text-purple-400">{node.name}</span>
                    </div>
                    {node.sub.map((s) => (
                      <p key={s} className="text-[11px] text-muted-foreground leading-relaxed">{s}</p>
                    ))}
                  </motion.div>
                  {i < 3 && (
                    <div className="flex items-center h-[80px] px-1 flex-shrink-0">
                      <div className="flex flex-col items-center">
                        <div className="w-6 h-0.5 bg-purple-500/40" />
                        <span className="text-[8px] text-purple-500/60 mt-0.5 whitespace-nowrap">{EDGE_LABELS[i]}</span>
                      </div>
                      <div className="w-0 h-0 border-t-[3px] border-t-transparent border-b-[3px] border-b-transparent border-l-[5px] border-l-purple-500/40" />
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Connector: row 1 → row 2 */}
            <div className="flex justify-end pr-[85px]">
              <div className="flex flex-col items-center">
                <div className="w-0.5 h-4 bg-purple-500/40" />
                <span className="text-[8px] text-purple-500/60">{EDGE_LABELS[3]}</span>
                <div className="w-0 h-0 border-l-[3px] border-l-transparent border-r-[3px] border-r-transparent border-t-[5px] border-t-purple-500/40" />
              </div>
            </div>

            {/* Row 2: nodes 5-8 (reversed direction) */}
            <div className="flex items-start gap-0 overflow-x-auto flex-row-reverse">
              {PIPELINE_NODES.slice(4).reverse().map((node, i) => (
                <div key={node.id} className="flex items-start flex-row-reverse flex-shrink-0" style={{ minWidth: i < 3 ? 200 : 170 }}>
                  <motion.div
                    onMouseEnter={() => setHoveredNode(node.id)}
                    onMouseLeave={() => setHoveredNode(null)}
                    whileHover={{ scale: 1.03 }}
                    className={cn(
                      "rounded-xl border-2 p-4 bg-card transition-all cursor-default min-w-[160px]",
                      hoveredNode === node.id ? "border-purple-500 shadow-lg shadow-purple-500/10" : "border-purple-500/30"
                    )}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className="w-6 h-6 rounded-full bg-purple-500 text-white text-xs font-bold flex items-center justify-center">{node.id}</span>
                      <span className="text-xs font-bold text-purple-600 dark:text-purple-400">{node.name}</span>
                    </div>
                    {node.sub.map((s) => (
                      <p key={s} className="text-[11px] text-muted-foreground leading-relaxed">{s}</p>
                    ))}
                  </motion.div>
                  {i < 3 && (
                    <div className="flex items-center h-[80px] px-1 flex-shrink-0 flex-row-reverse">
                      <div className="w-0 h-0 border-t-[3px] border-t-transparent border-b-[3px] border-b-transparent border-r-[5px] border-r-purple-500/40" />
                      <div className="flex flex-col items-center">
                        <div className="w-6 h-0.5 bg-purple-500/40" />
                        <span className="text-[8px] text-purple-500/60 mt-0.5 whitespace-nowrap">{EDGE_LABELS[4 + i]}</span>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Output label */}
          <div className="flex justify-start mt-3 pl-[85px]">
            <div className="px-3 py-1.5 rounded-lg bg-green-500/10 border border-green-500/20 text-green-600 dark:text-green-400 text-xs font-semibold">
              Final .py + HTML Report
            </div>
          </div>
        </motion.div>

        {/* ── Bottom grid: Data, AI, Verification, Azure ───── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Data Layer */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
            className={cn("glass-panel p-5 transition-all", activeSection === "data" && "ring-2 ring-emerald-500/30")}
          >
            <div className="flex items-center gap-2 mb-4">
              <Database className="w-4 h-4 text-emerald-500" />
              <h3 className="text-sm font-semibold text-foreground">Data Layer</h3>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {DATA_STORES.map((ds) => (
                <div key={ds.name} className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
                  <p className="text-xs font-semibold text-foreground">{ds.name}</p>
                  <p className="text-[10px] text-muted-foreground mt-1 leading-relaxed">{ds.desc}</p>
                </div>
              ))}
            </div>
          </motion.div>

          {/* AI Providers */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className={cn("glass-panel p-5 transition-all", activeSection === "ai" && "ring-2 ring-amber-500/30")}
          >
            <div className="flex items-center gap-2 mb-4">
              <Cpu className="w-4 h-4 text-amber-500" />
              <h3 className="text-sm font-semibold text-foreground">AI & Embeddings</h3>
            </div>
            <div className="space-y-2">
              {AI_PROVIDERS.map((p, i) => (
                <div key={p.name} className="flex items-center gap-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                  <div className={cn(
                    "w-6 h-6 rounded-full flex items-center justify-center text-[9px] font-bold flex-shrink-0",
                    p.role === "primary" ? "bg-amber-500 text-white" : p.role === "fallback" ? "bg-amber-500/20 text-amber-600" : "bg-amber-500/10 text-amber-500"
                  )}>
                    {p.role === "primary" ? "P" : p.role === "fallback" ? `F${i}` : "E"}
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-foreground">{p.name}</p>
                    <p className="text-[10px] text-muted-foreground">{p.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>

          {/* Verification */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35 }}
            className={cn("glass-panel p-5 transition-all", activeSection === "verification" && "ring-2 ring-red-500/30")}
          >
            <div className="flex items-center gap-2 mb-4">
              <Shield className="w-4 h-4 text-red-500" />
              <h3 className="text-sm font-semibold text-foreground">Verification Layer</h3>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {VERIFICATION.map((v) => (
                <div key={v.name} className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
                  <p className="text-xs font-semibold text-foreground">{v.name}</p>
                  <p className="text-[10px] text-muted-foreground mt-1 leading-relaxed">{v.desc}</p>
                </div>
              ))}
            </div>
          </motion.div>

          {/* Azure Services */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className={cn("glass-panel p-5 transition-all", activeSection === "azure" && "ring-2 ring-blue-500/30")}
          >
            <div className="flex items-center gap-2 mb-4">
              <Cloud className="w-4 h-4 text-blue-500" />
              <h3 className="text-sm font-semibold text-foreground">Azure Cloud</h3>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {AZURE_SERVICES.map((s) => (
                <div key={s.name} className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
                  <p className="text-xs font-semibold text-foreground">{s.name}</p>
                  <p className="text-[10px] text-muted-foreground mt-1 leading-relaxed">{s.desc}</p>
                </div>
              ))}
            </div>
          </motion.div>
        </div>

        {/* ── CI/CD Pipeline ─────────────────────────────────── */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.45 }} className="glass-panel p-5">
          <div className="flex items-center gap-2 mb-4">
            <GitBranch className="w-4 h-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold text-foreground">DevOps & CI/CD Pipeline</h3>
          </div>
          <div className="flex items-center gap-0 overflow-x-auto pb-1">
            {[
              { label: "Push / PR", color: "bg-muted text-foreground border-border" },
              { label: "Lint", color: "bg-blue-500/10 text-blue-500 border-blue-500/20" },
              { label: "Pytest (248)", color: "bg-green-500/10 text-green-500 border-green-500/20" },
              { label: "Security Scan", color: "bg-red-500/10 text-red-500 border-red-500/20" },
              { label: "Docker Build", color: "bg-purple-500/10 text-purple-500 border-purple-500/20" },
              { label: "Deploy (OIDC)", color: "bg-amber-500/10 text-amber-500 border-amber-500/20" },
              { label: "Benchmark", color: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" },
            ].map((step, i, arr) => (
              <div key={step.label} className="flex items-center flex-shrink-0">
                <div className={cn("px-3 py-2 rounded-lg border text-[11px] font-medium whitespace-nowrap", step.color)}>
                  {step.label}
                </div>
                {i < arr.length - 1 && (
                  <div className="flex items-center px-1">
                    <div className="w-4 h-0.5 bg-border" />
                    <div className="w-0 h-0 border-t-[3px] border-t-transparent border-b-[3px] border-b-transparent border-l-[4px] border-l-border" />
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="flex items-center gap-4 mt-3 text-[10px] text-muted-foreground">
            <span>GitHub Actions</span>
            <span>&bull;</span>
            <span>Multi-stage Dockerfile</span>
            <span>&bull;</span>
            <span>GHCR Registry</span>
            <span>&bull;</span>
            <span>Azure Container Apps</span>
          </div>
        </motion.div>

        {/* CTA */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }} className="text-center py-6">
          <p className="text-sm text-muted-foreground mb-4">See the pipeline in action with a live demo conversion.</p>
          <div className="flex justify-center gap-3">
            <Link to="/demo">
              <Button variant="outline" size="sm" className="gap-1.5">Try Demo</Button>
            </Link>
            <Link to="/signup">
              <Button size="sm" className="bg-accent text-accent-foreground hover:bg-accent/90 gap-1.5">
                Get Started <ArrowRight className="w-3.5 h-3.5" />
              </Button>
            </Link>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
