import { mockKnowledgeBase } from "@/lib/mock/data";
import { motion } from "framer-motion";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Plus, Edit, RotateCcw, Trash2 } from "lucide-react";

export default function KBManagementPage() {
  const [entries, setEntries] = useState(mockKnowledgeBase);

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Knowledge Base Management</h1>
          <p className="text-sm text-muted-foreground mt-1">{entries.length} entries</p>
        </div>
        <Button size="sm" className="bg-accent text-accent-foreground hover:bg-accent/90">
          <Plus className="w-3.5 h-3.5 mr-1.5" />Add Entry
        </Button>
      </div>

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
                    <button className="p-1 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground"><Edit className="w-3.5 h-3.5" /></button>
                    <button className="p-1 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground"><RotateCcw className="w-3.5 h-3.5" /></button>
                    <button className="p-1 rounded hover:bg-muted/50 text-muted-foreground hover:text-destructive"><Trash2 className="w-3.5 h-3.5" /></button>
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
