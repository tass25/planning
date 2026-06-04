import { useUserStore } from "@/store/user-store";
import UserDashboard from "@/components/dashboard/UserDashboard";
import AdminDashboard from "@/components/dashboard/AdminDashboard";
import { usePageTitle } from "@/lib/hooks";

export default function DashboardPage() {
  usePageTitle("Dashboard");
  const user = useUserStore((s) => s.currentUser);
  const isAdmin = user?.role === "admin";

  return isAdmin ? <AdminDashboard /> : <UserDashboard />;
}