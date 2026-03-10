import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { KnowledgeBaseEntry } from "@/types";
import { motion } from "framer-motion";
import { BookOpen, Search } from "lucide-react";

export default function KnowledgeBasePage() {
  const [kbEntries, setKbEntries] = useState<KnowledgeBaseEntry[]>([]);
  const [search, setSearch] = useState("");
  useEffect(() => { api.get<KnowledgeBaseEntry[]>("/kb").then(setKbEntries).catch(() => {}); }, []);

  const filtered = kbEntries.filter((e) =>
    e.sasSnippet.toLowerCase().includes(search.toLowerCase()) ||
    e.category.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Knowledge Base</h1>
          <p className="text-sm text-muted-foreground mt-1">{kbEntries.length} translation patterns</p>
        </div>
      </div>

      <div className="flex items-center gap-2 bg-muted/30 border border-border rounded-lg px-3 py-2 w-full max-w-md">
        <Search className="w-4 h-4 text-muted-foreground" />
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search patterns..." className="bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none flex-1" />
      </div>

      <div className="space-y-3">
        {filtered.map((entry) => (
          <div key={entry.id} className="glass-panel p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <BookOpen className="w-3.5 h-3.5 text-accent" />
                <span className="text-xs font-medium text-accent bg-accent/10 px-2 py-0.5 rounded">{entry.category}</span>
              </div>
              <span className="text-xs text-muted-foreground">Confidence: <span className="text-foreground font-medium">{(entry.confidence * 100).toFixed(0)}%</span></span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <span className="text-[10px] font-medium text-muted-foreground block mb-1">SAS</span>
                <pre className="text-xs font-mono text-foreground/70 bg-muted/30 rounded p-2.5 whitespace-pre-wrap">{entry.sasSnippet}</pre>
              </div>
              <div>
                <span className="text-[10px] font-medium text-muted-foreground block mb-1">Python</span>
                <pre className="text-xs font-mono text-foreground/70 bg-muted/30 rounded p-2.5 whitespace-pre-wrap">{entry.pythonTranslation}</pre>
              </div>
            </div>
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="text-center py-12 text-sm text-muted-foreground">No patterns found</div>
        )}
      </div>
    </motion.div>
  );
}
