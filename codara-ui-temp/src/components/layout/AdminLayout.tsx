import { Link, useLocation, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { CodaraLogo } from "@/components/CodaraLogo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useUserStore } from "@/store/user-store";
import { Outlet } from "react-router-dom";
import {
  LayoutDashboard, FileCode, FolderOpen, History, BookOpen,
  BarChart3, Shield, Settings, ChevronLeft, LogOut, Bell, Circle,
  Activity, Users, Database, Workflow, FileSearch, BookMarked
} from "lucide-react";
import { useState } from "react";

const adminNavItems = [
  { label: "Overview", path: "/dashboard", icon: LayoutDashboard },
  { label: "Audit Logs", path: "/admin/audit-logs", icon: FileCode },
  { label: "System Health", path: "/admin/system-health", icon: Activity },
  { label: "Users", path: "/admin/users", icon: Users },
  { label: "Pipeline Config", path: "/admin/pipeline-config", icon: Workflow },
  { label: "File Registry", path: "/admin/file-registry", icon: FileSearch },
  { label: "KB Management", path: "/admin/kb-management", icon: BookMarked },
  { label: "KB Changelog", path: "/admin/kb-changelog", icon: History },
];

const platformNavItems = [
  { label: "Conversions", path: "/conversions", icon: FileCode },
  { label: "Workspace", path: "/workspace", icon: FolderOpen },
  { label: "History", path: "/history", icon: History },
  { label: "Knowledge Base", path: "/knowledge-base", icon: BookOpen },
  { label: "Analytics", path: "/analytics", icon: BarChart3 },
];

export function AdminLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const { currentUser, logout } = useUserStore();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const renderNavItem = (item: { label: string; path: string; icon: any }) => {
    const active = location.pathname === item.path || location.pathname.startsWith(item.path + "/");
    return (
      <Link
        key={item.path}
        to={item.path}
        className={cn(
          "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all duration-200",
          active
            ? "bg-sidebar-accent text-accent font-medium"
            : "text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-foreground"
        )}
      >
        <item.icon className={cn("w-4 h-4 flex-shrink-0", active && "text-accent")} />
        {!collapsed && <span>{item.label}</span>}
      </Link>
    );
  };

  return (
    <div className="min-h-screen bg-background flex">
      {/* Sidebar */}
      <aside
        className={cn(
          "fixed left-0 top-0 h-screen flex flex-col border-r border-sidebar-border bg-sidebar z-50 transition-all duration-300",
          collapsed ? "w-16" : "w-60"
        )}
      >
        {/* Logo */}
        <div className="flex items-center h-16 border-b border-sidebar-border px-3">
          {collapsed ? (
            <CodaraLogo size="sm" showText={false} className="mx-auto" />
          ) : (
            <div className="flex items-center gap-2 px-1">
              <CodaraLogo size="md" />
              {!collapsed && (
                <span className="text-[9px] font-semibold uppercase tracking-widest text-accent bg-accent/10 px-1.5 py-0.5 rounded">
                  Admin
                </span>
              )}
            </div>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
          <div className={cn("mb-2", !collapsed && "px-2")}>
            {!collapsed && (
              <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                Administration
              </span>
            )}
          </div>
          {adminNavItems.map(renderNavItem)}

          <div className={cn("mt-6 mb-2", !collapsed && "px-2")}>
            {!collapsed && (
              <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                Platform
              </span>
            )}
          </div>
          {platformNavItems.map(renderNavItem)}

          <div className={cn("mt-6 mb-2", !collapsed && "px-2")}>
            {!collapsed && (
              <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                System
              </span>
            )}
          </div>
          {renderNavItem({ label: "Settings", path: "/settings", icon: Settings })}
        </nav>

        {/* User + Logout */}
        <div className="border-t border-sidebar-border">
          {!collapsed && (
            <div className="px-4 py-3 flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-accent to-secondary flex items-center justify-center text-xs font-bold text-accent-foreground">
                {currentUser?.name?.charAt(0) || "A"}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground truncate">{currentUser?.name}</p>
                <p className="text-[10px] text-muted-foreground truncate">{currentUser?.email}</p>
              </div>
            </div>
          )}
          <button
            onClick={handleLogout}
            className={cn(
              "flex items-center gap-3 w-full px-5 py-2.5 text-sm text-muted-foreground hover:text-destructive transition-colors",
              collapsed && "justify-center px-0"
            )}
          >
            <LogOut className="w-4 h-4 flex-shrink-0" />
            {!collapsed && <span>Sign out</span>}
          </button>
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="flex items-center justify-center w-full h-10 text-muted-foreground hover:text-foreground transition-colors"
          >
            <ChevronLeft className={cn("w-4 h-4 transition-transform", collapsed && "rotate-180")} />
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className={cn("flex-1 flex flex-col transition-all duration-300", collapsed ? "ml-16" : "ml-60")}>
        {/* Top bar */}
        <header className="h-14 border-b border-border bg-card/40 backdrop-blur-xl flex items-center justify-between px-6 sticky top-0 z-40">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Circle className="w-2 h-2 fill-success text-success" />
            <span>All systems operational</span>
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <button className="relative p-2 rounded-lg hover:bg-muted/50 transition-colors text-muted-foreground hover:text-foreground">
              <Bell className="w-4 h-4" />
              <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-accent" />
            </button>
          </div>
        </header>

        <main className="flex-1 p-6 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}