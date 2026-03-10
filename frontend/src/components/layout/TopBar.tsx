import { Bell, Search, Circle, Check, CheckCheck, Info, AlertTriangle, AlertCircle, CheckCircle } from "lucide-react";
import { useUserStore } from "@/store/user-store";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";

const typeIcon: Record<string, typeof Info> = {
  info: Info,
  success: CheckCircle,
  warning: AlertTriangle,
  error: AlertCircle,
};
const typeColor: Record<string, string> = {
  info: "text-blue-500",
  success: "text-success",
  warning: "text-warning",
  error: "text-destructive",
};

export function TopBar() {
  const user = useUserStore((s) => s.currentUser);
  const notifications = useUserStore((s) => s.notifications);
  const unreadCount = useUserStore((s) => s.unreadCount);
  const markNotificationRead = useUserStore((s) => s.markNotificationRead);
  const markAllNotificationsRead = useUserStore((s) => s.markAllNotificationsRead);
  const fetchNotifications = useUserStore((s) => s.fetchNotifications);
  const [showNotifs, setShowNotifs] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setShowNotifs(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Refresh notifications periodically
  useEffect(() => {
    const id = setInterval(fetchNotifications, 30_000);
    return () => clearInterval(id);
  }, [fetchNotifications]);

  return (
    <header className="h-14 border-b border-border bg-card/40 backdrop-blur-xl flex items-center justify-between px-6 sticky top-0 z-40">
      {/* Search */}
      <div className="flex items-center gap-2 bg-muted/50 rounded-lg px-3 py-1.5 w-72">
        <Search className="w-4 h-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search conversions, files..."
          className="bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none flex-1"
        />
        <kbd className="text-[10px] text-muted-foreground bg-background/50 px-1.5 py-0.5 rounded font-mono">⌘K</kbd>
      </div>

      {/* Right */}
      <div className="flex items-center gap-3">
        {/* System Status */}
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Circle className="w-2 h-2 fill-success text-success" />
          <span>All systems operational</span>
        </div>

        <ThemeToggle />

        {/* Notifications */}
        <div className="relative" ref={panelRef}>
          <button
            onClick={() => { setShowNotifs(!showNotifs); if (!showNotifs) fetchNotifications(); }}
            className="relative p-2 rounded-lg hover:bg-muted/50 transition-colors text-muted-foreground hover:text-foreground"
          >
            <Bell className="w-4 h-4" />
            {unreadCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] rounded-full bg-accent text-[10px] font-bold text-accent-foreground flex items-center justify-center px-1">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </button>

          {showNotifs && (
            <div className="absolute right-0 top-12 w-96 bg-card border border-border rounded-xl shadow-2xl z-50 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                <h3 className="text-sm font-semibold text-foreground">Notifications</h3>
                {unreadCount > 0 && (
                  <button
                    onClick={markAllNotificationsRead}
                    className="text-[11px] text-accent hover:underline flex items-center gap-1"
                  >
                    <CheckCheck className="w-3 h-3" /> Mark all read
                  </button>
                )}
              </div>
              <div className="max-h-80 overflow-y-auto">
                {notifications.length === 0 ? (
                  <div className="p-6 text-center text-sm text-muted-foreground">No notifications yet</div>
                ) : (
                  notifications.map((n) => {
                    const Icon = typeIcon[n.type] || Info;
                    const color = typeColor[n.type] || "text-muted-foreground";
                    return (
                      <div
                        key={n.id}
                        onClick={() => { if (!n.read) markNotificationRead(n.id); }}
                        className={cn(
                          "flex items-start gap-3 px-4 py-3 border-b border-border/50 cursor-pointer transition-colors hover:bg-muted/30",
                          !n.read && "bg-accent/5"
                        )}
                      >
                        <Icon className={cn("w-4 h-4 mt-0.5 flex-shrink-0", color)} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between">
                            <span className={cn("text-xs font-medium", !n.read ? "text-foreground" : "text-muted-foreground")}>{n.title}</span>
                            {!n.read && <span className="w-2 h-2 rounded-full bg-accent flex-shrink-0" />}
                          </div>
                          <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">{n.message}</p>
                          <span className="text-[10px] text-muted-foreground/50 mt-1 block">
                            {new Date(n.createdAt).toLocaleString()}
                          </span>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}
        </div>

        {/* User */}
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-accent to-secondary flex items-center justify-center text-[11px] font-semibold text-accent-foreground">
            {user?.name?.charAt(0) || "U"}
          </div>
          <span className="text-sm font-medium text-foreground hidden md:block">{user?.name || "User"}</span>
        </div>
      </div>
    </header>
  );
}
