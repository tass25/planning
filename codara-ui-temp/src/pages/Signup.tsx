import { useState } from "react";
import { useUserStore } from "@/store/user-store";
import { useNavigate, Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { CodaraLogo } from "@/components/CodaraLogo";
import { Loader2, Eye, EyeOff, CheckCircle, ArrowRight, Star } from "lucide-react";
import { motion } from "framer-motion";

const TESTIMONIALS = [
  { name: "Sarah Chen", role: "VP Engineering, Meridian Health", quote: "Codara cut our SAS migration timeline from 18 months to 6 weeks. The accuracy is remarkable." },
  { name: "Marcus Webb", role: "CTO, DataFirst Analytics", quote: "We migrated 2,400 SAS programs with 98.1% accuracy. The ROI was immediate." },
];

export default function SignupPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const { signup, isLoading } = useUserStore();
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
    const success = await signup(email, password, name);
    if (success) navigate("/dashboard");
    else setError("Signup failed");
  };

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

            {/* Testimonial */}
            <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.8 }} className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-5 max-w-md backdrop-blur-sm">
              <div className="flex gap-0.5 mb-3">
                {[...Array(5)].map((_, i) => (
                  <Star key={i} className="w-3.5 h-3.5 fill-accent text-accent" />
                ))}
              </div>
              <p className="text-sm text-white/60 italic leading-relaxed">"{TESTIMONIALS[0].quote}"</p>
              <div className="mt-3 flex items-center gap-2">
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-accent/30 to-secondary/30 flex items-center justify-center text-[10px] font-bold text-white/80">
                  {TESTIMONIALS[0].name.charAt(0)}
                </div>
                <div>
                  <p className="text-xs font-medium text-white/70">{TESTIMONIALS[0].name}</p>
                  <p className="text-[10px] text-white/30">{TESTIMONIALS[0].role}</p>
                </div>
              </div>
            </motion.div>
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

          <div className="grid grid-cols-2 gap-3">
            <button className="flex items-center justify-center gap-2 py-2.5 rounded-lg border border-border hover:bg-muted/30 transition-colors text-sm text-muted-foreground hover:text-foreground">
              <svg className="w-4 h-4" viewBox="0 0 24 24"><path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/><path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
              Google
            </button>
            <button className="flex items-center justify-center gap-2 py-2.5 rounded-lg border border-border hover:bg-muted/30 transition-colors text-sm text-muted-foreground hover:text-foreground">
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
              GitHub
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
