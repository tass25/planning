import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput,
  CommandItem, CommandList, CommandShortcut, CommandSeparator
} from "@/components/ui/command";
import {
  LayoutDashboard, FolderKanban, Upload, FileCode, History,
  BookOpen, BarChart3, Settings, Users, Activity, Cpu, Database,
  FileText, Shield, Wrench
} from "lucide-react";
import { useUserStore } from "@/store/user-store";

const NAV_ITEMS = [
  { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard, shortcut: "" },
  { label: "Projects", path: "/projects", icon: FolderKanban, shortcut: "" },
  { label: "New Conversion", path: "/conversions", icon: Upload, shortcut: "" },
  { label: "History", path: "/history", icon: History, shortcut: "" },
  { label: "Knowledge Base", path: "/knowledge-base", icon: BookOpen, shortcut: "" },
  { label: "Analytics", path: "/analytics", icon: BarChart3, shortcut: "" },
  { label: "Settings", path: "/settings", icon: Settings, shortcut: "" },
];

const ADMIN_ITEMS = [
  { label: "Admin Overview", path: "/admin", icon: Shield, shortcut: "" },
  { label: "Audit Logs", path: "/admin/audit-logs", icon: Activity, shortcut: "" },
  { label: "System Health", path: "/admin/system-health", icon: Cpu, shortcut: "" },
  { label: "User Management", path: "/admin/users", icon: Users, shortcut: "" },
  { label: "Pipeline Config", path: "/admin/pipeline-config", icon: Wrench, shortcut: "" },
  { label: "File Registry", path: "/admin/file-registry", icon: Database, shortcut: "" },
  { label: "KB Management", path: "/admin/kb-management", icon: BookOpen, shortcut: "" },
  { label: "KB Changelog", path: "/admin/kb-changelog", icon: FileText, shortcut: "" },
  { label: "Prompt Templates", path: "/admin/prompt-templates", icon: FileCode, shortcut: "" },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const user = useUserStore((s) => s.currentUser);
  const isAdmin = user?.role === "admin";

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  const go = (path: string) => {
    setOpen(false);
    navigate(path);
  };

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Search pages, actions..." />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>

        <CommandGroup heading="Navigation">
          {NAV_ITEMS.map((item) => (
            <CommandItem key={item.path} onSelect={() => go(item.path)}>
              <item.icon className="mr-2 h-4 w-4 text-muted-foreground" />
              <span>{item.label}</span>
              {item.shortcut && <CommandShortcut>{item.shortcut}</CommandShortcut>}
            </CommandItem>
          ))}
        </CommandGroup>

        {isAdmin && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Admin">
              {ADMIN_ITEMS.map((item) => (
                <CommandItem key={item.path} onSelect={() => go(item.path)}>
                  <item.icon className="mr-2 h-4 w-4 text-muted-foreground" />
                  <span>{item.label}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  );
}
