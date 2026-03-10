import { useState, useEffect } from "react";
import { useUserStore } from "@/store/user-store";
import { useNavigate, Link, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { CodaraLogo } from "@/components/CodaraLogo";
import { Loader2, Eye, EyeOff, ArrowRight, Copy, Check, Zap, Shield, Cpu, BarChart3 } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";

const DEMO_CREDENTIALS = {
  admin: { email: "admin@codara.dev", password: "admin123!" },
  user: { email: "user@codara.dev", password: "user123!" },
};

const FEATURES = [
  { icon: Cpu, label: "8-Stage AI Pipeline", desc: "Multi-pass translation with AST analysis" },
  { icon: Shield, label: "Enterprise Security", desc: "SOC2 compliant, audit logging built in" },
  { icon: BarChart3, label: "97.3% Accuracy", desc: "Validated across 10K+ SAS programs" },
  { icon: Zap, label: "10x Faster", desc: "Minutes not months for migration" },
];

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const { login, loginWithGitHub, isLoading } = useUserStore();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Handle GitHub OAuth callback
  useEffect(() => {
    const code = searchParams.get("code");
    if (code) {
      loginWithGitHub(code).then((ok) => {
        if (ok) navigate("/dashboard");
        else setError("GitHub login failed");
      });
    }
  }, [searchParams, loginWithGitHub, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!email || !password) { setError("Please fill in all fields"); return; }
    const success = await login(email, password);
    if (success) navigate("/dashboard");
    else setError("Invalid credentials");
  };

  const handleGitHubLogin = async () => {
    try {
      const { url } = await api.get<{ url: string }>("/auth/github/url");
      window.location.href = url;
    } catch {
      setError("GitHub OAuth not configured");
    }
  };

  const fillCredentials = (role: "admin" | "user") => {
    setEmail(DEMO_CREDENTIALS[role].email);
    setPassword(DEMO_CREDENTIALS[role].password);
    setError("");
  };

  const copyToClipboard = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 1500);
  };

  return (
    <div className="min-h-screen bg-background flex">
      {/* Left - Premium Branding Panel */}
      <div className="hidden lg:flex lg:w-[52%] relative overflow-hidden">
        {/* Deep layered gradient background */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,hsl(270,55%,15%)_0%,hsl(245,40%,8%)_50%,hsl(230,30%,5%)_100%)]" />
        
        {/* Animated mesh gradients */}
        <div className="absolute inset-0">
          <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] bg-[radial-gradient(circle,hsl(270,60%,30%,0.4)_0%,transparent_70%)] blur-3xl animate-pulse" style={{ animationDuration: "4s" }} />
          <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-[radial-gradient(circle,hsl(38,92%,50%,0.15)_0%,transparent_70%)] blur-3xl animate-pulse" style={{ animationDuration: "6s", animationDelay: "2s" }} />
          <div className="absolute top-[40%] right-[20%] w-[30%] h-[30%] bg-[radial-gradient(circle,hsl(200,80%,50%,0.08)_0%,transparent_70%)] blur-2xl animate-pulse" style={{ animationDuration: "5s", animationDelay: "1s" }} />
        </div>

        {/* Subtle grid overlay */}
        <div className="absolute inset-0 opacity-[0.03]" style={{
          backgroundImage: `linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)`,
          backgroundSize: "80px 80px"
        }} />

        {/* Diagonal accent line */}
        <div className="absolute top-0 right-0 w-px h-full bg-gradient-to-b from-transparent via-accent/20 to-transparent" />

        <div className="relative z-10 flex flex-col justify-between p-12 w-full">
          <CodaraLogo size="lg" variant="light" />

          <div className="space-y-10">
            <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15, duration: 0.6 }}>
              <h2 className="text-5xl font-extrabold text-white leading-[1.1] tracking-tight">
                Transform legacy SAS
                <br />
                <span className="bg-gradient-to-r from-accent via-amber-400 to-orange-400 bg-clip-text text-transparent">
                  into modern Python
                </span>
              </h2>
              <p className="text-white/40 text-lg mt-5 max-w-md leading-relaxed">
                Enterprise-grade code migration powered by an 8-stage AI pipeline. Production-ready output, not prototypes.
              </p>
            </motion.div>

            {/* Feature cards */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35, duration: 0.5 }} className="grid grid-cols-2 gap-3">
              {FEATURES.map((f, i) => (
                <motion.div
                  key={f.label}
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.45 + i * 0.08 }}
                  className="flex items-start gap-3 p-3.5 rounded-xl bg-white/[0.04] border border-white/[0.06] backdrop-blur-sm hover:bg-white/[0.07] transition-colors"
                >
                  <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <f.icon className="w-4 h-4 text-accent" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-white/90">{f.label}</p>
                    <p className="text-[11px] text-white/35 mt-0.5 leading-relaxed">{f.desc}</p>
                  </div>
                </motion.div>
              ))}
            </motion.div>

            {/* Code snippet */}
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.7 }}
              className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-5 max-w-md backdrop-blur-sm"
            >
              <div className="flex items-center gap-2 mb-3">
                <div className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
                <div className="w-2.5 h-2.5 rounded-full bg-amber-500/60" />
                <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/60" />
                <span className="ml-auto text-[10px] text-white/20 font-mono">output.py</span>
              </div>
              <pre className="text-[12px] font-mono leading-relaxed">
                <span className="text-white/30"># Codara AI Pipeline Output</span>{"\n"}
                <span className="text-purple-400">customers</span> <span className="text-white/50">=</span> <span className="text-blue-400">raw_data</span><span className="text-white/40">.</span><span className="text-amber-400">query</span><span className="text-white/40">(</span>{"\n"}
                <span className="text-emerald-400">    "status == 'active'"</span>{"\n"}
                <span className="text-white/40">)</span>{"\n"}
                <span className="text-purple-400">segments</span> <span className="text-white/50">=</span> <span className="text-blue-400">pd</span><span className="text-white/40">.</span><span className="text-amber-400">cut</span><span className="text-white/40">(</span><span className="text-purple-400">income</span><span className="text-white/40">)</span>
              </pre>
            </motion.div>
          </div>

          <div className="flex items-center gap-8 text-white/25 text-xs font-medium">
            <span>SOC2 Compliant</span>
            <span className="w-1 h-1 rounded-full bg-white/20" />
            <span>HIPAA Ready</span>
            <span className="w-1 h-1 rounded-full bg-white/20" />
            <span>Enterprise SSO</span>
          </div>
        </div>
      </div>

      {/* Right - Login Form */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12">
        <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="w-full max-w-md space-y-8">
          <div className="lg:hidden mb-8">
            <CodaraLogo size="lg" />
          </div>

          <div>
            <h1 className="text-2xl font-bold text-foreground">Welcome back</h1>
            <p className="text-sm text-muted-foreground mt-1">Sign in to your Codara workspace</p>
          </div>

          {/* Demo Credentials */}
          <div className="p-4 rounded-xl border border-accent/20 bg-accent/5 space-y-3">
            <p className="text-xs font-semibold text-accent uppercase tracking-wider">Demo Credentials</p>
            <div className="grid grid-cols-2 gap-2">
              {(["admin", "user"] as const).map((role) => (
                <button
                  key={role}
                  onClick={() => fillCredentials(role)}
                  className="flex flex-col items-start gap-1 p-3 rounded-lg border border-border hover:border-accent/40 hover:bg-accent/5 transition-all text-left group"
                >
                  <div className="flex items-center justify-between w-full">
                    <span className="text-xs font-semibold text-foreground capitalize">{role}</span>
                    <ArrowRight className="w-3 h-3 text-muted-foreground group-hover:text-accent transition-colors" />
                  </div>
                  <span className="text-[10px] text-muted-foreground font-mono">{DEMO_CREDENTIALS[role].email}</span>
                  <div className="flex items-center gap-1">
                    <span className="text-[10px] text-muted-foreground font-mono">{DEMO_CREDENTIALS[role].password}</span>
                    <button
                      onClick={(e) => { e.stopPropagation(); copyToClipboard(DEMO_CREDENTIALS[role].password, `${role}-pw`); }}
                      className="p-0.5 hover:text-accent transition-colors"
                    >
                      {copiedField === `${role}-pw` ? <Check className="w-2.5 h-2.5 text-success" /> : <Copy className="w-2.5 h-2.5" />}
                    </button>
                  </div>
                </button>
              ))}
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <motion.div initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }} className="text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2.5">
                {error}
              </motion.div>
            )}

            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1.5">Email address</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" className="w-full bg-muted/30 border border-border rounded-lg px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20 transition-all" />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-medium text-muted-foreground">Password</label>
                <button type="button" className="text-xs text-accent hover:underline">Forgot?</button>
              </div>
              <div className="relative">
                <input type={showPassword ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" className="w-full bg-muted/30 border border-border rounded-lg px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20 transition-all pr-10" />
                <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors">
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <Button type="submit" disabled={isLoading} className="w-full py-6 text-sm font-semibold bg-gradient-to-r from-accent to-accent/80 text-accent-foreground hover:opacity-90 transition-opacity glow-accent">
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Sign In"}
            </Button>
          </form>

          <div className="relative">
            <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-border" /></div>
            <div className="relative flex justify-center text-xs"><span className="bg-background px-3 text-muted-foreground">or continue with</span></div>
          </div>

          <div className="grid grid-cols-1 gap-3">
            <button
              onClick={handleGitHubLogin}
              disabled={isLoading}
              className="flex items-center justify-center gap-2 py-2.5 rounded-lg border border-border hover:bg-muted/30 transition-colors text-sm text-muted-foreground hover:text-foreground"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
              Continue with GitHub
            </button>
          </div>

          <p className="text-center text-xs text-muted-foreground">
            Don't have an account? <Link to="/signup" className="text-accent font-medium hover:underline">Create one</Link>
          </p>
        </motion.div>
      </div>
    </div>
  );
}
