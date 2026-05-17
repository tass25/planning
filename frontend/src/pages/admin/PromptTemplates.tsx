import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";
import { FileText, Save, X, Activity, Clock, CheckCircle2, Code2, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { PromptTemplate } from "@/types";

const CATEGORY_COLORS: Record<string, string> = {
  translation: "text-accent bg-accent/10 border-accent/20",
  verification: "text-warning bg-warning/10 border-warning/20",
  indexing: "text-secondary bg-secondary/10 border-secondary/20",
};

export default function PromptTemplatesPage() {
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.get<PromptTemplate[]>("/admin/prompts");
        setTemplates(data ?? []);
      } catch (err) {
        console.error("[codara] fetchTemplates failed", err);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleEdit = (tpl: PromptTemplate) => {
    setEditingId(tpl.id);
    setEditContent(tpl.content);
    setExpandedId(tpl.id);
  };

  const handleSave = async (id: string) => {
    setSaving(true);
    try {
      const updated = await api.put<PromptTemplate>(`/admin/prompts/${id}`, { content: editContent });
      setTemplates((prev) => prev.map((t) => (t.id === id ? updated : t)));
      setEditingId(null);
    } catch (err) {
      console.error("[codara] saveTemplate failed", err);
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setEditingId(null);
    setEditContent("");
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
      <div>
        <h1 className="text-2xl font-bold text-foreground">Prompt Templates</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {templates.length} Jinja2 templates powering the pipeline
        </p>
      </div>

      {/* Template cards */}
      <div className="space-y-3">
        {templates.map((tpl) => {
          const isExpanded = expandedId === tpl.id;
          const isEditing = editingId === tpl.id;
          const catColor = CATEGORY_COLORS[tpl.category] ?? "text-muted-foreground bg-muted/10 border-border";

          return (
            <motion.div key={tpl.id} layout className="glass-panel overflow-hidden">
              {/* Header */}
              <div
                className="flex items-center gap-4 p-4 cursor-pointer hover:bg-muted/10 transition-colors"
                onClick={() => setExpandedId(isExpanded ? null : tpl.id)}
              >
                <FileText className="w-5 h-5 text-muted-foreground flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-foreground">{tpl.displayName}</h3>
                    <span className={cn("text-[10px] font-medium px-2 py-0.5 rounded-full border", catColor)}>
                      {tpl.category}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">{tpl.description}</p>
                </div>
                <div className="flex items-center gap-4 flex-shrink-0">
                  <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Activity className="w-3 h-3" />
                    <span>{tpl.uses} calls</span>
                  </div>
                  <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Clock className="w-3 h-3" />
                    <span>{tpl.avgLatency}ms</span>
                  </div>
                  <div className="flex items-center gap-1 text-xs text-success">
                    <CheckCircle2 className="w-3 h-3" />
                    <span>{tpl.successRate}%</span>
                  </div>
                  <ChevronDown className={cn("w-4 h-4 text-muted-foreground transition-transform", isExpanded && "rotate-180")} />
                </div>
              </div>

              {/* Expanded content */}
              <AnimatePresence>
                {isExpanded && (
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: "auto" }}
                    exit={{ height: 0 }}
                    className="overflow-hidden border-t border-border"
                  >
                    <div className="p-4 space-y-4">
                      {/* Meta info */}
                      <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                        <div className="flex items-center gap-1.5">
                          <Code2 className="w-3 h-3" />
                          <span className="font-mono">{tpl.name}.j2</span>
                        </div>
                        <span>Model: <span className="font-mono text-foreground">{tpl.model}</span></span>
                        <span>Variables: <span className="font-mono text-foreground">{tpl.variables.join(", ") || "none"}</span></span>
                        <span>Last edited: {new Date(tpl.lastEdited).toLocaleString()}</span>
                      </div>

                      {/* Template content */}
                      {isEditing ? (
                        <div className="space-y-3">
                          <textarea
                            value={editContent}
                            onChange={(e) => setEditContent(e.target.value)}
                            className="w-full h-80 px-4 py-3 rounded-lg bg-muted/20 border border-border font-mono text-xs text-foreground resize-y focus:outline-none focus:border-accent"
                            spellCheck={false}
                          />
                          <div className="flex gap-2">
                            <Button onClick={() => handleSave(tpl.id)} disabled={saving} className="bg-accent text-accent-foreground hover:bg-accent/90">
                              <Save className="w-3.5 h-3.5 mr-1.5" />
                              {saving ? "Saving..." : "Save"}
                            </Button>
                            <Button variant="outline" onClick={handleCancel}>
                              <X className="w-3.5 h-3.5 mr-1.5" /> Cancel
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          <pre className="w-full max-h-80 overflow-auto px-4 py-3 rounded-lg bg-muted/20 border border-border font-mono text-xs text-foreground whitespace-pre-wrap">
                            {tpl.content}
                          </pre>
                          <Button size="sm" variant="outline" onClick={() => handleEdit(tpl)}>
                            Edit Template
                          </Button>
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

      {templates.length === 0 && (
        <div className="glass-panel p-12 text-center">
          <FileText className="w-10 h-10 mx-auto text-muted-foreground/30 mb-3" />
          <p className="text-sm text-muted-foreground">No prompt templates found</p>
        </div>
      )}
    </motion.div>
  );
}
