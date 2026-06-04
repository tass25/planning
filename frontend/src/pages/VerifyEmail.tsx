import { useEffect, useState } from "react";
import { useSearchParams, Link, useNavigate } from "react-router-dom";
import { useUserStore } from "@/store/user-store";
import { CodaraLogo } from "@/components/CodaraLogo";
import { motion } from "framer-motion";
import { CheckCircle2, XCircle, Loader2, ArrowRight, Shield, Zap, BarChart3, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";

type VerifyState = "verifying" | "success" | "error" | "pending";

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const { verifyEmail, resendVerification, isAuthenticated, currentUser } = useUserStore();
  const navigate = useNavigate();
  const [state, setState] = useState<VerifyState>(token ? "verifying" : "pending");
  const [resendLoading, setResendLoading] = useState(false);
  const [resendDone, setResendDone] = useState(false);

  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    verifyEmail(token).then((ok) => {
      if (cancelled) return;
      if (ok) {
        setState("success");
        setTimeout(() => navigate("/dashboard", { replace: true }), 2000);
      } else {
        setState("error");
      }
    });
    return () => { cancelled = true; };
  }, [token, verifyEmail, navigate]);

  const handleResend = async () => {
    setResendLoading(true);
    await resendVerification();
    setResendLoading(false);
    setResendDone(true);
  };

  const brandingPanel = (
    <div className="hidden lg:flex lg:w-[52%] relative overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,hsl(270,55%,15%)_0%,hsl(245,40%,8%)_50%,hsl(230,30%,5%)_100%)]" />
      <div className="absolute inset-0">
        <div className="absolute top-[10%] left-[10%] w-[50%] h-[50%] bg-[radial-gradient(circle,hsl(152,60%,38%,0.15)_0%,transparent_70%)] blur-3xl animate-pulse" style={{ animationDuration: "5s" }} />
        <div className="absolute bottom-[10%] right-[10%] w-[40%] h-[40%] bg-[radial-gradient(circle,hsl(38,92%,50%,0.12)_0%,transparent_70%)] blur-3xl animate-pulse" style={{ animationDuration: "7s", animationDelay: "1s" }} />
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
            <h2 className="text-4xl font-extrabold text-white leading-[1.1] tracking-tight">
              Your account is
              <br />
              <span className="bg-gradient-to-r from-emerald-400 via-accent to-amber-400 bg-clip-text text-transparent">
                almost ready
              </span>
            </h2>
            <p className="text-white/40 text-lg mt-5 max-w-md leading-relaxed">
              One step away from converting legacy SAS code into production-ready Python.
            </p>
          </motion.div>

          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }} className="space-y-4">
            {[
              { icon: Shield, label: "Enterprise-grade security", desc: "SOC2 compliant with full audit logging" },
              { icon: Zap, label: "8-stage AI pipeline", desc: "Multi-pass translation with formal verification" },
              { icon: BarChart3, label: "97.3% accuracy", desc: "Validated across 10,000+ SAS programs" },
            ].map((item, i) => (
              <motion.div
                key={item.label}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.5 + i * 0.1 }}
                className="flex items-start gap-4 p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] backdrop-blur-sm"
              >
                <div className="w-9 h-9 rounded-lg bg-accent/10 flex items-center justify-center flex-shrink-0">
                  <item.icon className="w-4.5 h-4.5 text-accent" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white/85">{item.label}</p>
                  <p className="text-xs text-white/35 mt-0.5">{item.desc}</p>
                </div>
              </motion.div>
            ))}
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
  );

  return (
    <div className="min-h-screen bg-background flex">
      {brandingPanel}

      <div className="flex-1 flex items-center justify-center p-6 lg:p-12">
        <div className="w-full max-w-md">
          <div className="lg:hidden mb-10">
            <CodaraLogo size="lg" />
          </div>

          {state === "pending" && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-8">
              <div className="text-center space-y-5">
                <div className="relative w-20 h-20 mx-auto">
                  <div className="absolute inset-0 rounded-full bg-accent/10 animate-pulse" style={{ animationDuration: "3s" }} />
                  <div className="relative w-20 h-20 rounded-full bg-gradient-to-br from-accent/20 to-accent/5 border border-accent/20 flex items-center justify-center">
                    <Mail className="w-9 h-9 text-accent" />
                  </div>
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-foreground">Check your email</h1>
                  <p className="text-sm text-muted-foreground mt-2 leading-relaxed max-w-sm mx-auto">
                    We sent a verification link to{" "}
                    {currentUser?.email ? (
                      <span className="font-semibold text-foreground">{currentUser.email}</span>
                    ) : (
                      "your email address"
                    )}
                    . Click the link to activate your account.
                  </p>
                </div>
              </div>

              <div className="rounded-xl border border-border bg-card/50 p-5 space-y-3">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Didn't receive it?</p>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex items-start gap-2">
                    <span className="text-accent mt-0.5">&#8226;</span>
                    Check your spam or junk folder
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-accent mt-0.5">&#8226;</span>
                    Make sure your email address is correct
                  </li>
                </ul>
              </div>

              {isAuthenticated && (
                <Button
                  onClick={handleResend}
                  disabled={resendLoading || resendDone}
                  variant="outline"
                  className="w-full py-5 text-sm font-medium cursor-pointer"
                >
                  {resendDone ? "Verification email sent!" : resendLoading ? "Sending..." : "Resend verification email"}
                </Button>
              )}

              <Button
                onClick={() => navigate("/login")}
                variant="ghost"
                className="w-full py-5 text-sm font-medium text-muted-foreground cursor-pointer"
              >
                Back to Sign In
              </Button>
            </motion.div>
          )}

          {state === "verifying" && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="text-center space-y-6">
              <div className="relative w-20 h-20 mx-auto">
                <div className="absolute inset-0 rounded-full bg-accent/10 animate-ping" style={{ animationDuration: "2s" }} />
                <div className="relative w-20 h-20 rounded-full bg-gradient-to-br from-accent/20 to-accent/5 border border-accent/20 flex items-center justify-center">
                  <Loader2 className="w-8 h-8 text-accent animate-spin" />
                </div>
              </div>
              <div>
                <h1 className="text-2xl font-bold text-foreground">Verifying your email</h1>
                <p className="text-sm text-muted-foreground mt-2 leading-relaxed">
                  Please wait while we confirm your email address...
                </p>
              </div>
              <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground/60">
                <div className="w-1.5 h-1.5 rounded-full bg-accent/40 animate-pulse" />
                <span>Secure verification in progress</span>
              </div>
            </motion.div>
          )}

          {state === "success" && (
            <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4 }} className="space-y-8">
              <div className="text-center space-y-5">
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: "spring", stiffness: 200, damping: 15, delay: 0.1 }}
                  className="relative w-20 h-20 mx-auto"
                >
                  <div className="absolute inset-0 rounded-full bg-success/10 animate-pulse" style={{ animationDuration: "3s" }} />
                  <div className="relative w-20 h-20 rounded-full bg-gradient-to-br from-success/20 to-success/5 border border-success/20 flex items-center justify-center">
                    <CheckCircle2 className="w-9 h-9 text-success" />
                  </div>
                </motion.div>
                <div>
                  <h1 className="text-2xl font-bold text-foreground">Email verified</h1>
                  <p className="text-sm text-muted-foreground mt-2 leading-relaxed max-w-sm mx-auto">
                    Your account is fully activated. Redirecting to your dashboard...
                  </p>
                </div>
              </div>

              <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground/60">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Redirecting...</span>
              </div>

              <Button
                onClick={() => navigate("/dashboard", { replace: true })}
                className="w-full py-6 text-sm font-semibold bg-gradient-to-r from-accent to-accent/80 text-accent-foreground hover:opacity-90 transition-opacity glow-accent cursor-pointer"
              >
                Go to Dashboard
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </motion.div>
          )}

          {state === "error" && (
            <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="space-y-8">
              <div className="text-center space-y-5">
                <div className="relative w-20 h-20 mx-auto">
                  <div className="absolute inset-0 rounded-full bg-destructive/10" />
                  <div className="relative w-20 h-20 rounded-full bg-gradient-to-br from-destructive/20 to-destructive/5 border border-destructive/20 flex items-center justify-center">
                    <XCircle className="w-9 h-9 text-destructive" />
                  </div>
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-foreground">Verification failed</h1>
                  <p className="text-sm text-muted-foreground mt-2 leading-relaxed max-w-sm mx-auto">
                    This link is invalid or has already been used. Verification links are single-use and expire after 24 hours.
                  </p>
                </div>
              </div>

              <div className="rounded-xl border border-border bg-card/50 p-5 space-y-3">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Troubleshooting</p>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex items-start gap-2">
                    <span className="text-accent mt-0.5">&#8226;</span>
                    Check that you clicked the most recent verification email
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-accent mt-0.5">&#8226;</span>
                    Links expire after 24 hours — request a new one below
                  </li>
                </ul>
              </div>

              <div className="flex gap-3">
                <Button
                  onClick={() => navigate("/login")}
                  variant="outline"
                  className="flex-1 py-5 text-sm font-medium cursor-pointer"
                >
                  Sign In
                </Button>
                <Button
                  onClick={() => navigate("/signup")}
                  className="flex-1 py-5 text-sm font-semibold bg-gradient-to-r from-accent to-accent/80 text-accent-foreground hover:opacity-90 transition-opacity cursor-pointer"
                >
                  Create Account
                </Button>
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}
