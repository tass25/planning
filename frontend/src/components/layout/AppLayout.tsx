import { Outlet, Navigate } from "react-router-dom";
import { useUserStore } from "@/store/user-store";
import { UserLayout } from "./UserLayout";
import { AdminLayout } from "./AdminLayout";

export function AppLayout() {
  const { currentUser, isAuthenticated } = useUserStore();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  const isAdmin = currentUser?.role === "admin";

  return isAdmin ? <AdminLayout /> : <UserLayout />;
}