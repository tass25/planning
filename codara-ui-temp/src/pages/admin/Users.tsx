import { mockUsers } from "@/lib/mock/data";
import { StatusBadge } from "@/components/ui/status-badge";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

const roleColors: Record<string, string> = {
  admin: "bg-secondary/15 text-secondary border-secondary/20",
  user: "bg-accent/15 text-accent border-accent/20",
  viewer: "bg-muted text-muted-foreground border-border",
};

export default function UsersPage() {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">User Management</h1>
        <p className="text-sm text-muted-foreground mt-1">{mockUsers.length} users</p>
      </div>

      <div className="glass-panel overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Email</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Role</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Conversions</th>
              <th className="text-left text-xs font-medium text-muted-foreground px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {mockUsers.map((user) => (
              <tr key={user.id} className="hover:bg-muted/20 transition-colors">
                <td className="px-4 py-3">
                  <div>
                    <p className="text-sm font-medium text-foreground">{user.name}</p>
                    <p className="text-xs text-muted-foreground">{user.email}</p>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className={cn("inline-flex px-2 py-0.5 rounded-md text-xs font-medium border capitalize", roleColors[user.role])}>{user.role}</span>
                </td>
                <td className="px-4 py-3 text-sm text-foreground font-mono">{user.conversionCount}</td>
                <td className="px-4 py-3">
                  <span className={cn("text-xs font-medium capitalize", user.status === "active" ? "text-success" : user.status === "inactive" ? "text-muted-foreground" : "text-destructive")}>{user.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}
