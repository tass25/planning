import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { CodaraLogo } from "@/components/CodaraLogo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { CheckCircle, Code2, ArrowLeft, ArrowRight, Shield, Zap, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";
import { usePageTitle } from "@/lib/hooks";

const DEMO_SAS = `/* Customer segmentation pipeline */
DATA work.customers;
  SET raw.customer_data;
  LENGTH segment $20;
  IF income > 100000 THEN segment = 'Premium';
  ELSE IF income > 50000 THEN segment = 'Standard';
  ELSE segment = 'Basic';

  lifetime_value = income * tenure_years * 0.15;

  IF lifetime_value > 50000 THEN priority = 'HIGH';
  ELSE priority = 'NORMAL';
RUN;

PROC SQL;
  CREATE TABLE work.summary AS
  SELECT segment,
         COUNT(*) AS n_customers,
         MEAN(lifetime_value) AS avg_ltv,
         SUM(revenue) AS total_revenue
  FROM work.customers
  GROUP BY segment
  ORDER BY avg_ltv DESC;
QUIT;`;

const DEMO_PYTHON = `# Codara AI Pipeline v3.1.0
import pandas as pd

def segment_customers(df: pd.DataFrame) -> pd.DataFrame:
    customers = df.copy()

    conditions = [
        customers['income'] > 100000,
        customers['income'] > 50000,
    ]
    choices = ['Premium', 'Standard']
    customers['segment'] = pd.np.select(
        conditions, choices, default='Basic'
    )

    customers['lifetime_value'] = (
        customers['income'] * customers['tenure_years'] * 0.15
    )

    customers['priority'] = pd.np.where(
        customers['lifetime_value'] > 50000, 'HIGH', 'NORMAL'
    )

    return customers

def create_summary(customers: pd.DataFrame) -> pd.DataFrame:
    summary = (
        customers
        .groupby('segment')
        .agg(
            n_customers=('segment', 'size'),
            avg_ltv=('lifetime_value', 'mean'),
            total_revenue=('revenue', 'sum'),
        )
        .sort_values('avg_ltv', ascending=False)
        .reset_index()
    )
    return summary`;

const DEMO_STAGES = [
  { name: "File Processing", status: "completed", latency: "0.3s" },
  { name: "SAS Partitioning", status: "completed", latency: "0.8s" },
  { name: "Dependency Resolution", status: "completed", latency: "0.2s" },
  { name: "LLM Translation", status: "completed", latency: "4.2s" },
  { name: "Syntax Validation", status: "completed", latency: "1.1s" },
  { name: "CEGAR Repair", status: "completed", latency: "0.0s" },
  { name: "Module Assembly", status: "completed", latency: "0.4s" },
  { name: "Finalization", status: "completed", latency: "0.1s" },
];

export default function DemoPage() {
  usePageTitle("Demo");
  const sasLines = DEMO_SAS.split("\n");
  const pyLines = DEMO_PYTHON.split("\n");
  const maxLines = Math.max(sasLines.length, pyLines.length);

  return (
    <div className="min-h-screen bg-background">
      <nav className="border-b border-border/50 backdrop-blur-xl sticky top-0 z-50 bg-background/80">
        <div className="max-w-7xl mx-auto flex items-center justify-between px-6 h-16">
          <div className="flex items-center gap-4">
            <Link to="/">
              <CodaraLogo size="md" />
            </Link>
            <span className="text-[10px] font-semibold uppercase tracking-widest text-accent bg-accent/10 px-2 py-1 rounded">
              Live Demo
            </span>
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

      <div className="max-w-7xl mx-auto px-6 py-8 space-y-6">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
          <Link to="/" className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 mb-4">
            <ArrowLeft className="w-3 h-3" /> Back to Home
          </Link>
          <h1 className="text-2xl font-bold text-foreground">customer_segmentation.sas</h1>
          <div className="flex items-center gap-3 mt-2">
            <span className="text-xs font-medium bg-success/15 text-success border border-success/20 px-2 py-0.5 rounded">Completed</span>
            <span className="text-xs text-muted-foreground font-mono">python</span>
            <span className="text-xs text-success font-medium">96.4% accuracy</span>
          </div>
        </motion.div>

        {/* Pipeline */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass-panel p-5">
          <h2 className="text-sm font-semibold text-foreground mb-4">Pipeline</h2>
          <div className="flex items-start gap-0 overflow-x-auto">
            {DEMO_STAGES.map((s, i) => (
              <div key={s.name} className="flex items-start flex-shrink-0" style={{ minWidth: i < DEMO_STAGES.length - 1 ? 140 : 100 }}>
                <div className="flex flex-col items-center">
                  <div className="w-10 h-10 rounded-xl border-2 border-success bg-success/10 text-success flex items-center justify-center">
                    <CheckCircle className="w-4 h-4" />
                  </div>
                  <span className="text-[10px] font-medium mt-2 text-center leading-tight max-w-[90px]">{s.name}</span>
                  <span className="text-[9px] text-muted-foreground font-mono mt-0.5">{s.latency}</span>
                </div>
                {i < DEMO_STAGES.length - 1 && (
                  <div className="flex items-center h-10 flex-1 px-1">
                    <div className="h-0.5 w-full rounded-full bg-success" />
                    <div className="w-0 h-0 border-t-[4px] border-t-transparent border-b-[4px] border-b-transparent border-l-[6px] border-l-success" />
                  </div>
                )}
              </div>
            ))}
          </div>
        </motion.div>

        {/* Score cards */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { icon: BarChart3, label: "Accuracy", value: "96.4%", color: "text-accent" },
            { icon: Code2, label: "Partitions", value: "2", color: "text-secondary" },
            { icon: Zap, label: "Duration", value: "7.1s", color: "text-warning" },
            { icon: Shield, label: "Stages Passed", value: "8/8", color: "text-success" },
          ].map((card) => (
            <div key={card.label} className="glass-panel p-5 text-center">
              <card.icon className={cn("w-5 h-5 mx-auto mb-2", card.color)} />
              <p className="text-2xl font-bold text-foreground">{card.value}</p>
              <p className="text-[10px] text-muted-foreground mt-1">{card.label}</p>
            </div>
          ))}
        </motion.div>

        {/* Diff view */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="border border-border rounded-lg overflow-hidden bg-card">
          <div className="grid grid-cols-2 border-b border-border text-xs font-medium">
            <div className="flex items-center gap-2 px-3 py-2 bg-red-500/5 border-r border-border text-red-400">
              <Code2 className="w-3.5 h-3.5" />
              <span>customer_segmentation.sas</span>
              <span className="ml-auto text-muted-foreground font-mono">{sasLines.length} lines</span>
            </div>
            <div className="flex items-center gap-2 px-3 py-2 bg-green-500/5 text-green-400">
              <Code2 className="w-3.5 h-3.5" />
              <span>customer_segmentation.py</span>
              <span className="ml-auto text-muted-foreground font-mono">{pyLines.length} lines</span>
            </div>
          </div>
          <div className="grid grid-cols-2 divide-x divide-border max-h-[500px] overflow-auto">
            <div className="font-mono text-[12px] leading-relaxed">
              {Array.from({ length: maxLines }).map((_, i) => (
                <div key={i} className="flex hover:bg-red-500/[0.03]">
                  <span className="w-10 text-right pr-2 text-muted-foreground/30 select-none flex-shrink-0 border-r border-border/50 py-0.5">{i + 1}</span>
                  <span className="pl-3 py-0.5 text-foreground/70 whitespace-pre">{sasLines[i] || ""}</span>
                </div>
              ))}
            </div>
            <div className="font-mono text-[12px] leading-relaxed">
              {Array.from({ length: maxLines }).map((_, i) => (
                <div key={i} className="flex hover:bg-green-500/[0.03]">
                  <span className="w-10 text-right pr-2 text-muted-foreground/30 select-none flex-shrink-0 border-r border-border/50 py-0.5">{i + 1}</span>
                  <span className="pl-3 py-0.5 text-foreground/70 whitespace-pre">{pyLines[i] || ""}</span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* CTA */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="text-center py-8">
          <h2 className="text-xl font-bold text-foreground mb-2">Ready to convert your own SAS files?</h2>
          <p className="text-sm text-muted-foreground mb-6">Sign up in seconds and start converting immediately.</p>
          <Link to="/signup">
            <Button size="lg" className="bg-accent text-accent-foreground hover:bg-accent/90 gap-2 px-8">
              Get Started <ArrowRight className="w-4 h-4" />
            </Button>
          </Link>
        </motion.div>
      </div>
    </div>
  );
}
