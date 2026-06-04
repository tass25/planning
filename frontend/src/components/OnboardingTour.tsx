import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, GitCompare, Download, Sparkles, X, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";

const STEPS = [
  {
    icon: Upload,
    title: "Upload SAS Files",
    desc: "Drag & drop your .sas files to begin. Codara auto-detects dependencies, macros, and complexity.",
    color: "accent",
    path: "/conversions",
  },
  {
    icon: Sparkles,
    title: "Watch the Pipeline",
    desc: "The 8-stage AI pipeline parses, partitions, routes, translates, and validates your code automatically.",
    color: "secondary",
  },
  {
    icon: GitCompare,
    title: "Review Side-by-Side",
    desc: "Compare SAS and Python in a GitHub-style diff view. Check accuracy scores, partitions, and risk levels.",
    color: "success",
  },
  {
    icon: Download,
    title: "Export & Iterate",
    desc: "Download production-ready Python, submit corrections to improve the knowledge base, and track your history.",
    color: "accent",
  },
];

const STORAGE_KEY = "codara_onboarding_done";

export function OnboardingTour() {
  const [step, setStep] = useState(0);
  const [visible, setVisible] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const done = localStorage.getItem(STORAGE_KEY);
    if (!done) setVisible(true);
  }, []);

  const dismiss = () => {
    setVisible(false);
    localStorage.setItem(STORAGE_KEY, "1");
  };

  const next = () => {
    if (step < STEPS.length - 1) {
      setStep(step + 1);
    } else {
      dismiss();
      navigate("/conversions");
    }
  };

  if (!visible) return null;

  const s = STEPS[step];
  const colorMap: Record<string, string> = {
    accent: "bg-accent/10 text-accent border-accent/20",
    secondary: "bg-secondary/10 text-secondary border-secondary/20",
    success: "bg-success/10 text-success border-success/20",
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[100] bg-background/80 backdrop-blur-sm flex items-center justify-center p-4"
      >
        <motion.div
          key={step}
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: -20 }}
          transition={{ duration: 0.3 }}
          className="glass-panel max-w-md w-full p-8 relative"
        >
          <button onClick={dismiss} className="absolute top-4 right-4 text-muted-foreground hover:text-foreground transition-colors">
            <X className="w-4 h-4" />
          </button>

          <div className={`w-14 h-14 rounded-2xl border flex items-center justify-center mb-5 ${colorMap[s.color]}`}>
            <s.icon className="w-6 h-6" />
          </div>

          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-2">
            Step {step + 1} of {STEPS.length}
          </p>
          <h2 className="text-xl font-bold text-foreground mb-2">{s.title}</h2>
          <p className="text-sm text-muted-foreground leading-relaxed">{s.desc}</p>

          <div className="flex items-center justify-between mt-8">
            <div className="flex gap-1.5">
              {STEPS.map((_, i) => (
                <div key={i} className={`w-2 h-2 rounded-full transition-colors ${i === step ? "bg-accent" : i < step ? "bg-accent/40" : "bg-muted"}`} />
              ))}
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={dismiss} className="text-muted-foreground">
                Skip
              </Button>
              <Button size="sm" onClick={next} className="bg-accent text-accent-foreground hover:bg-accent/90 gap-1.5">
                {step < STEPS.length - 1 ? "Next" : "Get Started"}
                <ArrowRight className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
