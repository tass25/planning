import { useUserStore } from "@/store/user-store";
import UserDashboard from "@/components/dashboard/UserDashboard";
import AdminDashboard from "@/components/dashboard/AdminDashboard";

export default function DashboardPage() {
  const user = useUserStore((s) => s.currentUser);
  const isAdmin = user?.role === "admin";

  return isAdmin ? <AdminDashboard /> : <UserDashboard />;
}