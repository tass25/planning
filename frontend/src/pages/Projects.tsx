import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, FolderKanban, FileCode, CheckCircle2, Archive, Rocket, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Project, Conversion } from "@/types";
import { useConversionStore } from "@/store/conversion-store";
import { StatusBadge } from "@/components/ui/status-badge";

const COLOR_OPTIONS = [
  { value: "accent", label: "Blue", class: "bg-accent" },
  { value: "success", label: "Green", class: "bg-success" },
  { value: "warning", label: "Amber", class: "bg-warning" },
  { value: "destructive", label: "Red", class: "bg-destructive" },
  { value: "secondary", label: "Purple", class: "bg-secondary" },
];

const STATUS_ICONS: Record<string, typeof FolderKanban> = {
  active: FolderKanban,
  archived: Archive,
  shipped: Rocket,
};

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState("accent");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [projectConversions, setProjectConversions] = useState<Record<string, Conversion[]>>({});
  const [showAssign, setShowAssign] = useState<string | null>(null);
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

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      const proj = await api.post<Project>("/projects", { name: newName.trim(), color: newColor });
      setProjects((prev) => [proj, ...prev]);
      setNewName("");
      setNewColor("accent");
      setShowCreate(false);
    } catch (err) {
      console.error("[codara] createProject failed", err);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/projects/${id}`);
      setProjects((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      console.error("[codara] deleteProject failed", err);
    }
  };

  const handleStatusChange = async (id: string, status: string) => {
    try {
      const updated = await api.put<Project>(`/projects/${id}`, { status });
      setProjects((prev) => prev.map((p) => (p.id === id ? updated : p)));
    } catch (err) {
      console.error("[codara] updateProject failed", err);
    }
  };

  const handleExpand = async (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    if (!projectConversions[id]) {
      try {
        const allConvs = await api.get<Conversion[]>("/conversions");
        setProjectConversions((prev) => ({ ...prev, [id]: allConvs ?? [] }));
      } catch (err) {
        console.error("[codara] fetch conversions for project failed", err);
      }
    }
  };

  const handleAssignConversion = async (projectId: string, conversionId: string) => {
    try {
      await api.post(`/projects/${projectId}/files`, { conversionId });
      await fetchProjects();
      setShowAssign(null);
    } catch (err) {
      console.error("[codara] assign conversion failed", err);
    }
  };

  const handleRemoveConversion = async (projectId: string, conversionId: string) => {
    try {
      await api.delete(`/projects/${projectId}/files/${conversionId}`);
      await fetchProjects();
    } catch (err) {
      console.error("[codara] remove conversion failed", err);
    }
  };

  const colorClass = (color: string) => {
    const opt = COLOR_OPTIONS.find((c) => c.value === color);
    return opt?.class ?? "bg-accent";
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Projects</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {projects.length} project{projects.length !== 1 ? "s" : ""} — group your conversions
          </p>
        </div>
        <Button onClick={() => setShowCreate(!showCreate)} className="bg-accent text-accent-foreground hover:bg-accent/90">
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
            className="glass-panel p-5 space-y-4 overflow-hidden"
          >
            <h2 className="text-sm font-semibold text-foreground">Create Project</h2>
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-2">Project Name</label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                placeholder="e.g. Financial ETL Migration"
                className="w-full px-3 py-2 rounded-lg bg-muted/30 border border-border text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:border-accent"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-2">Color</label>
              <div className="flex gap-2">
                {COLOR_OPTIONS.map((c) => (
                  <button
                    key={c.value}
                    onClick={() => setNewColor(c.value)}
                    className={cn(
                      "w-8 h-8 rounded-full transition-all",
                      c.class,
                      newColor === c.value ? "ring-2 ring-offset-2 ring-offset-background ring-foreground scale-110" : "opacity-60 hover:opacity-100"
                    )}
                  />
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <Button onClick={handleCreate} disabled={!newName.trim()} className="bg-accent text-accent-foreground hover:bg-accent/90">
                Create
              </Button>
              <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Projects grid */}
      {projects.length === 0 ? (
        <div className="glass-panel p-12 text-center">
          <FolderKanban className="w-10 h-10 mx-auto text-muted-foreground/30 mb-3" />
          <p className="text-sm text-muted-foreground">No projects yet. Create one to group your conversions.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {projects.map((proj) => {
            const Icon = STATUS_ICONS[proj.status] || FolderKanban;
            const isExpanded = expandedId === proj.id;

            return (
              <motion.div key={proj.id} layout className="glass-panel overflow-hidden">
                {/* Header */}
                <div
                  className="flex items-center gap-4 p-4 cursor-pointer hover:bg-muted/10 transition-colors"
                  onClick={() => handleExpand(proj.id)}
                >
                  <div className={cn("w-2 h-10 rounded-full flex-shrink-0", colorClass(proj.color))} />
                  <Icon className="w-5 h-5 text-muted-foreground flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-semibold text-foreground truncate">{proj.name}</h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {proj.files} file{proj.files !== 1 ? "s" : ""} — {proj.converted} converted — {new Date(proj.updatedAt).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <select
                      value={proj.status}
                      onChange={(e) => { e.stopPropagation(); handleStatusChange(proj.id, e.target.value); }}
                      onClick={(e) => e.stopPropagation()}
                      className="text-xs bg-muted/30 border border-border rounded px-2 py-1 text-muted-foreground focus:outline-none focus:border-accent"
                    >
                      <option value="active">Active</option>
                      <option value="archived">Archived</option>
                      <option value="shipped">Shipped</option>
                    </select>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDelete(proj.id); }}
                      className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* Expanded: conversions inside this project */}
                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ height: 0 }}
                      animate={{ height: "auto" }}
                      exit={{ height: 0 }}
                      className="overflow-hidden border-t border-border"
                    >
                      <div className="p-4 space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Conversions</span>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={(e) => { e.stopPropagation(); setShowAssign(showAssign === proj.id ? null : proj.id); }}
                          >
                            <Plus className="w-3 h-3 mr-1" /> Assign Conversion
                          </Button>
                        </div>

                        {/* Assign dialog */}
                        <AnimatePresence>
                          {showAssign === proj.id && (
                            <motion.div
                              initial={{ opacity: 0, height: 0 }}
                              animate={{ opacity: 1, height: "auto" }}
                              exit={{ opacity: 0, height: 0 }}
                              className="bg-muted/20 rounded-lg p-3 space-y-2 overflow-hidden"
                            >
                              <div className="flex items-center justify-between">
                                <span className="text-xs font-medium text-foreground">Select a conversion to assign</span>
                                <button onClick={() => setShowAssign(null)} className="text-muted-foreground hover:text-foreground">
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </div>
                              <div className="max-h-48 overflow-y-auto space-y-1">
                                {conversions.length === 0 ? (
                                  <p className="text-xs text-muted-foreground py-2">No conversions available</p>
                                ) : (
                                  conversions.map((c) => (
                                    <button
                                      key={c.id}
                                      onClick={() => handleAssignConversion(proj.id, c.id)}
                                      className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-muted/30 transition-colors text-left"
                                    >
                                      <FileCode className="w-3.5 h-3.5 text-accent flex-shrink-0" />
                                      <span className="text-xs font-medium text-foreground truncate">{c.fileName}</span>
                                      <StatusBadge status={c.status} />
                                    </button>
                                  ))
                                )}
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>

                        {proj.files === 0 ? (
                          <p className="text-xs text-muted-foreground/60 py-4 text-center">No conversions assigned yet</p>
                        ) : (
                          <div className="space-y-1">
                            {(projectConversions[proj.id] ?? [])
                              .filter(() => true)
                              .map((c) => (
                                <div key={c.id} className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-muted/10 transition-colors">
                                  <FileCode className="w-3.5 h-3.5 text-accent flex-shrink-0" />
                                  <Link to={`/workspace/${c.id}`} className="flex-1 text-xs font-medium text-foreground hover:text-accent truncate">
                                    {c.fileName}
                                  </Link>
                                  <StatusBadge status={c.status} />
                                  {c.accuracy > 0 && (
                                    <span className="text-[10px] font-mono text-success">{c.accuracy}%</span>
                                  )}
                                  <button
                                    onClick={() => handleRemoveConversion(proj.id, c.id)}
                                    className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                                  >
                                    <X className="w-3 h-3" />
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
