import { Outlet, Navigate } from "react-router-dom";
import { useUserStore } from "@/store/user-store";
import { UserLayout } from "./UserLayout";
import { AdminLayout } from "./AdminLayout";
import { CommandPalette } from "@/components/CommandPalette";

export function AppLayout() {
  const { currentUser, isAuthenticated } = useUserStore();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (currentUser && !currentUser.emailVerified && currentUser.role !== "admin") {
    return <Navigate to="/verify-email" replace />;
  }

  const isAdmin = currentUser?.role === "admin";

  return (
    <>
      <CommandPalette />
      {isAdmin ? <AdminLayout /> : <UserLayout />}
    </>
  );
}