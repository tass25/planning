import { useEffect } from "react";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { useUserStore } from "@/store/user-store";
import { useConversionStore } from "@/store/conversion-store";
import { getToken } from "@/lib/api";
import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import LoginPage from "./pages/Login";
import SignupPage from "./pages/Signup";
import DashboardPage from "./pages/Dashboard";
import ConversionsPage from "./pages/Conversions";
import WorkspacePage from "./pages/Workspace";
import HistoryPage from "./pages/History";
import KnowledgeBasePage from "./pages/KnowledgeBase";
import AnalyticsPage from "./pages/Analytics";
import AdminPage from "./pages/Admin";
import AuditLogsPage from "./pages/admin/AuditLogs";
import SystemHealthPage from "./pages/admin/SystemHealth";
import UsersPage from "./pages/admin/Users";
import PipelineConfigPage from "./pages/admin/PipelineConfig";
import FileRegistryPage from "./pages/admin/FileRegistry";
import KBManagementPage from "./pages/admin/KBManagement";
import KBChangelogPage from "./pages/admin/KBChangelog";
import SettingsPage from "./pages/Settings";

const queryClient = new QueryClient();

const App = () => {
  useEffect(() => {
    useUserStore.getState().restoreSession().catch((err) => {
      console.error("[codara] restoreSession failed", err);
    });
    // Only fetch conversions if user has a token — prevents 401 on cold load
    if (getToken()) {
      useConversionStore.getState().fetchConversions().catch((err) => {
        console.error("[codara] initial fetchConversions failed", err);
      });
    }
  }, []);

  return (
  <ErrorBoundary>
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Index />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />

          {/* App routes with layout */}
          <Route element={<AppLayout />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/conversions" element={<ConversionsPage />} />
            <Route path="/workspace" element={<WorkspacePage />} />
            <Route path="/workspace/:conversionId" element={<WorkspacePage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/knowledge-base" element={<KnowledgeBasePage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/admin/audit-logs" element={<AuditLogsPage />} />
            <Route path="/admin/system-health" element={<SystemHealthPage />} />
            <Route path="/admin/users" element={<UsersPage />} />
            <Route path="/admin/pipeline-config" element={<PipelineConfigPage />} />
            <Route path="/admin/file-registry" element={<FileRegistryPage />} />
            <Route path="/admin/kb-management" element={<KBManagementPage />} />
            <Route path="/admin/kb-changelog" element={<KBChangelogPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>

          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
  </ErrorBoundary>
  );
};

export default App;
