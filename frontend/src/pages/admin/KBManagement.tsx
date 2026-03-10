import { motion, AnimatePresence } from "framer-motion";
import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Plus, Edit, RotateCcw, Trash2, X, Save } from "lucide-react";
import { api } from "@/lib/api";
import type { KnowledgeBaseEntry } from "@/types";
import { toast } from "sonner";

interface KBFormData {
  sasSnippet: string;
  pythonTranslation: string;
  category: string;
  confidence: number;
}

const EMPTY_FORM: KBFormData = { sasSnippet: "", pythonTranslation: "", category: "", confidence: 0.9 };

export default function KBManagementPage() {
  const [entries, setEntries] = useState<KnowledgeBaseEntry[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState<KBFormData>(EMPTY_FORM);

  const refresh = () => api.get<KnowledgeBaseEntry[]>("/kb").then(setEntries).catch(() => {});
  useEffect(() => { refresh(); }, []);

  const handleAdd = async () => {
    if (!form.sasSnippet || !form.pythonTranslation || !form.category) {
      toast.error("Please fill in all fields");
      return;
    }
    try {
      await api.post("/kb", form);
      toast.success("Entry added");
      setShowAdd(false);
      setForm(EMPTY_FORM);
      refresh();
    } catch { toast.error("Failed to add entry"); }
  };

  const handleEdit = async (id: string) => {
    try {
      await api.put(`/kb/${id}`, form);
      toast.success("Entry updated");
      setEditingId(null);
      setForm(EMPTY_FORM);
      refresh();
    } catch { toast.error("Failed to update entry"); }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/kb/${id}`);
      toast.success("Entry deleted");
      refresh();
    } catch { toast.error("Failed to delete entry"); }
  };

  const startEdit = (entry: KnowledgeBaseEntry) => {
    setEditingId(entry.id);
    setShowAdd(false);
    setForm({
      sasSnippet: entry.sasSnippet,
      pythonTranslation: entry.pythonTranslation,
      category: entry.category,
      confidence: entry.confidence,
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setShowAdd(false);
    setForm(EMPTY_FORM);
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Knowledge Base Management</h1>
          <p className="text-sm text-muted-foreground mt-1">{entries.length} entries</p>
        </div>
        <Button size="sm" className="bg-accent text-accent-foreground hover:bg-accent/90" onClick={() => { setShowAdd(true); setEditingId(null); setForm(EMPTY_FORM); }}>
          <Plus className="w-3.5 h-3.5 mr-1.5" />Add Entry
        </Button>
      </div>

      {/* Add / Edit Form */}
      <AnimatePresence>
        {(showAdd || editingId) && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="glass-panel p-5 space-y-4 overflow-hidden">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground">{editingId ? "Edit Entry" : "Add New Entry"}</h3>
              <button onClick={cancelEdit} className="p-1 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground"><X className="w-4 h-4" /></button>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">SAS Snippet</label>
                <textarea value={form.sasSnippet} onChange={(e) => setForm({ ...form, sasSnippet: e.target.value })} className="w-full h-24 bg-muted/30 border border-border rounded-lg p-3 text-xs font-mono text-foreground placeholder:text-muted-foreground resize-none focus:outline-none focus:border-accent transition-colors" placeholder="proc means data=..." />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">Python Translation</label>
                <textarea value={form.pythonTranslation} onChange={(e) => setForm({ ...form, pythonTranslation: e.target.value })} className="w-full h-24 bg-muted/30 border border-border rounded-lg p-3 text-xs font-mono text-foreground placeholder:text-muted-foreground resize-none focus:outline-none focus:border-accent transition-colors" placeholder="df.describe()" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">Category</label>
                <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="w-full bg-muted/30 border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-accent transition-colors" placeholder="proc_means, data_step, ..." />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">Confidence (0-1)</label>
                <input type="number" min="0" max="1" step="0.05" value={form.confidence} onChange={(e) => setForm({ ...form, confidence: parseFloat(e.target.value) || 0 })} className="w-full bg-muted/30 border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent transition-colors" />
              </div>
            </div>
            <Button size="sm" onClick={() => editingId ? handleEdit(editingId) : handleAdd()} className="bg-accent text-accent-foreground hover:bg-accent/90">
              <Save className="w-3.5 h-3.5 mr-1.5" />{editingId ? "Save Changes" : "Add Entry"}
            </Button>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="glass-panel overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">SAS Snippet</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Python Translation</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Category</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Confidence</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {entries.map((entry) => (
              <tr key={entry.id} className="hover:bg-muted/20 transition-colors">
                <td className="px-4 py-3"><pre className="text-xs font-mono text-foreground/70 max-w-[200px] truncate">{entry.sasSnippet}</pre></td>
                <td className="px-4 py-3"><pre className="text-xs font-mono text-foreground/70 max-w-[200px] truncate">{entry.pythonTranslation}</pre></td>
                <td className="px-4 py-3"><span className="text-xs text-accent bg-accent/10 px-2 py-0.5 rounded">{entry.category}</span></td>
                <td className="px-4 py-3 text-xs font-mono text-foreground">{(entry.confidence * 100).toFixed(0)}%</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1">
                    <button onClick={() => startEdit(entry)} className="p-1 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground" title="Edit"><Edit className="w-3.5 h-3.5" /></button>
                    <button onClick={() => handleDelete(entry.id)} className="p-1 rounded hover:bg-muted/50 text-muted-foreground hover:text-destructive" title="Delete"><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}
