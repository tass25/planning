/**
 * useAdminUsers — wraps admin user list, update, and delete operations.
 *
 * Usage:
 *   const { users, loading, update, remove } = useAdminUsers();
 */

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type { User } from "@/types";

interface UseAdminUsersReturn {
  users: User[];
  loading: boolean;
  error: string | null;
  update: (id: string, patch: { role?: User["role"]; status?: User["status"] }) => Promise<void>;
  remove: (id: string) => Promise<void>;
  refresh: () => Promise<void>;
}

export function useAdminUsers(): UseAdminUsersReturn {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<User[]>("/admin/users");
      setUsers(data ?? []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      console.error("[codara] useAdminUsers fetch failed", err);
    } finally {
      setLoading(false);
    }
  }, []);

  const update = useCallback(
    async (id: string, patch: { role?: User["role"]; status?: User["status"] }) => {
      setError(null);
      try {
        const updated = await api.put<User>(`/admin/users/${id}`, patch);
        setUsers((prev) => prev.map((u) => (u.id === id ? updated : u)));
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        throw err;
      }
    },
    [],
  );

  const remove = useCallback(async (id: string) => {
    setError(null);
    try {
      await api.delete(`/admin/users/${id}`);
      setUsers((prev) => prev.filter((u) => u.id !== id));
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      throw err;
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { users, loading, error, update, remove, refresh };
}
