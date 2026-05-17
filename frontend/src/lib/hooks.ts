import { useState, useEffect, useCallback, useRef } from "react";
import api, { isAuthenticated, getAuthVersion } from "./api";

// ── Generic fetch hook ──────────────────────────────────────────────────────

type FetchState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
};

function useFetch<T>(path: string, deps: any[] = []): FetchState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const authVer = getAuthVersion();

  const fetch_ = useCallback(async () => {
    if (!path || !isAuthenticated()) {
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(path);
      if (mountedRef.current) setData(res as T);
    } catch (e: any) {
      if (mountedRef.current) setError(e.message || "Request failed");
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [path, authVer, ...deps]);

  useEffect(() => {
    mountedRef.current = true;
    fetch_();
    return () => { mountedRef.current = false; };
  }, [fetch_]);

  return { data, loading, error, refetch: fetch_ };
}

// ── Conversions ─────────────────────────────────────────────────────────────

export interface ConversionStage {
  stage: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  latency: number | null;
  retryCount: number;
  warnings: string[];
  description: string | null;
  startedAt: string | null;
  completedAt: string | null;
}

export interface Conversion {
  id: string;
  fileName: string;
  status: "queued" | "running" | "completed" | "partial" | "failed";
  runtime: string;
  duration: number;
  accuracy: number;
  createdAt: string;
  updatedAt: string | null;
  progress: number;
  stages: ConversionStage[];
  sasCode: string | null;
  pythonCode: string | null;
  validationReport: string | null;
  mergeReport: string | null;
  cost: number;
}

export function useConversions() {
  return useFetch<Conversion[]>("/conversions");
}

export function useConversion(id: string | undefined) {
  return useFetch<Conversion>(id ? `/conversions/${id}` : "", [id]);
}

export function useConversionPolling(id: string | undefined) {
  const [conv, setConv] = useState<Conversion | null>(null);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef<any>(null);

  useEffect(() => {
    if (!id) return;
    let mounted = true;

    const poll = async () => {
      try {
        const res = await api.get(`/conversions/${id}`) as Conversion;
        if (mounted) {
          setConv(res);
          setLoading(false);
          if (res.status === "completed" || res.status === "failed" || res.status === "partial") {
            clearInterval(intervalRef.current);
          }
        }
      } catch {
        if (mounted) setLoading(false);
      }
    };

    poll();
    intervalRef.current = setInterval(poll, 1200);

    return () => {
      mounted = false;
      clearInterval(intervalRef.current);
    };
  }, [id]);

  return { data: conv, loading };
}

export interface UploadedFile {
  id: string;
  name: string;
  size: number;
  modules: string[];
  estimatedComplexity: string;
  uploadedAt: string;
}

export async function uploadFiles(files: FileList | File[]): Promise<UploadedFile[]> {
  const formData = new FormData();
  for (const f of Array.from(files)) {
    formData.append("files", f);
  }
  return api.upload("/conversions/upload", formData) as Promise<UploadedFile[]>;
}

export async function startConversion(
  fileIds: string[],
  config: { targetRuntime?: string; testCoverage?: string } = {}
): Promise<Conversion> {
  return api.post("/conversions/start", {
    fileIds,
    config: {
      targetRuntime: config.targetRuntime || "python",
      testCoverage: config.testCoverage || "full",
    },
  }) as Promise<Conversion>;
}

export async function downloadConversion(id: string): Promise<Blob> {
  const res = await api.get(`/conversions/${id}/download`);
  return (res as Response).blob();
}

export async function submitCorrection(
  conversionId: string,
  data: { correctedCode: string; explanation: string; category: string }
): Promise<any> {
  return api.post(`/conversions/${conversionId}/corrections`, data);
}

// ── Analytics ───────────────────────────────────────────────────────────────

export interface AnalyticsDay {
  date: string;
  conversions: number;
  successRate: number;
  avgLatency: number;
  failures: number;
}

export function useAnalytics() {
  return useFetch<AnalyticsDay[]>("/analytics");
}

export interface FailureMode {
  name: string;
  value: number;
}

export function useFailureModes() {
  return useFetch<FailureMode[]>("/analytics/failure-modes");
}

// ── Knowledge Base ──────────────────────────────────────────────────────────

export interface KBEntry {
  id: string;
  sasSnippet: string;
  pythonTranslation: string;
  category: string;
  confidence: number;
  createdAt: string;
  updatedAt: string;
}

export function useKnowledgeBase() {
  return useFetch<KBEntry[]>("/kb");
}

export async function createKBEntry(data: {
  sasSnippet: string;
  pythonTranslation: string;
  category: string;
  confidence?: number;
}): Promise<KBEntry> {
  return api.post("/kb", data) as Promise<KBEntry>;
}

export async function updateKBEntry(id: string, data: Partial<KBEntry>): Promise<KBEntry> {
  return api.put(`/kb/${id}`, data) as Promise<KBEntry>;
}

export async function deleteKBEntry(id: string): Promise<void> {
  await api.delete(`/kb/${id}`);
}

export interface KBChangelogEntry {
  id: string;
  entryId: string;
  action: string;
  user: string;
  timestamp: string;
  description: string;
}

export function useKBChangelog() {
  return useFetch<KBChangelogEntry[]>("/kb/changelog");
}

// ── Notifications ───────────────────────────────────────────────────────────

export interface Notification {
  id: string;
  userId: string;
  title: string;
  message: string;
  type: "info" | "success" | "warning" | "error";
  read: boolean;
  createdAt: string;
}

export function useNotifications() {
  const state = useFetch<Notification[]>("/notifications");

  const markRead = useCallback(async (id: string) => {
    await api.put(`/notifications/${id}/read`);
    state.refetch();
  }, [state.refetch]);

  const markAllRead = useCallback(async () => {
    await api.put("/notifications/read-all");
    state.refetch();
  }, [state.refetch]);

  return { ...state, markRead, markAllRead };
}

// ── Admin: Users ────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  name: string;
  role: "admin" | "user" | "viewer";
  conversionCount: number;
  status: "active" | "inactive" | "suspended";
  emailVerified: boolean;
  createdAt: string;
}

export function useUsers() {
  return useFetch<User[]>("/admin/users");
}

export async function updateUser(id: string, data: { role?: string; status?: string }): Promise<any> {
  return api.put(`/admin/users/${id}`, data);
}

export async function deleteUser(id: string): Promise<void> {
  await api.delete(`/admin/users/${id}`);
}

// ── Admin: Audit Logs ───────────────────────────────────────────────────────

export interface AuditLog {
  id: string;
  model: string;
  latency: number;
  cost: number;
  promptHash: string;
  success: boolean;
  timestamp: string;
}

export function useAuditLogs() {
  return useFetch<AuditLog[]>("/admin/audit-logs");
}

// ── Admin: System Health ────────────────────────────────────────────────────

export interface SystemService {
  name: string;
  status: "online" | "degraded" | "offline";
  latency: number;
  uptime: number;
}

export function useSystemHealth() {
  return useFetch<SystemService[]>("/admin/system-health");
}

// ── Admin: Pipeline Config ──────────────────────────────────────────────────

export interface PipelineConfig {
  maxRetries: number;
  timeout: number;
  checkpointInterval: number;
}

export function usePipelineConfig() {
  return useFetch<PipelineConfig>("/admin/pipeline-config");
}

export async function updatePipelineConfig(data: Partial<PipelineConfig>): Promise<PipelineConfig> {
  return api.put("/admin/pipeline-config", data) as Promise<PipelineConfig>;
}

// ── Admin: File Registry ────────────────────────────────────────────────────

export interface FileRegistryEntry {
  id: string;
  fileName: string;
  status: string;
  dependencies: string[];
  lineage: string[];
}

export function useFileRegistry() {
  return useFetch<FileRegistryEntry[]>("/admin/file-registry");
}

// ── Settings ────────────────────────────────────────────────────────────────

export interface UserSettings {
  defaultRuntime: string;
  emailNotifications: boolean;
}

export function useSettings() {
  return useFetch<UserSettings>("/settings");
}

export async function updateSettings(data: Partial<UserSettings>): Promise<any> {
  return api.put("/settings", data);
}

export async function updateProfile(data: { name?: string; email?: string }): Promise<any> {
  return api.put("/auth/me", data);
}

// ── Error Queue ─────────────────────────────────────────────────────────────

export interface ErrorQueueItem {
  id: string;
  fileName: string;
  stage: string;
  error: string;
  model: string;
  retries: number;
  createdAt: string;
  severity: string;
  userId: string;
  userName: string;
}

export function useErrorQueue() {
  return useFetch<ErrorQueueItem[]>("/admin/error-queue");
}

export async function retryConversion(convId: string): Promise<any> {
  return api.post(`/admin/error-queue/${convId}/retry`);
}

export async function dismissError(convId: string): Promise<void> {
  await api.delete(`/admin/error-queue/${convId}`);
}

// ── Projects ────────────────────────────────────────────────────────────────

export interface Project {
  id: string;
  name: string;
  ownerId: string;
  ownerName: string;
  status: string;
  color: string;
  files: number;
  converted: number;
  createdAt: string;
  updatedAt: string;
}

export function useProjects() {
  return useFetch<Project[]>("/projects");
}

export async function createProject(data: { name: string; color?: string }): Promise<Project> {
  return api.post("/projects", data) as Promise<Project>;
}

export async function updateProject(id: string, data: { name?: string; status?: string; color?: string }): Promise<Project> {
  return api.put(`/projects/${id}`, data) as Promise<Project>;
}

export async function deleteProject(id: string): Promise<void> {
  await api.delete(`/projects/${id}`);
}

export async function addFileToProject(projectId: string, conversionId: string): Promise<any> {
  return api.post(`/projects/${projectId}/files`, { conversionId });
}

// ── Cost Dashboard ──────────────────────────────────────────────────────────

export interface CostByModel {
  model: string;
  calls: number;
  tokens: number;
  cost: number;
}

export interface DailyCost {
  date: string;
  cost: number;
  calls: number;
}

export interface CostSummary {
  totalCost: number;
  totalCalls: number;
  totalTokens: number;
  byModel: CostByModel[];
  daily: DailyCost[];
}

export function useCostSummary() {
  return useFetch<CostSummary>("/admin/cost");
}

// ── Prompt Templates ───────────────────────────────────────────────────────

export interface PromptTemplate {
  id: string;
  name: string;
  displayName: string;
  description: string;
  model: string;
  category: string;
  status: string;
  content: string;
  variables: string[];
  uses: number;
  avgLatency: number;
  successRate: number;
  lastEdited: string;
  version: string;
}

export function usePromptTemplates() {
  return useFetch<PromptTemplate[]>("/admin/prompts");
}

export async function updatePromptTemplate(id: string, data: { content?: string; status?: string }): Promise<PromptTemplate> {
  return api.put(`/admin/prompts/${id}`, data) as Promise<PromptTemplate>;
}
