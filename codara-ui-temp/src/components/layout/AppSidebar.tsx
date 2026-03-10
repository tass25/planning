import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, FileCode, FolderOpen, History, BookOpen,
  BarChart3, Shield, Settings, ChevronLeft, LogOut
} from "lucide-react";
import { useState } from "react";
import { CodaraLogo } from "@/components/CodaraLogo";
import { useUserStore } from "@/store/user-store";
import { useNavigate } from "react-router-dom";

const userNavItems = [
  { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
  { label: "Conversions", path: "/conversions", icon: FileCode },
  { label: "Workspace", path: "/workspace", icon: FolderOpen },
  { label: "History", path: "/history", icon: History },
  { label: "Knowledge Base", path: "/knowledge-base", icon: BookOpen },
  { label: "Analytics", path: "/analytics", icon: BarChart3 },
];

const adminNavItems = [
  { label: "Admin Overview", path: "/admin", icon: Shield },
  { label: "Audit Logs", path: "/admin/audit-logs", icon: FileCode },
  { label: "System Health", path: "/admin/system-health", icon: LayoutDashboard },
  { label: "Users", path: "/admin/users", icon: BarChart3 },
  { label: "Pipeline Config", path: "/admin/pipeline-config", icon: FolderOpen },
  { label: "File Registry", path: "/admin/file-registry", icon: History },
  { label: "KB Management", path: "/admin/kb-management", icon: BookOpen },
  { label: "KB Changelog", path: "/admin/kb-changelog", icon: History },
];

export function AppSidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const { currentUser, logout } = useUserStore();
  const isAdmin = currentUser?.role === "admin";

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
    <aside
      className={cn(
        "fixed left-0 top-0 h-screen flex flex-col border-r border-sidebar-border bg-sidebar z-50 transition-all duration-300",
        collapsed ? "w-16" : "w-60"
      )}
    >
      <div className="flex items-center h-16 border-b border-sidebar-border px-3">
        {collapsed ? (
          <CodaraLogo size="sm" showText={false} className="mx-auto" />
        ) : (
          <CodaraLogo size="md" className="px-1" />
        )}
      </div>

      <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
        <div className={cn("mb-2", !collapsed && "px-2")}>
          {!collapsed && <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Platform</span>}
        </div>
        {userNavItems.map(renderNavItem)}

        {isAdmin && (
          <>
            <div className={cn("mt-6 mb-2", !collapsed && "px-2")}>
              {!collapsed && <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Admin</span>}
            </div>
            {adminNavItems.map(renderNavItem)}
          </>
        )}

        <div className={cn("mt-6 mb-2", !collapsed && "px-2")}>
          {!collapsed && <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">System</span>}
        </div>
        {renderNavItem({ label: "Settings", path: "/settings", icon: Settings })}
      </nav>

      {/* Logout & Collapse */}
      <div className="border-t border-sidebar-border">
        <button
          onClick={handleLogout}
          className={cn(
            "flex items-center gap-3 w-full px-5 py-3 text-sm text-muted-foreground hover:text-destructive transition-colors",
            collapsed && "justify-center px-0"
          )}
        >
          <LogOut className="w-4 h-4 flex-shrink-0" />
          {!collapsed && <span>Logout</span>}
        </button>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center justify-center w-full h-10 text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className={cn("w-4 h-4 transition-transform", collapsed && "rotate-180")} />
        </button>
      </div>
    </aside>
  );
}