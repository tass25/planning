import { useState } from "react";
import { useUserStore } from "@/store/user-store";
import { useNavigate, Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { CodaraLogo } from "@/components/CodaraLogo";
import { Loader2, Eye, EyeOff, CheckCircle, ArrowRight, Star, Mail, RefreshCw, Clock, ShieldCheck, Inbox } from "lucide-react";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { usePageTitle } from "@/lib/hooks";

const HIGHLIGHTS = [
  { icon: "🔬", title: "8-Stage AI Pipeline", desc: "LangGraph orchestration with deterministic parsing, RAPTOR clustering, and multi-tier RAG retrieval." },
  { icon: "✅", title: "Z3 Formal Verification", desc: "SMT-based proofs for arithmetic, boolean, sort/dedup, and assignment patterns in translations." },
];

export default function SignupPage() {
  usePageTitle("Sign Up");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [needsVerification, setNeedsVerification] = useState(false);
  const [resendLoading, setResendLoading] = useState(false);
  const [resendDone, setResendDone] = useState(false);
  const { signup, resendVerification, isLoading } = useUserStore();
  const navigate = useNavigate();

  const passwordChecks = [
    { label: "8+ characters", valid: password.length >= 8 },
    { label: "One uppercase", valid: /[A-Z]/.test(password) },
    { label: "One number", valid: /\d/.test(password) },
  ];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!name || !email || !password) { setError("Please fill in all fields"); return; }
    if (password.length < 8) { setError("Password must be at least 8 characters"); return; }
    const result = await signup(email, password, name);
    if (result.success) {
      if (result.needsVerification) {
        setNeedsVerification(true);
      } else {
        navigate("/dashboard");
      }
    } else {
      setError("Signup failed — email may already be in use");
    }
  };

  const handleGitHubSignup = async () => {
    try {
      const { url } = await api.get<{ url: string }>("/auth/github/url");
      window.location.href = url;
    } catch {
      setError("GitHub OAuth not configured");
    }
  };

  const handleResend = async () => {
    setResendLoading(true);
    await resendVerification();
    setResendLoading(false);
    setResendDone(true);
    setTimeout(() => setResendDone(false), 30000);
  };

  if (needsVerification) {
    return (
      <div className="min-h-screen bg-background flex">
        {/* Left — branding panel */}
        <div className="hidden lg:flex lg:w-[52%] relative overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_right,hsl(270,55%,15%)_0%,hsl(245,40%,8%)_50%,hsl(230,30%,5%)_100%)]" />
          <div className="absolute inset-0">
            <div className="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] bg-[radial-gradient(circle,hsl(270,60%,30%,0.35)_0%,transparent_70%)] blur-3xl animate-pulse" style={{ animationDuration: "5s" }} />
            <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-[radial-gradient(circle,hsl(38,92%,50%,0.12)_0%,transparent_70%)] blur-3xl animate-pulse" style={{ animationDuration: "7s", animationDelay: "1.5s" }} />
          </div>
          <div className="absolute inset-0 opacity-[0.03]" style={{
            backgroundImage: "linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)",
            backgroundSize: "80px 80px"
          }} />
          <div className="absolute top-0 right-0 w-px h-full bg-gradient-to-b from-transparent via-accent/20 to-transparent" />

          <div className="relative z-10 flex flex-col justify-between p-12 w-full">
            <CodaraLogo size="lg" variant="light" />

            <div className="space-y-10">
              <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15, duration: 0.6 }}>
                <h2 className="text-5xl font-extrabold text-white leading-[1.1] tracking-tight">
                  One last
                  <br />
                  <span className="bg-gradient-to-r from-accent via-amber-400 to-orange-400 bg-clip-text text-transparent">
                    step
                  </span>
                </h2>
                <p className="text-white/40 text-lg mt-5 max-w-md leading-relaxed">
                  Verify your email to unlock the full power of enterprise SAS-to-Python migration.
                </p>
              </motion.div>

              <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }} className="space-y-3">
                {[
                  { icon: ShieldCheck, text: "Secure your account with verified identity" },
                  { icon: Inbox, text: "Receive pipeline status & completion alerts" },
                  { icon: Star, text: "Unlock knowledge base contributions" },
                ].map((item, i) => (
                  <motion.div
                    key={item.text}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.6 + i * 0.1 }}
                    className="flex items-center gap-3 p-3.5 rounded-xl bg-white/[0.03] border border-white/[0.06] backdrop-blur-sm"
                  >
                    <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center flex-shrink-0">
                      <item.icon className="w-4 h-4 text-accent" />
                    </div>
                    <span className="text-sm text-white/60">{item.text}</span>
                  </motion.div>
                ))}
              </motion.div>
            </div>

            <div className="flex items-center gap-8 text-white/25 text-xs font-medium">
              <span>Encrypted</span>
              <span className="w-1 h-1 rounded-full bg-white/20" />
              <span>GDPR Compliant</span>
              <span className="w-1 h-1 rounded-full bg-white/20" />
              <span>No Spam</span>
            </div>
          </div>
        </div>

        {/* Right — verification message */}
        <div className="flex-1 flex items-center justify-center p-6 lg:p-12">
          <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="w-full max-w-md space-y-8">
            <div className="lg:hidden mb-8">
              <CodaraLogo size="lg" />
            </div>

            {/* Email icon with animated ring */}
            <div className="flex justify-center">
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", stiffness: 200, damping: 15 }}
                className="relative"
              >
                <div className="absolute inset-0 rounded-full bg-accent/10 animate-ping" style={{ animationDuration: "3s" }} />
                <div className="relative w-20 h-20 rounded-full bg-gradient-to-br from-accent/20 via-accent/10 to-transparent border border-accent/20 flex items-center justify-center">
                  <Mail className="w-9 h-9 text-accent" />
                </div>
              </motion.div>
            </div>

            {/* Heading */}
            <div className="text-center">
              <h1 className="text-2xl font-bold text-foreground">Check your inbox</h1>
              <p className="text-sm text-muted-foreground mt-2 leading-relaxed">
                We sent a verification link to
              </p>
              <p className="text-sm font-semibold text-foreground mt-1 bg-muted/50 border border-border rounded-lg px-4 py-2 inline-block">
                {email}
              </p>
            </div>

            {/* Steps card */}
            <div className="rounded-xl border border-border bg-card/50 p-5 space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-7 h-7 rounded-full bg-accent/10 flex items-center justify-center text-[11px] font-bold text-accent">1</div>
                <span className="text-sm text-foreground">Open the email from <span className="font-medium text-accent">Codara</span></span>
              </div>
              <div className="ml-3.5 border-l border-border/50 h-3" />
              <div className="flex items-center gap-3">
                <div className="w-7 h-7 rounded-full bg-accent/10 flex items-center justify-center text-[11px] font-bold text-accent">2</div>
                <span className="text-sm text-foreground">Click <span className="font-medium">"Verify Email Address"</span></span>
              </div>
              <div className="ml-3.5 border-l border-border/50 h-3" />
              <div className="flex items-center gap-3">
                <div className="w-7 h-7 rounded-full bg-muted flex items-center justify-center text-[11px] font-bold text-muted-foreground">3</div>
                <span className="text-sm text-muted-foreground">Start converting SAS to Python</span>
              </div>
            </div>

            {/* Actions */}
            <div className="space-y-3">
              <Button
                onClick={() => navigate("/dashboard")}
                className="w-full py-6 text-sm font-semibold bg-gradient-to-r from-accent to-accent/80 text-accent-foreground hover:opacity-90 transition-opacity glow-accent cursor-pointer"
              >
                Continue to Dashboard
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>

              <div className="flex items-center justify-between px-1">
                <button
                  onClick={handleResend}
                  disabled={resendLoading || resendDone}
                  className="text-xs text-muted-foreground hover:text-accent transition-colors flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                >
                  {resendLoading ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : resendDone ? (
                    <CheckCircle className="w-3 h-3 text-success" />
                  ) : (
                    <RefreshCw className="w-3 h-3" />
                  )}
                  {resendDone ? "Email sent" : "Resend email"}
                </button>
                <div className="flex items-center gap-1 text-xs text-muted-foreground/50">
                  <Clock className="w-3 h-3" />
                  <span>Expires in 24h</span>
                </div>
              </div>
            </div>

            {/* Help text */}
            <div className="rounded-lg bg-muted/30 border border-border/50 px-4 py-3">
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                Can't find the email? Check your spam or junk folder. The email is sent from <span className="font-medium text-foreground/70">noreply@codara.dev</span>
              </p>
            </div>

            <p className="text-center text-xs text-muted-foreground">
              Wrong email? <Link to="/signup" onClick={() => setNeedsVerification(false)} className="text-accent font-medium hover:underline">Use a different address</Link>
            </p>
          </motion.div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex">
      {/* Left - Premium Branding */}
      <div className="hidden lg:flex lg:w-[52%] relative overflow-hidden">
        {/* Deep gradient */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_right,hsl(270,55%,15%)_0%,hsl(245,40%,8%)_50%,hsl(230,30%,5%)_100%)]" />
        
        {/* Animated mesh */}
        <div className="absolute inset-0">
          <div className="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] bg-[radial-gradient(circle,hsl(270,60%,30%,0.35)_0%,transparent_70%)] blur-3xl animate-pulse" style={{ animationDuration: "5s" }} />
          <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-[radial-gradient(circle,hsl(38,92%,50%,0.12)_0%,transparent_70%)] blur-3xl animate-pulse" style={{ animationDuration: "7s", animationDelay: "1.5s" }} />
        </div>

        {/* Grid */}
        <div className="absolute inset-0 opacity-[0.03]" style={{
          backgroundImage: `linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)`,
          backgroundSize: "80px 80px"
        }} />

        <div className="absolute top-0 right-0 w-px h-full bg-gradient-to-b from-transparent via-accent/20 to-transparent" />

        <div className="relative z-10 flex flex-col justify-between p-12 w-full">
          <CodaraLogo size="lg" variant="light" />

          <div className="space-y-10">
            <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15, duration: 0.6 }}>
              <h2 className="text-5xl font-extrabold text-white leading-[1.1] tracking-tight">
                Start converting
                <br />
                <span className="bg-gradient-to-r from-accent via-amber-400 to-orange-400 bg-clip-text text-transparent">
                  in minutes
                </span>
              </h2>
              <p className="text-white/40 text-lg mt-5 max-w-md leading-relaxed">
                Join hundreds of enterprise teams shipping production-ready Python from legacy SAS.
              </p>
            </motion.div>

            {/* Steps */}
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }} className="space-y-3">
              {[
                { step: "01", text: "Upload your SAS programs" },
                { step: "02", text: "AI pipeline analyzes & converts" },
                { step: "03", text: "Review side-by-side diffs" },
                { step: "04", text: "Export production-ready Python" },
              ].map((item, i) => (
                <motion.div
                  key={item.step}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.5 + i * 0.08 }}
                  className="flex items-center gap-4 group"
                >
                  <span className="text-[11px] font-mono font-bold text-accent/60 w-6">{item.step}</span>
                  <div className="h-px flex-1 max-w-[20px] bg-white/10 group-hover:bg-accent/30 transition-colors" />
                  <span className="text-sm text-white/60 group-hover:text-white/80 transition-colors">{item.text}</span>
                </motion.div>
              ))}
            </motion.div>

            {/* Highlights */}
            <div className="space-y-3 max-w-md">
              {HIGHLIGHTS.map((h, i) => (
                <motion.div key={h.title} initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.8 + i * 0.15 }} className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-4 backdrop-blur-sm">
                  <div className="flex items-start gap-3">
                    <span className="text-lg mt-0.5">{h.icon}</span>
                    <div>
                      <p className="text-xs font-semibold text-white/80">{h.title}</p>
                      <p className="text-[11px] text-white/40 leading-relaxed mt-0.5">{h.desc}</p>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-8 text-white/25 text-xs font-medium">
            <span>Free tier available</span>
            <span className="w-1 h-1 rounded-full bg-white/20" />
            <span>No credit card required</span>
            <span className="w-1 h-1 rounded-full bg-white/20" />
            <span>Cancel anytime</span>
          </div>
        </div>
      </div>

      {/* Right - Signup Form */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12">
        <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="w-full max-w-md space-y-8">
          <div className="lg:hidden mb-8">
            <CodaraLogo size="lg" />
          </div>

          <div>
            <h1 className="text-2xl font-bold text-foreground">Create your account</h1>
            <p className="text-sm text-muted-foreground mt-1">Get started with Codara in seconds</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <motion.div initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }} className="text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2.5">
                {error}
              </motion.div>
            )}

            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1.5">Full name</label>
              <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Sarah Chen" className="w-full bg-muted/30 border border-border rounded-lg px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20 transition-all" />
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1.5">Work email</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" className="w-full bg-muted/30 border border-border rounded-lg px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20 transition-all" />
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1.5">Password</label>
              <div className="relative">
                <input type={showPassword ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Create a strong password" className="w-full bg-muted/30 border border-border rounded-lg px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20 transition-all pr-10" />
                <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors">
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {password && (
                <div className="flex items-center gap-3 mt-2">
                  {passwordChecks.map((check) => (
                    <div key={check.label} className="flex items-center gap-1">
                      <CheckCircle className={`w-3 h-3 ${check.valid ? "text-success" : "text-muted-foreground/40"}`} />
                      <span className={`text-[10px] ${check.valid ? "text-success" : "text-muted-foreground/40"}`}>{check.label}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <Button type="submit" disabled={isLoading} className="w-full py-6 text-sm font-semibold bg-gradient-to-r from-accent to-accent/80 text-accent-foreground hover:opacity-90 transition-opacity glow-accent">
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Create Account"}
            </Button>

            <p className="text-[10px] text-muted-foreground text-center leading-relaxed">
              By signing up, you agree to our Terms of Service and Privacy Policy
            </p>
          </form>

          <div className="relative">
            <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-border" /></div>
            <div className="relative flex justify-center text-xs"><span className="bg-background px-3 text-muted-foreground">or continue with</span></div>
          </div>

          <div className="grid grid-cols-1 gap-3">
            <button
              onClick={handleGitHubSignup}
              disabled={isLoading}
              className="flex items-center justify-center gap-2 py-2.5 rounded-lg border border-border hover:bg-muted/30 transition-colors text-sm text-muted-foreground hover:text-foreground"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
              Continue with GitHub
            </button>
          </div>

          <p className="text-center text-xs text-muted-foreground">
            Already have an account? <Link to="/login" className="text-accent font-medium hover:underline">Sign in</Link>
          </p>
        </motion.div>
      </div>
    </div>
  );
}
