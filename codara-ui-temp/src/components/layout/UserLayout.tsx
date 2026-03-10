import { Link, useLocation, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { CodaraLogo } from "@/components/CodaraLogo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useUserStore } from "@/store/user-store";
import { Outlet } from "react-router-dom";
import {
  LayoutDashboard, FileCode, FolderOpen, History, BookOpen,
  BarChart3, Settings, LogOut, Bell, Menu, X
} from "lucide-react";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

const userNav = [
  { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
  { label: "Conversions", path: "/conversions", icon: FileCode },
  { label: "Workspace", path: "/workspace", icon: FolderOpen },
  { label: "History", path: "/history", icon: History },
  { label: "Knowledge Base", path: "/knowledge-base", icon: BookOpen },
  { label: "Analytics", path: "/analytics", icon: BarChart3 },
];

export function UserLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { currentUser, logout } = useUserStore();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Top Navigation */}
      <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-xl">
        <div className="max-w-[1400px] mx-auto flex items-center justify-between h-16 px-6">
          {/* Left: Logo + Nav */}
          <div className="flex items-center gap-8">
            <Link to="/dashboard">
              <CodaraLogo size="md" />
            </Link>

            {/* Desktop Nav */}
            <nav className="hidden lg:flex items-center gap-1">
              {userNav.map((item) => {
                const active = location.pathname === item.path || location.pathname.startsWith(item.path + "/");
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={cn(
                      "flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all duration-200",
                      active
                        ? "bg-accent/10 text-accent"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                    )}
                  >
                    <item.icon className="w-4 h-4" />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>

          {/* Right: Actions */}
          <div className="flex items-center gap-2">
            <ThemeToggle />

            <button className="relative p-2 rounded-lg hover:bg-muted/50 transition-colors text-muted-foreground hover:text-foreground">
              <Bell className="w-4 h-4" />
              <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-accent" />
            </button>

            <Link to="/settings" className="p-2 rounded-lg hover:bg-muted/50 transition-colors text-muted-foreground hover:text-foreground">
              <Settings className="w-4 h-4" />
            </Link>

            {/* Profile */}
            <div className="relative ml-1">
              <button
                onClick={() => setProfileOpen(!profileOpen)}
                className="flex items-center gap-2.5 pl-3 pr-2 py-1.5 rounded-xl hover:bg-muted/50 transition-colors"
              >
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-accent to-secondary flex items-center justify-center text-xs font-bold text-accent-foreground">
                  {currentUser?.name?.charAt(0) || "U"}
                </div>
                <div className="hidden md:block text-left">
                  <p className="text-sm font-medium text-foreground leading-tight">{currentUser?.name || "User"}</p>
                  <p className="text-[10px] text-muted-foreground leading-tight">{currentUser?.email}</p>
                </div>
              </button>

              <AnimatePresence>
                {profileOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 4, scale: 0.97 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 4, scale: 0.97 }}
                    transition={{ duration: 0.15 }}
                    className="absolute right-0 top-full mt-2 w-56 glass-panel-strong p-2 shadow-xl z-50"
                  >
                    <div className="px-3 py-2 border-b border-border mb-1">
                      <p className="text-sm font-medium text-foreground">{currentUser?.name}</p>
                      <p className="text-xs text-muted-foreground">{currentUser?.email}</p>
                    </div>
                    <Link
                      to="/settings"
                      onClick={() => setProfileOpen(false)}
                      className="flex items-center gap-2.5 px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-lg transition-colors"
                    >
                      <Settings className="w-3.5 h-3.5" /> Settings
                    </Link>
                    <button
                      onClick={handleLogout}
                      className="flex items-center gap-2.5 px-3 py-2 text-sm text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors w-full"
                    >
                      <LogOut className="w-3.5 h-3.5" /> Sign out
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Mobile Menu Toggle */}
            <button
              className="lg:hidden p-2 rounded-lg hover:bg-muted/50 text-muted-foreground"
              onClick={() => setMobileOpen(!mobileOpen)}
            >
              {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {/* Mobile Nav */}
        <AnimatePresence>
          {mobileOpen && (
            <motion.nav
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="lg:hidden border-t border-border overflow-hidden"
            >
              <div className="p-4 space-y-1">
                {userNav.map((item) => {
                  const active = location.pathname === item.path;
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      onClick={() => setMobileOpen(false)}
                      className={cn(
                        "flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors",
                        active
                          ? "bg-accent/10 text-accent"
                          : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                      )}
                    >
                      <item.icon className="w-4 h-4" />
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </motion.nav>
          )}
        </AnimatePresence>
      </header>

      {/* Main Content */}
      <main className="max-w-[1400px] mx-auto px-6 py-6">
        <Outlet />
      </main>
    </div>
  );
}