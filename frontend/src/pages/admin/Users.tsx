import { StatusBadge } from "@/components/ui/status-badge";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useEffect, useState, useMemo } from "react";
import { api } from "@/lib/api";
import type { User } from "@/types";
import { usePageTitle } from "@/lib/hooks";
import { Search, Pencil, Trash2, X, Check } from "lucide-react";

const roleColors: Record<string, string> = {
  admin: "bg-secondary/15 text-secondary border-secondary/20",
  user: "bg-accent/15 text-accent border-accent/20",
  viewer: "bg-muted text-muted-foreground border-border",
};

export default function UsersPage() {
  usePageTitle("Users");
  const [users, setUsers] = useState<User[]>([]);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editRole, setEditRole] = useState<User["role"]>("user");
  const [editStatus, setEditStatus] = useState<User["status"]>("active");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => { api.get<User[]>("/admin/users").then(setUsers).catch(() => {}); }, []);

  const filtered = useMemo(() => users.filter((u) => {
    const q = search.toLowerCase();
    if (q && !u.name.toLowerCase().includes(q) && !u.email.toLowerCase().includes(q)) return false;
    if (roleFilter !== "all" && u.role !== roleFilter) return false;
    if (statusFilter !== "all" && u.status !== statusFilter) return false;
    return true;
  }), [users, search, roleFilter, statusFilter]);

  const startEdit = (u: User) => { setEditingId(u.id); setEditRole(u.role); setEditStatus(u.status); };

  const saveEdit = async (id: string) => {
    try {
      const updated = await api.put<User>(`/admin/users/${id}`, { role: editRole, status: editStatus });
      setUsers((prev) => prev.map((u) => (u.id === id ? { ...u, ...updated } : u)));
    } catch {
      setUsers((prev) => prev.map((u) => (u.id === id ? { ...u, role: editRole, status: editStatus } : u)));
    }
    setEditingId(null);
  };

  const confirmDelete = async (id: string) => {
    try { await api.delete(`/admin/users/${id}`); setUsers((prev) => prev.filter((u) => u.id !== id)); } catch {}
    setDeletingId(null);
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">User Management</h1>
        <p className="text-sm text-muted-foreground mt-1">{filtered.length} of {users.length} users</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search by name or email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-border bg-card text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
        </div>
        <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} className="px-3 py-2 text-sm rounded-lg border border-border bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-accent/40">
          <option value="all">All Roles</option>
          <option value="admin">Admin</option>
          <option value="user">User</option>
          <option value="viewer">Viewer</option>
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="px-3 py-2 text-sm rounded-lg border border-border bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-accent/40">
          <option value="all">All Statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
          <option value="suspended">Suspended</option>
        </select>
      </div>

      <div className="glass-panel overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Email</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Role</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Conversions</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Status</th>
              <th className="text-right text-xs font-medium text-muted-foreground px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filtered.map((user) => (
              <tr key={user.id} className="hover:bg-muted/20 transition-colors">
                <td className="px-4 py-3">
                  <div>
                    <p className="text-sm font-medium text-foreground">{user.name}</p>
                    <p className="text-xs text-muted-foreground">{user.email}</p>
                  </div>
                </td>
                <td className="px-4 py-3">
                  {editingId === user.id ? (
                    <select value={editRole} onChange={(e) => setEditRole(e.target.value as User["role"])} className="px-2 py-1 text-xs rounded border border-border bg-card text-foreground">
                      <option value="admin">Admin</option>
                      <option value="user">User</option>
                      <option value="viewer">Viewer</option>
                    </select>
                  ) : (
                    <span className={cn("inline-flex px-2 py-0.5 rounded-md text-xs font-medium border capitalize", roleColors[user.role])}>{user.role}</span>
                  )}
                </td>
                <td className="px-4 py-3 text-sm text-foreground font-mono">{user.conversionCount}</td>
                <td className="px-4 py-3">
                  {editingId === user.id ? (
                    <select value={editStatus} onChange={(e) => setEditStatus(e.target.value as User["status"])} className="px-2 py-1 text-xs rounded border border-border bg-card text-foreground">
                      <option value="active">Active</option>
                      <option value="inactive">Inactive</option>
                      <option value="suspended">Suspended</option>
                    </select>
                  ) : (
                    <span className={cn("text-xs font-medium capitalize", user.status === "active" ? "text-success" : user.status === "inactive" ? "text-muted-foreground" : "text-destructive")}>{user.status}</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-1">
                    {editingId === user.id ? (
                      <>
                        <button onClick={() => saveEdit(user.id)} className="p-1.5 rounded-md hover:bg-success/20 text-success transition-colors" title="Save"><Check className="w-3.5 h-3.5" /></button>
                        <button onClick={() => setEditingId(null)} className="p-1.5 rounded-md hover:bg-muted text-muted-foreground transition-colors" title="Cancel"><X className="w-3.5 h-3.5" /></button>
                      </>
                    ) : deletingId === user.id ? (
                      <>
                        <button onClick={() => confirmDelete(user.id)} className="px-2 py-1 text-xs rounded-md bg-destructive/15 text-destructive hover:bg-destructive/25 transition-colors">Confirm</button>
                        <button onClick={() => setDeletingId(null)} className="px-2 py-1 text-xs rounded-md hover:bg-muted text-muted-foreground transition-colors">Cancel</button>
                      </>
                    ) : (
                      <>
                        <button onClick={() => startEdit(user)} className="p-1.5 rounded-md hover:bg-accent/20 text-muted-foreground hover:text-accent transition-colors" title="Edit"><Pencil className="w-3.5 h-3.5" /></button>
                        <button onClick={() => setDeletingId(user.id)} className="p-1.5 rounded-md hover:bg-destructive/20 text-muted-foreground hover:text-destructive transition-colors" title="Delete"><Trash2 className="w-3.5 h-3.5" /></button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={5} className="text-center text-sm text-muted-foreground py-8">No users match your filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}
