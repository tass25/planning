import { Bell, Search, Circle } from "lucide-react";
import { useUserStore } from "@/store/user-store";
import { ThemeToggle } from "@/components/ThemeToggle";

export function TopBar() {
  const user = useUserStore((s) => s.currentUser);

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
        <button className="relative p-2 rounded-lg hover:bg-muted/50 transition-colors text-muted-foreground hover:text-foreground">
          <Bell className="w-4 h-4" />
          <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-accent" />
        </button>

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
