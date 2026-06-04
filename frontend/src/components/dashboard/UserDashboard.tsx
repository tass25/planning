import { useConversionStore } from "@/store/conversion-store";
import { useUserStore } from "@/store/user-store";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  Upload, FolderOpen, BookOpen, ArrowRight, FileCode,
  Sparkles, Rocket, CheckCircle2, Clock3, FileUp
} from "lucide-react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { OnboardingTour } from "@/components/OnboardingTour";

const fadeUp = (delay = 0) => ({
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.4, delay },
});

export default function UserDashboard() {
  const conversions = useConversionStore((s) => s.conversions);
  const user = useUserStore((s) => s.currentUser);
  const total = conversions.length;
  const completed = conversions.filter((c) => c.status === "completed").length;
  const running = conversions.filter((c) => c.status === "running").length;

  const greeting =
    new Date().getHours() < 12
      ? "Good morning"
      : new Date().getHours() < 18
      ? "Good afternoon"
      : "Good evening";

  const steps = [
    {
      step: 1,
      title: "Upload SAS files",
      desc: "Drag & drop your .sas files or browse from your machine",
      icon: FileUp,
      color: "accent" as const,
      link: "/conversions",
    },
    {
      step: 2,
      title: "Review in Workspace",
      desc: "Compare SAS → Python side-by-side with highlighted diffs",
      icon: FolderOpen,
      color: "secondary" as const,
      link: "/workspace",
    },
    {
      step: 3,
      title: "Export & Integrate",
      desc: "Download converted Python files ready for production",
      icon: Rocket,
      color: "success" as const,
      link: "/history",
    },
  ];

  const colorMap = {
    accent: {
      bg: "bg-accent/10",
      text: "text-accent",
      border: "border-accent/20",
      glow: "hover:glow-accent",
      ring: "ring-accent/20",
    },
    secondary: {
      bg: "bg-secondary/10",
      text: "text-secondary",
      border: "border-secondary/20",
      glow: "hover:glow-secondary",
      ring: "ring-secondary/20",
    },
    success: {
      bg: "bg-success/10",
      text: "text-success",
      border: "border-success/20",
      glow: "",
      ring: "ring-success/20",
    },
  };

  return (
    <div className="space-y-8">
      <OnboardingTour />
      {/* Hero Welcome */}
      <motion.div {...fadeUp(0)} className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-accent/10 via-secondary/5 to-transparent border border-accent/10 p-8">
        <div className="relative z-10">
          <p className="text-sm font-medium text-accent mb-1">{greeting}</p>
          <h1 className="text-3xl font-bold text-foreground">
            {user?.name?.split(" ")[0] || "there"} 👋
          </h1>
          <p className="text-muted-foreground mt-2 max-w-lg">
            Convert your SAS code to Python in minutes. Upload files, review translations, and export production-ready code.
          </p>
          <Link to="/conversions">
            <Button className="mt-5 bg-accent hover:bg-accent/90 text-accent-foreground gap-2 px-6">
              <Upload className="w-4 h-4" /> Start New Conversion
            </Button>
          </Link>
        </div>
        {/* Decorative */}
        <div className="absolute -right-10 -top-10 w-48 h-48 bg-accent/5 rounded-full blur-3xl" />
        <div className="absolute -right-5 bottom-0 w-32 h-32 bg-secondary/5 rounded-full blur-2xl" />
      </motion.div>

      {/* Quick Stats Row */}
      <motion.div {...fadeUp(0.1)} className="grid grid-cols-3 gap-4">
        <div className="glass-panel p-5 flex items-center gap-4">
          <div className="w-11 h-11 rounded-xl bg-accent/10 flex items-center justify-center">
            <FileCode className="w-5 h-5 text-accent" />
          </div>
          <div>
            <p className="text-2xl font-bold text-foreground">{total}</p>
            <p className="text-xs text-muted-foreground">Total Conversions</p>
          </div>
        </div>
        <div className="glass-panel p-5 flex items-center gap-4">
          <div className="w-11 h-11 rounded-xl bg-success/10 flex items-center justify-center">
            <CheckCircle2 className="w-5 h-5 text-success" />
          </div>
          <div>
            <p className="text-2xl font-bold text-foreground">{completed}</p>
            <p className="text-xs text-muted-foreground">Completed</p>
          </div>
        </div>
        <div className="glass-panel p-5 flex items-center gap-4">
          <div className="w-11 h-11 rounded-xl bg-secondary/10 flex items-center justify-center">
            <Clock3 className="w-5 h-5 text-secondary" />
          </div>
          <div>
            <p className="text-2xl font-bold text-foreground">{running}</p>
            <p className="text-xs text-muted-foreground">In Progress</p>
          </div>
        </div>
      </motion.div>

      {/* How It Works — Step Cards */}
      <motion.div {...fadeUp(0.2)}>
        <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-accent" /> How It Works
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {steps.map((s) => {
            const c = colorMap[s.color];
            return (
              <Link
                key={s.step}
                to={s.link}
                className={cn(
                  "glass-panel p-6 group transition-all duration-300 hover:scale-[1.02]",
                  c.glow
                )}
              >
                <div className="flex items-center gap-3 mb-3">
                  <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center", c.bg)}>
                    <s.icon className={cn("w-4 h-4", c.text)} />
                  </div>
                  <span className={cn("text-xs font-bold uppercase tracking-wider", c.text)}>
                    Step {s.step}
                  </span>
                </div>
                <h3 className="text-sm font-semibold text-foreground group-hover:text-accent transition-colors">
                  {s.title}
                </h3>
                <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">
                  {s.desc}
                </p>
              </Link>
            );
          })}
        </div>
      </motion.div>

      {/* Activity Timeline */}
      <motion.div {...fadeUp(0.3)}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-foreground">Recent Activity</h2>
          <Link to="/history" className="text-xs text-accent hover:underline flex items-center gap-1">
            View all <ArrowRight className="w-3 h-3" />
          </Link>
        </div>

        {conversions.length === 0 ? (
          <div className="glass-panel p-12 text-center">
            <Upload className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">No activity yet</p>
            <p className="text-xs text-muted-foreground/70 mt-1">Upload your first SAS file to get started</p>
            <Link to="/conversions">
              <Button variant="outline" size="sm" className="mt-4 gap-2">
                <Upload className="w-3 h-3" /> Upload Files
              </Button>
            </Link>
          </div>
        ) : (
          <div className="glass-panel p-5 space-y-0">
            {conversions.slice(0, 6).map((c, i) => {
              const statusMsg = c.status === "completed" ? `Converted with ${c.accuracy}% accuracy` :
                c.status === "running" ? "Pipeline in progress..." :
                c.status === "failed" ? "Conversion failed" :
                c.status === "partial" ? "Partial conversion" : "Queued for processing";
              const statusColor = c.status === "completed" ? "bg-success" :
                c.status === "running" ? "bg-accent animate-pulse" :
                c.status === "failed" ? "bg-destructive" : "bg-warning";
              const timeAgo = (() => {
                const diff = Date.now() - new Date(c.updatedAt || c.createdAt).getTime();
                const mins = Math.floor(diff / 60000);
                if (mins < 1) return "just now";
                if (mins < 60) return `${mins}m ago`;
                const hrs = Math.floor(mins / 60);
                if (hrs < 24) return `${hrs}h ago`;
                return `${Math.floor(hrs / 24)}d ago`;
              })();
              return (
                <Link key={c.id} to={`/workspace/${c.id}`} className="flex items-start gap-3 py-3 group relative">
                  {i < conversions.slice(0, 6).length - 1 && (
                    <div className="absolute left-[9px] top-8 bottom-0 w-px bg-border" />
                  )}
                  <div className={cn("w-[18px] h-[18px] rounded-full flex-shrink-0 mt-0.5 border-2 border-background", statusColor)} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground group-hover:text-accent transition-colors truncate">{c.fileName}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{statusMsg}</p>
                  </div>
                  <span className="text-[10px] text-muted-foreground/60 flex-shrink-0 mt-0.5">{timeAgo}</span>
                </Link>
              );
            })}
          </div>
        )}
      </motion.div>

      {/* Quick Links */}
      <motion.div {...fadeUp(0.4)} className="flex items-center gap-3">
        <Link
          to="/knowledge-base"
          className="glass-panel px-5 py-3 flex items-center gap-2.5 hover:border-accent/30 transition-colors group flex-1"
        >
          <BookOpen className="w-4 h-4 text-accent" />
          <div>
            <p className="text-sm font-medium text-foreground group-hover:text-accent transition-colors">Knowledge Base</p>
            <p className="text-[11px] text-muted-foreground">Browse SAS → Python patterns</p>
          </div>
        </Link>
        <Link
          to="/analytics"
          className="glass-panel px-5 py-3 flex items-center gap-2.5 hover:border-secondary/30 transition-colors group flex-1"
        >
          <Sparkles className="w-4 h-4 text-secondary" />
          <div>
            <p className="text-sm font-medium text-foreground group-hover:text-secondary transition-colors">My Analytics</p>
            <p className="text-[11px] text-muted-foreground">View your conversion insights</p>
          </div>
        </Link>
      </motion.div>
    </div>
  );
}
