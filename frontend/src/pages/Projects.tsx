import { useState, useEffect, useCallback } from "react";
import { usePageTitle } from "@/lib/hooks";
import { api } from "@/lib/api";
import { Link, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus, FolderKanban, FileCode, Archive, Rocket, Trash2, X,
  Pencil, Check, Palette, Search, SlidersHorizontal, Calendar,
  MoreHorizontal, ChevronRight, FileUp
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Project, Conversion } from "@/types";
import { useConversionStore } from "@/store/conversion-store";
import { StatusBadge } from "@/components/ui/status-badge";
import { ProjectCardSkeleton } from "@/components/Skeletons";
import { toast } from "sonner";

const COLOR_OPTIONS = [
  { value: "accent", label: "Blue", class: "bg-accent", light: "bg-accent/15 text-accent" },
  { value: "success", label: "Green", class: "bg-success", light: "bg-success/15 text-success" },
  { value: "warning", label: "Amber", class: "bg-warning", light: "bg-warning/15 text-warning" },
  { value: "destructive", label: "Red", class: "bg-destructive", light: "bg-destructive/15 text-destructive" },
  { value: "secondary", label: "Purple", class: "bg-secondary", light: "bg-secondary/15 text-secondary" },
  { value: "pink", label: "Pink", class: "bg-pink-500", light: "bg-pink-500/15 text-pink-500" },
  { value: "cyan", label: "Cyan", class: "bg-cyan-500", light: "bg-cyan-500/15 text-cyan-500" },
  { value: "orange", label: "Orange", class: "bg-orange-500", light: "bg-orange-500/15 text-orange-500" },
];

const STATUS_CONFIG: Record<string, { label: string; icon: typeof FolderKanban; badge: string }> = {
  active: { label: "Active", icon: FolderKanban, badge: "bg-success/15 text-success border-success/20" },
  archived: { label: "Archived", icon: Archive, badge: "bg-muted/50 text-muted-foreground border-border" },
  shipped: { label: "Shipped", icon: Rocket, badge: "bg-accent/15 text-accent border-accent/20" },
};

export default function ProjectsPage() {
  usePageTitle("Projects");
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState("accent");

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  // Card interactions
  const [openCardId, setOpenCardId] = useState<string | null>(null);
  const [cardConversions, setCardConversions] = useState<Record<string, Conversion[]>>({});
  const [showAssign, setShowAssign] = useState<string | null>(null);
  const [editingNameId, setEditingNameId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editingColorId, setEditingColorId] = useState<string | null>(null);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const conversions = useConversionStore((s) => s.conversions);

  const fetchProjects = useCallback(async () => {
    try {
      const data = await api.get<Project[]>("/projects");
      setProjects(data ?? []);
    } catch (err) {
      console.error("[codara] fetchProjects failed", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchProjects(); }, [fetchProjects]);

  // Filtered projects
  const filtered = projects.filter((p) => {
    if (statusFilter !== "all" && p.status !== statusFilter) return false;
    if (searchQuery && !p.name.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      const proj = await api.post<Project>("/projects", { name: newName.trim(), color: newColor });
      setProjects((prev) => [proj, ...prev]);
      setNewName("");
      setNewColor("accent");
      setShowCreate(false);
      toast.success("Project created");
    } catch (err) {
      toast.error("Failed to create project");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/projects/${id}`);
      setProjects((prev) => prev.filter((p) => p.id !== id));
      setDeleteConfirmId(null);
      setMenuOpenId(null);
      if (openCardId === id) setOpenCardId(null);
      toast.success("Project deleted");
    } catch (err) {
      toast.error("Failed to delete project");
    }
  };

  const handleUpdate = async (id: string, data: { name?: string; status?: string; color?: string }) => {
    try {
      const updated = await api.put<Project>(`/projects/${id}`, data);
      setProjects((prev) => prev.map((p) => (p.id === id ? updated : p)));
    } catch (err) {
      console.error("[codara] updateProject failed", err);
    }
  };

  const handleSaveName = async (id: string) => {
    if (editName.trim()) await handleUpdate(id, { name: editName.trim() });
    setEditingNameId(null);
  };

  const handleOpenCard = async (id: string) => {
    if (openCardId === id) { setOpenCardId(null); return; }
    setOpenCardId(id);
    try {
      const convs = await api.get<Conversion[]>(`/projects/${id}/conversions`);
      setCardConversions((prev) => ({ ...prev, [id]: convs ?? [] }));
    } catch (err) {
      console.error("[codara] fetch project conversions failed", err);
    }
  };

  const handleAssign = async (projectId: string, conversionId: string) => {
    try {
      await api.post(`/projects/${projectId}/files`, { conversionId });
      await fetchProjects();
      const convs = await api.get<Conversion[]>(`/projects/${projectId}/conversions`);
      setCardConversions((prev) => ({ ...prev, [projectId]: convs ?? [] }));
      setShowAssign(null);
    } catch (err) {
      console.error("[codara] assign conversion failed", err);
    }
  };

  const handleRemoveConversion = async (projectId: string, conversionId: string) => {
    try {
      await api.delete(`/projects/${projectId}/files/${conversionId}`);
      await fetchProjects();
      setCardConversions((prev) => ({
        ...prev,
        [projectId]: (prev[projectId] ?? []).filter((c) => c.id !== conversionId),
      }));
    } catch (err) {
      console.error("[codara] remove conversion failed", err);
    }
  };

  const colorClass = (color: string) => {
    const opt = COLOR_OPTIONS.find((c) => c.value === color);
    return opt?.class ?? "bg-accent";
  };

  const colorLightClass = (color: string) => {
    const opt = COLOR_OPTIONS.find((c) => c.value === color);
    return opt?.light ?? "bg-accent/15 text-accent";
  };

  const statusCounts = {
    all: projects.length,
    active: projects.filter((p) => p.status === "active").length,
    archived: projects.filter((p) => p.status === "archived").length,
    shipped: projects.filter((p) => p.status === "shipped").length,
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div><h1 className="text-2xl font-bold text-foreground">Projects</h1></div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <ProjectCardSkeleton /><ProjectCardSkeleton /><ProjectCardSkeleton />
          <ProjectCardSkeleton /><ProjectCardSkeleton /><ProjectCardSkeleton />
        </div>
      </div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Projects</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Organize and track your SAS conversion projects
          </p>
        </div>
        <Button onClick={() => setShowCreate(!showCreate)} className="bg-accent text-accent-foreground hover:bg-accent/90 cursor-pointer">
          <Plus className="w-4 h-4 mr-2" /> New Project
        </Button>
      </div>

      {/* Create form */}
      <AnimatePresence>
        {showCreate && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="glass-panel p-6 space-y-5">
              <h2 className="text-base font-semibold text-foreground">Create new project</h2>
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-2">Project Name</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  placeholder="e.g. Financial ETL Migration"
                  className="w-full px-4 py-2.5 rounded-xl bg-muted/30 border border-border text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 transition-all"
                  autoFocus
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-3">Color tag</label>
                <div className="flex gap-3">
                  {COLOR_OPTIONS.map((c) => (
                    <button
                      key={c.value}
                      onClick={() => setNewColor(c.value)}
                      title={c.label}
                      className={cn(
                        "w-9 h-9 rounded-full transition-all cursor-pointer",
                        c.class,
                        newColor === c.value ? "ring-2 ring-offset-2 ring-offset-background ring-foreground scale-110" : "opacity-50 hover:opacity-80 hover:scale-105"
                      )}
                    />
                  ))}
                </div>
              </div>
              <div className="flex gap-2 pt-1">
                <Button onClick={handleCreate} disabled={!newName.trim()} className="bg-accent text-accent-foreground hover:bg-accent/90 cursor-pointer px-6">
                  Create Project
                </Button>
                <Button variant="ghost" onClick={() => setShowCreate(false)} className="cursor-pointer text-muted-foreground">Cancel</Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Filters bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/50" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search projects..."
            className="w-full pl-9 pr-3 py-2 rounded-xl bg-muted/20 border border-border text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:border-accent/50 focus:bg-muted/30 transition-all"
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Status pills */}
        <div className="flex items-center gap-1.5">
          <SlidersHorizontal className="w-3.5 h-3.5 text-muted-foreground/50 mr-1" />
          {(["all", "active", "archived", "shipped"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer",
                statusFilter === s
                  ? "bg-accent/15 text-accent border border-accent/25"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/30 border border-transparent"
              )}
            >
              {s === "all" ? "All" : STATUS_CONFIG[s].label}
              <span className={cn(
                "ml-1.5 text-[10px] font-semibold",
                statusFilter === s ? "text-accent/70" : "text-muted-foreground/50"
              )}>
                {statusCounts[s]}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Projects grid */}
      {projects.length === 0 ? (
        <div className="glass-panel p-16 text-center">
          <div className="w-16 h-16 mx-auto rounded-2xl bg-accent/10 flex items-center justify-center mb-4">
            <FolderKanban className="w-8 h-8 text-accent/40" />
          </div>
          <h3 className="text-base font-semibold text-foreground mb-1">No projects yet</h3>
          <p className="text-sm text-muted-foreground mb-6 max-w-sm mx-auto">
            Create a project to organize your SAS conversions into logical groups.
          </p>
          <Button onClick={() => setShowCreate(true)} className="bg-accent text-accent-foreground hover:bg-accent/90 cursor-pointer">
            <Plus className="w-4 h-4 mr-2" /> Create your first project
          </Button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="glass-panel p-12 text-center">
          <Search className="w-8 h-8 mx-auto text-muted-foreground/20 mb-3" />
          <p className="text-sm text-muted-foreground">No projects match your filters.</p>
          <button onClick={() => { setSearchQuery(""); setStatusFilter("all"); }} className="text-xs text-accent hover:underline mt-2 cursor-pointer">
            Clear filters
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((proj, i) => {
            const statusConf = STATUS_CONFIG[proj.status] || STATUS_CONFIG.active;
            const StatusIcon = statusConf.icon;
            const isOpen = openCardId === proj.id;
            const convs = cardConversions[proj.id] ?? [];
            const progressPct = proj.files > 0 ? Math.round((proj.converted / proj.files) * 100) : 0;

            return (
              <motion.div
                key={proj.id}
                layout
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
                className={cn(
                  "glass-panel overflow-hidden flex flex-col transition-all duration-200",
                  isOpen ? "md:col-span-2 xl:col-span-3" : "hover:shadow-lg hover:-translate-y-0.5"
                )}
              >
                {/* Color accent — thicker bar */}
                <div className={cn("h-1.5", colorClass(proj.color))} />

                {/* Card body */}
                <div className="p-5 flex-1 flex flex-col">
                  {/* Top row: icon + name + menu */}
                  <div className="flex items-start gap-3 mb-4">
                    <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0", colorLightClass(proj.color))}>
                      <FolderKanban className="w-5 h-5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      {editingNameId === proj.id ? (
                        <div className="flex items-center gap-2">
                          <input
                            type="text"
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleSaveName(proj.id);
                              if (e.key === "Escape") setEditingNameId(null);
                            }}
                            className="flex-1 px-2 py-1 rounded-lg bg-muted/30 border border-accent text-sm font-semibold text-foreground focus:outline-none"
                            autoFocus
                          />
                          <button onClick={() => handleSaveName(proj.id)} className="p-1 rounded hover:bg-success/10 text-success cursor-pointer">
                            <Check className="w-4 h-4" />
                          </button>
                          <button onClick={() => setEditingNameId(null)} className="p-1 rounded hover:bg-muted/30 text-muted-foreground cursor-pointer">
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      ) : (
                        <>
                          <h3 className="text-sm font-bold text-foreground truncate leading-tight">{proj.name}</h3>
                          <div className="flex items-center gap-2 mt-1">
                            <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold border", statusConf.badge)}>
                              <StatusIcon className="w-3 h-3" />
                              {statusConf.label}
                            </span>
                          </div>
                        </>
                      )}
                    </div>

                    {/* Menu */}
                    <div className="relative">
                      <button
                        onClick={(e) => { e.stopPropagation(); setMenuOpenId(menuOpenId === proj.id ? null : proj.id); }}
                        className="p-1.5 rounded-lg hover:bg-muted/30 text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                      >
                        <MoreHorizontal className="w-4 h-4" />
                      </button>
                      <AnimatePresence>
                        {menuOpenId === proj.id && (
                          <motion.div
                            initial={{ opacity: 0, scale: 0.95, y: -4 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.95, y: -4 }}
                            className="absolute right-0 top-full mt-1 w-44 glass-panel-strong shadow-xl z-50 py-1 overflow-hidden"
                          >
                            <button
                              onClick={() => { setEditingNameId(proj.id); setEditName(proj.name); setMenuOpenId(null); }}
                              className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-colors cursor-pointer"
                            >
                              <Pencil className="w-3.5 h-3.5" /> Rename
                            </button>
                            <button
                              onClick={() => { setEditingColorId(editingColorId === proj.id ? null : proj.id); setMenuOpenId(null); }}
                              className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-colors cursor-pointer"
                            >
                              <Palette className="w-3.5 h-3.5" /> Change color
                            </button>
                            {(["active", "archived", "shipped"] as const).filter((s) => s !== proj.status).map((s) => (
                              <button
                                key={s}
                                onClick={() => { handleUpdate(proj.id, { status: s }); setMenuOpenId(null); }}
                                className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-colors cursor-pointer"
                              >
                                {(() => { const I = STATUS_CONFIG[s].icon; return <I className="w-3.5 h-3.5" />; })()}
                                Mark as {STATUS_CONFIG[s].label}
                              </button>
                            ))}
                            <div className="my-1 h-px bg-border" />
                            {deleteConfirmId === proj.id ? (
                              <div className="flex items-center gap-1 px-3 py-2">
                                <span className="text-xs text-destructive font-medium">Delete?</span>
                                <button onClick={() => handleDelete(proj.id)} className="px-2 py-0.5 rounded text-[10px] bg-destructive text-destructive-foreground font-semibold cursor-pointer">
                                  Yes
                                </button>
                                <button onClick={() => setDeleteConfirmId(null)} className="px-2 py-0.5 rounded text-[10px] bg-muted text-muted-foreground font-semibold cursor-pointer">
                                  No
                                </button>
                              </div>
                            ) : (
                              <button
                                onClick={() => setDeleteConfirmId(proj.id)}
                                className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-destructive hover:bg-destructive/10 transition-colors cursor-pointer"
                              >
                                <Trash2 className="w-3.5 h-3.5" /> Delete project
                              </button>
                            )}
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </div>

                  {/* Color picker popover */}
                  <AnimatePresence>
                    {editingColorId === proj.id && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        className="overflow-hidden mb-4"
                      >
                        <div className="flex items-center gap-2 p-3 rounded-xl bg-muted/20 border border-border">
                          <span className="text-xs text-muted-foreground mr-1">Color:</span>
                          {COLOR_OPTIONS.map((c) => (
                            <button
                              key={c.value}
                              onClick={() => { handleUpdate(proj.id, { color: c.value }); setEditingColorId(null); }}
                              title={c.label}
                              className={cn(
                                "w-7 h-7 rounded-full transition-all cursor-pointer",
                                c.class,
                                proj.color === c.value ? "ring-2 ring-offset-1 ring-offset-background ring-foreground scale-110" : "opacity-50 hover:opacity-90 hover:scale-105"
                              )}
                            />
                          ))}
                          <button onClick={() => setEditingColorId(null)} className="ml-auto p-1 text-muted-foreground hover:text-foreground cursor-pointer">
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>

                  {/* Stats row */}
                  <div className="grid grid-cols-3 gap-3 mb-4">
                    <div className="text-center p-2.5 rounded-xl bg-muted/15">
                      <p className="text-lg font-bold text-foreground leading-none">{proj.files}</p>
                      <p className="text-[10px] text-muted-foreground mt-1">Files</p>
                    </div>
                    <div className="text-center p-2.5 rounded-xl bg-muted/15">
                      <p className="text-lg font-bold text-success leading-none">{proj.converted}</p>
                      <p className="text-[10px] text-muted-foreground mt-1">Converted</p>
                    </div>
                    <div className="text-center p-2.5 rounded-xl bg-muted/15">
                      <p className={cn("text-lg font-bold leading-none", progressPct === 100 ? "text-success" : progressPct > 0 ? "text-accent" : "text-muted-foreground")}>
                        {progressPct}%
                      </p>
                      <p className="text-[10px] text-muted-foreground mt-1">Complete</p>
                    </div>
                  </div>

                  {/* Progress bar */}
                  {proj.files > 0 && (
                    <div className="mb-4">
                      <div className="h-1.5 rounded-full bg-muted/30 overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${progressPct}%` }}
                          transition={{ duration: 0.6, ease: "easeOut" }}
                          className={cn("h-full rounded-full", progressPct === 100 ? "bg-success" : colorClass(proj.color))}
                        />
                      </div>
                    </div>
                  )}

                  {/* Footer: date + open button */}
                  <div className="mt-auto flex items-center justify-between pt-2">
                    <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground/60">
                      <Calendar className="w-3 h-3" />
                      {new Date(proj.updatedAt).toLocaleDateString()}
                    </div>
                    <button
                      onClick={() => handleOpenCard(proj.id)}
                      className={cn(
                        "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer",
                        isOpen ? "bg-accent/15 text-accent" : "text-muted-foreground hover:text-foreground hover:bg-muted/30"
                      )}
                    >
                      {isOpen ? "Close" : "Open"}
                      <ChevronRight className={cn("w-3.5 h-3.5 transition-transform", isOpen && "rotate-90")} />
                    </button>
                  </div>
                </div>

                {/* Expanded: files panel */}
                <AnimatePresence>
                  {isOpen && (
                    <motion.div
                      initial={{ height: 0 }}
                      animate={{ height: "auto" }}
                      exit={{ height: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="border-t border-border p-5 space-y-4 bg-muted/5">
                        <div className="flex items-center justify-between">
                          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                            Files ({convs.length})
                          </h4>
                          <Button
                            size="sm"
                            variant="outline"
                            className="cursor-pointer h-8 text-xs"
                            onClick={() => setShowAssign(showAssign === proj.id ? null : proj.id)}
                          >
                            <FileUp className="w-3 h-3 mr-1.5" /> Add File
                          </Button>
                        </div>

                        {/* Assign picker */}
                        <AnimatePresence>
                          {showAssign === proj.id && (
                            <motion.div
                              initial={{ opacity: 0, height: 0 }}
                              animate={{ opacity: 1, height: "auto" }}
                              exit={{ opacity: 0, height: 0 }}
                              className="overflow-hidden"
                            >
                              <div className="rounded-xl bg-muted/20 border border-border p-3 space-y-2">
                                <div className="flex items-center justify-between">
                                  <span className="text-xs font-medium text-foreground">Select a conversion to add</span>
                                  <button onClick={() => setShowAssign(null)} className="text-muted-foreground hover:text-foreground cursor-pointer">
                                    <X className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                                <div className="max-h-48 overflow-y-auto space-y-1">
                                  {conversions.length === 0 ? (
                                    <p className="text-xs text-muted-foreground py-3 text-center">No conversions available. Upload a SAS file first.</p>
                                  ) : (
                                    conversions
                                      .filter((c) => !convs.some((pc) => pc.id === c.id))
                                      .map((c) => (
                                        <button
                                          key={c.id}
                                          onClick={() => handleAssign(proj.id, c.id)}
                                          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-muted/30 transition-colors text-left cursor-pointer"
                                        >
                                          <FileCode className="w-3.5 h-3.5 text-accent flex-shrink-0" />
                                          <span className="text-xs font-medium text-foreground truncate flex-1">{c.fileName}</span>
                                          <StatusBadge status={c.status} />
                                        </button>
                                      ))
                                  )}
                                </div>
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>

                        {convs.length === 0 ? (
                          <div className="py-8 text-center">
                            <FileCode className="w-8 h-8 mx-auto text-muted-foreground/15 mb-2" />
                            <p className="text-xs text-muted-foreground/60">No files yet. Click "Add File" to link a conversion.</p>
                          </div>
                        ) : (
                          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                            {convs.map((c) => (
                              <div
                                key={c.id}
                                className="flex items-center gap-3 px-3.5 py-3 rounded-xl bg-background/50 border border-border/50 hover:border-accent/30 hover:bg-accent/5 transition-all group"
                              >
                                <FileCode className="w-4 h-4 text-accent flex-shrink-0" />
                                <div className="flex-1 min-w-0">
                                  <Link to={`/workspace/${c.id}`} className="text-sm font-medium text-foreground hover:text-accent truncate block">
                                    {c.fileName}
                                  </Link>
                                  <div className="flex items-center gap-2 mt-0.5">
                                    <StatusBadge status={c.status} />
                                    {c.accuracy > 0 && (
                                      <span className={cn(
                                        "text-[10px] font-mono font-bold",
                                        c.accuracy >= 80 ? "text-success" : c.accuracy >= 50 ? "text-warning" : "text-destructive"
                                      )}>
                                        {c.accuracy}%
                                      </span>
                                    )}
                                    {c.duration > 0 && (
                                      <span className="text-[10px] text-muted-foreground/40">{c.duration.toFixed(1)}s</span>
                                    )}
                                  </div>
                                </div>
                                <button
                                  onClick={() => handleRemoveConversion(proj.id, c.id)}
                                  className="p-1 rounded hover:bg-destructive/10 text-muted-foreground/30 hover:text-destructive transition-all opacity-0 group-hover:opacity-100 cursor-pointer"
                                  title="Remove from project"
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            );
          })}
        </div>
      )}
    </motion.div>
  );
}
