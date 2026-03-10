import { motion } from "framer-motion";
import { useUserStore } from "@/store/user-store";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { api } from "@/lib/api";

export default function SettingsPage() {
  const user = useUserStore((s) => s.currentUser);
  const [saved, setSaved] = useState(false);
  const [name, setName] = useState(user?.name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [runtime, setRuntime] = useState<string>("python");
  const [notifications, setNotifications] = useState(true);

  const handleSaveProfile = async () => {
    try {
      await api.put("/settings/profile", { name, email });
      useUserStore.getState().restoreSession();
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch { /* toast error */ }
  };

  const handleSavePreferences = async (rt?: string, notif?: boolean) => {
    const payload = { defaultRuntime: rt ?? runtime, emailNotifications: notif ?? notifications };
    try { await api.put("/settings/preferences", payload); } catch { /* toast error */ }
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">Manage your account and preferences</p>
      </div>

      <div className="glass-panel p-6 max-w-lg space-y-5">
        <h2 className="text-sm font-semibold text-foreground">Profile</h2>
        <div>
          <label className="text-xs font-medium text-muted-foreground block mb-1.5">Name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} className="w-full bg-muted/30 border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent transition-colors" />
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground block mb-1.5">Email</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} className="w-full bg-muted/30 border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent transition-colors" />
        </div>
        <Button onClick={handleSaveProfile} className="bg-accent text-accent-foreground hover:bg-accent/90">
          {saved ? "✓ Saved" : "Save Changes"}
        </Button>
      </div>

      <div className="glass-panel p-6 max-w-lg space-y-5">
        <h2 className="text-sm font-semibold text-foreground">Preferences</h2>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-foreground">Default Runtime</p>
            <p className="text-xs text-muted-foreground">Target language</p>
          </div>
          <span className="bg-muted/30 border border-border rounded-lg px-3 py-1.5 text-sm text-foreground">Python (pandas)</span>
        </div>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-foreground">Email Notifications</p>
            <p className="text-xs text-muted-foreground">Conversion completion alerts</p>
          </div>
          <button onClick={() => { const v = !notifications; setNotifications(v); handleSavePreferences(undefined, v); }} className={`w-10 h-5 rounded-full relative transition-colors ${notifications ? "bg-accent" : "bg-muted"}`}>
            <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-accent-foreground transition-transform ${notifications ? "right-0.5" : "left-0.5"}`} />
          </button>
        </div>
      </div>
    </motion.div>
  );
}
