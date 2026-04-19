export type PipelineStage =
  | "file_process"
  | "sas_partition"
  | "strategy_select"
  | "translate"
  | "validate"
  | "repair"
  | "merge"
  | "finalize";

export type StageStatus = "pending" | "running" | "completed" | "failed" | "skipped";

export interface PipelineStageInfo {
  stage: PipelineStage;
  status: StageStatus;
  latency?: number;
  retryCount: number;
  warnings: string[];
  description?: string;
  startedAt?: string;
  completedAt?: string;
}

export type ConversionStatus = "queued" | "running" | "completed" | "partial" | "failed";
export type TargetRuntime = "python";
export type TestCoverage = "full" | "structural_only";
export type RiskLevel = "low" | "medium" | "high";

export interface SasFile {
  id: string;
  name: string;
  size: number;
  modules: string[];
  estimatedComplexity: RiskLevel;
  uploadedAt: string;
}

export interface ConversionConfig {
  targetRuntime: TargetRuntime;
  testCoverage: TestCoverage;
}

export interface Conversion {
  id: string;
  fileName: string;
  status: ConversionStatus;
  runtime: TargetRuntime;
  duration: number;
  accuracy: number;
  createdAt: string;
  updatedAt?: string;
  stages: PipelineStageInfo[];
  sasCode?: string;
  pythonCode?: string;
  validationReport?: string;
  mergeReport?: string;
}

export interface Partition {
  id: string;
  conversionId: string;
  sasBlock: string;
  riskLevel: RiskLevel;
  strategy: string;
  translatedCode: string;
}

export interface AuditLog {
  id: string;
  model: string;
  latency: number;
  cost: number;
  promptHash: string;
  success: boolean;
  timestamp: string;
}

export interface KnowledgeBaseEntry {
  id: string;
  sasSnippet: string;
  pythonTranslation: string;
  category: string;
  confidence: number;
  createdAt: string;
  updatedAt: string;
}

export interface KBChangelogEntry {
  id: string;
  entryId: string;
  action: "add" | "edit" | "rollback" | "delete";
  user: string;
  timestamp: string;
  description: string;
}

export interface FileRegistryEntry {
  id: string;
  fileName: string;
  status: ConversionStatus;
  dependencies: string[];
  lineage: string[];
}

export interface PipelineConfig {
  maxRetries: number;
  timeout: number;
  checkpointInterval: number;
}

export interface SystemService {
  name: string;
  status: "online" | "degraded" | "offline";
  latency: number;
  uptime: number;
}

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

export interface Notification {
  id: string;
  userId: string;
  title: string;
  message: string;
  type: "info" | "success" | "warning" | "error";
  read: boolean;
  createdAt: string;
}

export interface Correction {
  id: string;
  conversionId: string;
  correctedCode: string;
  explanation: string;
  category: string;
  submittedAt: string;
}

export interface AnalyticsData {
  date: string;
  conversions: number;
  successRate: number;
  avgLatency: number;
  failures: number;
}
