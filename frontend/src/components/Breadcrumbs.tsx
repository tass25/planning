import { Link, useLocation } from "react-router-dom";
import { ChevronRight, Home } from "lucide-react";

const LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  projects: "Projects",
  conversions: "Conversions",
  workspace: "Workspace",
  history: "History",
  "knowledge-base": "Knowledge Base",
  analytics: "Analytics",
  settings: "Settings",
  admin: "Admin",
  "audit-logs": "Audit Logs",
  "system-health": "System Health",
  users: "Users",
  "pipeline-config": "Pipeline Config",
  "file-registry": "File Registry",
  "kb-management": "KB Management",
  "kb-changelog": "KB Changelog",
  "prompt-templates": "Prompt Templates",
};

export function Breadcrumbs() {
  const { pathname } = useLocation();
  const segments = pathname.split("/").filter(Boolean);

  if (segments.length <= 1) return null;

  const crumbs = segments.map((seg, i) => {
    const path = "/" + segments.slice(0, i + 1).join("/");
    const label = LABELS[seg] || (seg.length > 12 ? seg.slice(0, 12) + "..." : seg);
    const isLast = i === segments.length - 1;
    return { label, path, isLast };
  });

  return (
    <nav className="flex items-center gap-1.5 text-xs text-muted-foreground mb-4">
      <Link to="/dashboard" className="hover:text-foreground transition-colors">
        <Home className="w-3.5 h-3.5" />
      </Link>
      {crumbs.map((c) => (
        <span key={c.path} className="flex items-center gap-1.5">
          <ChevronRight className="w-3 h-3 text-muted-foreground/40" />
          {c.isLast ? (
            <span className="text-foreground font-medium">{c.label}</span>
          ) : (
            <Link to={c.path} className="hover:text-foreground transition-colors">{c.label}</Link>
          )}
        </span>
      ))}
    </nav>
  );
}
