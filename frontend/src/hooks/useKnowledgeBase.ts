/**
 * useKnowledgeBase — wraps KB CRUD operations.
 *
 * Usage:
 *   const { entries, loading, create, update, remove } = useKnowledgeBase();
 */

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type { KnowledgeBaseEntry } from "@/types";

interface UseKnowledgeBaseReturn {
  entries: KnowledgeBaseEntry[];
  loading: boolean;
  error: string | null;
  create: (entry: Omit<KnowledgeBaseEntry, "id" | "createdAt" | "updatedAt">) => Promise<void>;
  update: (id: string, entry: Partial<KnowledgeBaseEntry>) => Promise<void>;
  remove: (id: string) => Promise<void>;
  refresh: () => Promise<void>;
}

export function useKnowledgeBase(): UseKnowledgeBaseReturn {
  const [entries, setEntries] = useState<KnowledgeBaseEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<KnowledgeBaseEntry[]>("/kb");
      setEntries(data ?? []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      console.error("[codara] useKnowledgeBase fetch failed", err);
    } finally {
      setLoading(false);
    }
  }, []);

  const create = useCallback(
    async (entry: Omit<KnowledgeBaseEntry, "id" | "createdAt" | "updatedAt">) => {
      setError(null);
      try {
        await api.post<KnowledgeBaseEntry>("/kb", entry);
        await refresh();
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        throw err;
      }
    },
    [refresh],
  );

  const update = useCallback(
    async (id: string, entry: Partial<KnowledgeBaseEntry>) => {
      setError(null);
      try {
        await api.put<KnowledgeBaseEntry>(`/kb/${id}`, entry);
        await refresh();
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        throw err;
      }
    },
    [refresh],
  );

  const remove = useCallback(
    async (id: string) => {
      setError(null);
      try {
        await api.delete(`/kb/${id}`);
        setEntries((prev) => prev.filter((e) => e.id !== id));
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        throw err;
      }
    },
    [],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { entries, loading, error, create, update, remove, refresh };
}
