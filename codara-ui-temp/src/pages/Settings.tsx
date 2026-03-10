import { motion } from "framer-motion";
import { useUserStore } from "@/store/user-store";
import { Button } from "@/components/ui/button";
import { useState } from "react";

export default function SettingsPage() {
  const user = useUserStore((s) => s.currentUser);
  const [saved, setSaved] = useState(false);

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
          <input defaultValue={user?.name} className="w-full bg-muted/30 border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent transition-colors" />
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground block mb-1.5">Email</label>
          <input defaultValue={user?.email} className="w-full bg-muted/30 border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent transition-colors" />
        </div>
        <Button onClick={() => { setSaved(true); setTimeout(() => setSaved(false), 2000); }} className="bg-accent text-accent-foreground hover:bg-accent/90">
          {saved ? "✓ Saved" : "Save Changes"}
        </Button>
      </div>

      <div className="glass-panel p-6 max-w-lg space-y-5">
        <h2 className="text-sm font-semibold text-foreground">Preferences</h2>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-foreground">Default Runtime</p>
            <p className="text-xs text-muted-foreground">Python or PySpark</p>
          </div>
          <select className="bg-muted/30 border border-border rounded-lg px-3 py-1.5 text-sm text-foreground focus:outline-none focus:border-accent transition-colors">
            <option>Python</option>
            <option>PySpark</option>
          </select>
        </div>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-foreground">Email Notifications</p>
            <p className="text-xs text-muted-foreground">Conversion completion alerts</p>
          </div>
          <button className="w-10 h-5 rounded-full bg-accent relative transition-colors">
            <span className="absolute right-0.5 top-0.5 w-4 h-4 rounded-full bg-accent-foreground transition-transform" />
          </button>
        </div>
      </div>
    </motion.div>
  );
}
