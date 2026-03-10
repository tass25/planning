import { Link } from "react-router-dom";
import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { CodaraLogo } from "@/components/CodaraLogo";
import { ThemeToggle } from "@/components/ThemeToggle";
import {
  ArrowRight, Code2, GitBranch, Shield, BarChart3,
  Cpu, Zap, Star, ChevronRight, CheckCircle2,
  Building2, Lock, Globe
} from "lucide-react";
import { motion, useScroll, useTransform } from "framer-motion";
import { cn } from "@/lib/utils";

const fadeUp = (delay = 0) => ({
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true },
  transition: { duration: 0.5, delay },
});

const FEATURES = [
  { icon: Cpu, title: "8-Stage AI Pipeline", desc: "Multi-pass AST analysis, intelligent partitioning, and context-aware translation with automatic validation loops.", color: "accent" },
  { icon: GitBranch, title: "Side-by-Side Diffs", desc: "Synchronized scrolling code comparison with inline annotations showing exactly what changed and why.", color: "secondary" },
  { icon: Shield, title: "Enterprise QA", desc: "Built-in validation, automated test generation, and repair stages ensure production-grade output every time.", color: "success" },
  { icon: BarChart3, title: "Full Observability", desc: "Track every conversion, audit LLM calls, monitor costs, and review system health through a unified dashboard.", color: "accent" },
];

const STATS = [
  { value: "97.3%", label: "Avg Accuracy" },
  { value: "10x", label: "Faster Migration" },
  { value: "2,400+", label: "Programs Converted" },
  { value: "<3min", label: "Avg Convert Time" },
];

const LOGOS = ["Meridian Health", "DataFirst", "Apex Financial", "NovaTech", "Syndicate Bank"];

const STEPS = [
  { step: "01", title: "Upload", desc: "Drag & drop your .sas files or connect your repository. Codara auto-detects dependencies and macros." },
  { step: "02", title: "Analyze", desc: "The 8-stage AI pipeline parses, partitions, and translates your code with full context awareness." },
  { step: "03", title: "Review", desc: "Compare SAS → Python side-by-side with syntax highlighting, inline diffs, and accuracy scores." },
  { step: "04", title: "Ship", desc: "Export production-ready Python with generated tests, documentation, and migration reports." },
];

export default function LandingPage() {
  const heroRef = useRef<HTMLElement>(null);
  const codeRef = useRef<HTMLDivElement>(null);
  const ctaRef = useRef<HTMLElement>(null);

  const { scrollYProgress: heroProgress } = useScroll({ target: heroRef, offset: ["start start", "end start"] });
  const { scrollYProgress: codeProgress } = useScroll({ target: codeRef, offset: ["start end", "end start"] });
  const { scrollYProgress: ctaProgress } = useScroll({ target: ctaRef, offset: ["start end", "end start"] });

  // Hero parallax
  const heroOrbY1 = useTransform(heroProgress, [0, 1], [0, 150]);
  const heroOrbY2 = useTransform(heroProgress, [0, 1], [0, 100]);
  const heroTextY = useTransform(heroProgress, [0, 1], [0, 60]);
  const heroOpacity = useTransform(heroProgress, [0, 0.7], [1, 0]);
  const gridY = useTransform(heroProgress, [0, 1], [0, 40]);

  // Code preview parallax
  const codeY = useTransform(codeProgress, [0, 1], [60, -40]);
  const codeScale = useTransform(codeProgress, [0, 0.5, 1], [0.95, 1, 0.98]);

  const ctaOrbY2 = useTransform(ctaProgress, [0, 1], [-30, 50]);

  // CTA parallax
  const ctaOrbY = useTransform(ctaProgress, [0, 1], [40, -40]);

  return (
    <div className="min-h-screen bg-background overflow-x-hidden">
      {/* Nav */}
      <nav className="border-b border-border/50 backdrop-blur-xl sticky top-0 z-50 bg-background/80">
        <div className="max-w-7xl mx-auto flex items-center justify-between px-6 h-16">
          <CodaraLogo size="md" />
          <div className="hidden md:flex items-center gap-6">
            <a href="#features" className="text-sm text-muted-foreground hover:text-foreground transition-colors">Features</a>
            <a href="#how-it-works" className="text-sm text-muted-foreground hover:text-foreground transition-colors">How It Works</a>
            <a href="#pricing" className="text-sm text-muted-foreground hover:text-foreground transition-colors">Pricing</a>
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Link to="/login"><Button variant="ghost" size="sm" className="text-muted-foreground hover:text-foreground">Sign In</Button></Link>
            <Link to="/signup"><Button size="sm" className="bg-accent text-accent-foreground hover:bg-accent/90">Get Started Free</Button></Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section ref={heroRef} className="relative">
        {/* Background effects with parallax */}
        <div className="absolute inset-0 overflow-hidden">
          <motion.div style={{ y: heroOrbY1 }} className="absolute top-[-30%] left-[10%] w-[500px] h-[500px] bg-[radial-gradient(circle,hsl(var(--accent)/0.08)_0%,transparent_70%)] blur-3xl" />
          <motion.div style={{ y: heroOrbY2 }} className="absolute top-[-10%] right-[5%] w-[400px] h-[400px] bg-[radial-gradient(circle,hsl(var(--secondary)/0.06)_0%,transparent_70%)] blur-3xl" />
          <motion.div style={{ y: gridY }} className="absolute inset-0 opacity-[0.02]" >
            <div className="w-full h-[200%]" style={{
              backgroundImage: `linear-gradient(hsl(var(--foreground)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--foreground)) 1px, transparent 1px)`,
              backgroundSize: "80px 80px"
            }} />
          </motion.div>
        </div>

        <div className="max-w-7xl mx-auto px-6 pt-24 pb-20 relative z-10">
        <motion.div style={{ y: heroTextY, opacity: heroOpacity }} className="text-center max-w-4xl mx-auto">
            {/* Badge */}
            <motion.div {...fadeUp(0)} className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-accent/20 bg-accent/5 text-xs font-medium text-accent mb-8">
              <Zap className="w-3 h-3" />
              Trusted by enterprise teams worldwide
              <ChevronRight className="w-3 h-3" />
            </motion.div>

            <h1 className="text-5xl md:text-7xl font-extrabold text-foreground leading-[1.05] tracking-tight">
              Transform legacy SAS
              <br />
              <span className="bg-gradient-to-r from-accent via-amber-500 to-orange-500 bg-clip-text text-transparent">
                into modern Python
              </span>
            </h1>
            <p className="text-lg md:text-xl text-muted-foreground mt-6 max-w-2xl mx-auto leading-relaxed">
              Codara's 8-stage AI pipeline converts entire SAS codebases to production-ready Python — with 97.3% accuracy, full audit trails, and zero guesswork.
            </p>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mt-10">
              <Link to="/signup">
                <Button size="lg" className="bg-accent text-accent-foreground hover:bg-accent/90 glow-accent px-8 py-6 text-base font-semibold gap-2">
                  Start Free Trial <ArrowRight className="w-4 h-4" />
                </Button>
              </Link>

            </div>

            <p className="text-xs text-muted-foreground/60 mt-4">No credit card required · Free tier available · SOC2 compliant</p>
          </motion.div>

          {/* Code Preview with parallax */}
          <motion.div ref={codeRef} style={{ y: codeY, scale: codeScale }} className="mt-20 max-w-5xl mx-auto">
            <div className="relative">
              {/* Glow border */}
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-br from-accent/30 via-secondary/20 to-accent/10 blur-sm" />
              <div className="relative glass-panel p-1 rounded-2xl">
                <div className="bg-card rounded-xl overflow-hidden">
                  {/* Terminal header */}
                  <div className="flex items-center justify-between px-5 py-3 border-b border-border/50 bg-muted/20">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-destructive/50" />
                      <div className="w-3 h-3 rounded-full bg-warning/50" />
                      <div className="w-3 h-3 rounded-full bg-success/50" />
                    </div>
                    <span className="text-[11px] text-muted-foreground font-mono">codara pipeline — customer_segmentation.sas → .py</span>
                    <div className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
                      <span className="text-[10px] text-success font-mono">Converting</span>
                    </div>
                  </div>
                  {/* Code */}
                  <div className="grid grid-cols-2 divide-x divide-border/50">
                    <div className="p-5">
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-3">SAS Input</p>
                      <pre className="text-[12px] font-mono leading-relaxed">
                        <span className="text-muted-foreground/50">/* Customer segmentation */</span>{"\n"}
                        <span className="text-blue-400 dark:text-blue-300">PROC SQL</span><span className="text-foreground/70">;</span>{"\n"}
                        <span className="text-foreground/60">  </span><span className="text-purple-400 dark:text-purple-300">CREATE TABLE</span><span className="text-foreground/70"> work.customers </span><span className="text-purple-400 dark:text-purple-300">AS</span>{"\n"}
                        <span className="text-foreground/60">  </span><span className="text-purple-400 dark:text-purple-300">SELECT</span><span className="text-foreground/70"> *, </span>{"\n"}
                        <span className="text-foreground/60">    </span><span className="text-blue-400 dark:text-blue-300">CASE</span>{"\n"}
                        <span className="text-foreground/60">      </span><span className="text-purple-400 dark:text-purple-300">WHEN</span><span className="text-foreground/70"> income </span><span className="text-accent">&gt;</span><span className="text-foreground/70"> 100000</span>{"\n"}
                        <span className="text-foreground/60">      </span><span className="text-purple-400 dark:text-purple-300">THEN</span><span className="text-emerald-400 dark:text-emerald-300"> 'Premium'</span>{"\n"}
                        <span className="text-foreground/60">    </span><span className="text-blue-400 dark:text-blue-300">END</span><span className="text-foreground/70"> </span><span className="text-purple-400 dark:text-purple-300">AS</span><span className="text-foreground/70"> segment</span>{"\n"}
                        <span className="text-foreground/60">  </span><span className="text-purple-400 dark:text-purple-300">FROM</span><span className="text-foreground/70"> raw.data;</span>{"\n"}
                        <span className="text-blue-400 dark:text-blue-300">QUIT</span><span className="text-foreground/70">;</span>
                      </pre>
                    </div>
                    <div className="p-5 bg-accent/[0.02]">
                      <div className="flex items-center justify-between mb-3">
                        <p className="text-[10px] uppercase tracking-wider text-accent font-semibold">Python Output</p>
                        <span className="text-[10px] text-success font-mono flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> 98.4%</span>
                      </div>
                      <pre className="text-[12px] font-mono leading-relaxed">
                        <span className="text-muted-foreground/50"># Codara AI Pipeline v3.2</span>{"\n"}
                        <span className="text-purple-400 dark:text-purple-300">import</span><span className="text-foreground/70"> pandas </span><span className="text-purple-400 dark:text-purple-300">as</span><span className="text-foreground/70"> pd</span>{"\n\n"}
                        <span className="text-blue-400 dark:text-blue-300">def</span><span className="text-accent"> segment_customers</span><span className="text-foreground/70">(df):</span>{"\n"}
                        <span className="text-foreground/60">    </span><span className="text-foreground/70">customers </span><span className="text-accent">=</span><span className="text-foreground/70"> df.copy()</span>{"\n"}
                        <span className="text-foreground/60">    </span><span className="text-foreground/70">customers[</span><span className="text-emerald-400 dark:text-emerald-300">'segment'</span><span className="text-foreground/70">] </span><span className="text-accent">=</span>{"\n"}
                        <span className="text-foreground/60">      </span><span className="text-foreground/70">pd.</span><span className="text-blue-400 dark:text-blue-300">cut</span><span className="text-foreground/70">(</span>{"\n"}
                        <span className="text-foreground/60">        </span><span className="text-foreground/70">customers[</span><span className="text-emerald-400 dark:text-emerald-300">'income'</span><span className="text-foreground/70">],</span>{"\n"}
                        <span className="text-foreground/60">        </span><span className="text-foreground/70">labels</span><span className="text-accent">=</span><span className="text-foreground/70">[</span><span className="text-emerald-400 dark:text-emerald-300">'Basic'</span><span className="text-foreground/70">,</span><span className="text-emerald-400 dark:text-emerald-300">'Premium'</span><span className="text-foreground/70">]</span>{"\n"}
                        <span className="text-foreground/60">    </span><span className="text-foreground/70">)</span>
                      </pre>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Social Proof / Logos */}
      <section className="border-y border-border/30 bg-muted/10 py-10">
        <div className="max-w-7xl mx-auto px-6">
          <p className="text-center text-xs text-muted-foreground/60 uppercase tracking-widest font-medium mb-6">Trusted by teams at</p>
          <div className="flex items-center justify-center gap-12 flex-wrap">
            {LOGOS.map((name) => (
              <span key={name} className="text-sm font-semibold text-muted-foreground/30 tracking-wide">{name}</span>
            ))}
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="py-20">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            {STATS.map((stat, i) => (
              <motion.div key={stat.label} {...fadeUp(i * 0.08)} className="text-center">
                <p className="text-4xl md:text-5xl font-extrabold bg-gradient-to-br from-foreground to-foreground/60 bg-clip-text text-transparent">{stat.value}</p>
                <p className="text-sm text-muted-foreground mt-1.5">{stat.label}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-20 bg-muted/10">
        <div className="max-w-7xl mx-auto px-6">
          <motion.div {...fadeUp(0)} className="text-center mb-14">
            <p className="text-xs uppercase tracking-widest text-accent font-semibold mb-3">Capabilities</p>
            <h2 className="text-3xl md:text-4xl font-extrabold text-foreground">Enterprise-grade from day one</h2>
            <p className="text-muted-foreground mt-3 max-w-lg mx-auto">Everything you need to migrate SAS codebases at scale — with confidence, auditability, and speed.</p>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {FEATURES.map((f, i) => {
              const colorClasses: Record<string, string> = {
                accent: "bg-accent/10 text-accent group-hover:bg-accent/15",
                secondary: "bg-secondary/10 text-secondary group-hover:bg-secondary/15",
                success: "bg-success/10 text-success group-hover:bg-success/15",
              };
              return (
                <motion.div
                  key={f.title}
                  {...fadeUp(i * 0.08)}
                  className="glass-panel p-7 hover:border-accent/20 transition-all duration-300 group"
                >
                  <div className="flex items-start gap-4">
                    <div className={cn("w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 transition-colors", colorClasses[f.color])}>
                      <f.icon className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-foreground mb-1.5">{f.title}</h3>
                      <p className="text-sm text-muted-foreground leading-relaxed">{f.desc}</p>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="py-24">
        <div className="max-w-7xl mx-auto px-6">
          <motion.div {...fadeUp(0)} className="text-center mb-16">
            <p className="text-xs uppercase tracking-widest text-accent font-semibold mb-3">Workflow</p>
            <h2 className="text-3xl md:text-4xl font-extrabold text-foreground">Four steps to production</h2>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            {STEPS.map((s, i) => (
              <motion.div key={s.step} {...fadeUp(i * 0.1)} className="relative group">
                {/* Connector line */}
                {i < STEPS.length - 1 && (
                  <div className="hidden md:block absolute top-8 left-[calc(100%+1px)] w-[calc(100%-56px)] h-px bg-gradient-to-r from-border to-border/30 z-0" style={{ left: "calc(50% + 28px)", width: "calc(100% - 56px)" }} />
                )}
                <div className="relative z-10 text-center">
                  <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-accent/10 to-secondary/10 border border-accent/10 flex items-center justify-center mx-auto mb-5 group-hover:scale-110 group-hover:border-accent/30 transition-all">
                    <span className="text-lg font-extrabold text-accent font-mono">{s.step}</span>
                  </div>
                  <h3 className="text-base font-bold text-foreground mb-2">{s.title}</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">{s.desc}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Trust / Security */}
      <section className="py-20 bg-muted/10">
        <div className="max-w-7xl mx-auto px-6">
          <motion.div {...fadeUp(0)} className="text-center mb-12">
            <p className="text-xs uppercase tracking-widest text-accent font-semibold mb-3">Security & Compliance</p>
            <h2 className="text-3xl md:text-4xl font-extrabold text-foreground">Built for regulated industries</h2>
          </motion.div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {[
              { icon: Lock, title: "SOC2 Type II", desc: "Independently audited security controls with continuous monitoring and annual certification." },
              { icon: Building2, title: "HIPAA Compliant", desc: "Full BAA support with encrypted data handling, access controls, and audit logging." },
              { icon: Globe, title: "Enterprise SSO", desc: "SAML 2.0 and OIDC integration with major identity providers. Role-based access built in." },
            ].map((item, i) => (
              <motion.div key={item.title} {...fadeUp(i * 0.08)} className="glass-panel p-7 text-center hover:border-accent/20 transition-all">
                <div className="w-12 h-12 rounded-2xl bg-accent/10 flex items-center justify-center mx-auto mb-4">
                  <item.icon className="w-5 h-5 text-accent" />
                </div>
                <h3 className="text-base font-bold text-foreground mb-1.5">{item.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{item.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section ref={ctaRef} className="py-24 relative overflow-hidden">
        <div className="absolute inset-0">
          <motion.div style={{ y: ctaOrbY }} className="absolute top-0 left-[20%] w-[400px] h-[400px] bg-[radial-gradient(circle,hsl(var(--accent)/0.06)_0%,transparent_70%)] blur-3xl" />
          <motion.div style={{ y: ctaOrbY2 }} className="absolute bottom-0 right-[20%] w-[300px] h-[300px] bg-[radial-gradient(circle,hsl(var(--secondary)/0.05)_0%,transparent_70%)] blur-3xl" />
        </div>
        <motion.div {...fadeUp(0)} className="max-w-3xl mx-auto px-6 text-center relative z-10">
          <h2 className="text-3xl md:text-5xl font-extrabold text-foreground leading-tight">
            Ready to leave SAS behind?
          </h2>
          <p className="text-lg text-muted-foreground mt-5 max-w-xl mx-auto">
            Start converting your first program in minutes. No credit card, no setup, no vendor lock-in.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mt-10">
            <Link to="/signup">
              <Button size="lg" className="bg-accent text-accent-foreground hover:bg-accent/90 glow-accent px-8 py-6 text-base font-semibold gap-2">
                Start Free Trial <ArrowRight className="w-4 h-4" />
              </Button>
            </Link>
            <Link to="/login">
              <Button variant="outline" size="lg" className="border-border text-muted-foreground hover:text-foreground px-8 py-6 text-base">
                Talk to Sales
              </Button>
            </Link>
          </div>
        </motion.div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border/50 py-12 bg-muted/5">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-10">
            <div>
              <CodaraLogo size="md" />
              <p className="text-xs text-muted-foreground mt-3 leading-relaxed">Enterprise-grade SAS to Python migration powered by AI.</p>
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground uppercase tracking-wider mb-3">Product</p>
              <div className="space-y-2">
                <a href="#features" className="text-sm text-muted-foreground hover:text-foreground transition-colors block">Features</a>
                <a href="#how-it-works" className="text-sm text-muted-foreground hover:text-foreground transition-colors block">How It Works</a>
                <a href="#pricing" className="text-sm text-muted-foreground hover:text-foreground transition-colors block">Pricing</a>
              </div>
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground uppercase tracking-wider mb-3">Company</p>
              <div className="space-y-2">
                <a href="#" className="text-sm text-muted-foreground hover:text-foreground transition-colors block">About</a>
                <a href="#" className="text-sm text-muted-foreground hover:text-foreground transition-colors block">Blog</a>
                <a href="#" className="text-sm text-muted-foreground hover:text-foreground transition-colors block">Careers</a>
              </div>
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground uppercase tracking-wider mb-3">Legal</p>
              <div className="space-y-2">
                <a href="#" className="text-sm text-muted-foreground hover:text-foreground transition-colors block">Privacy</a>
                <a href="#" className="text-sm text-muted-foreground hover:text-foreground transition-colors block">Terms</a>
                <a href="#" className="text-sm text-muted-foreground hover:text-foreground transition-colors block">Security</a>
              </div>
            </div>
          </div>
          <div className="border-t border-border/50 pt-6 flex items-center justify-between">
            <span className="text-xs text-muted-foreground/60">© 2026 Codara Inc. All rights reserved.</span>
            <div className="flex items-center gap-4 text-muted-foreground/40">
              <span className="text-[10px]">SOC2</span>
              <span className="text-[10px]">HIPAA</span>
              <span className="text-[10px]">GDPR</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
