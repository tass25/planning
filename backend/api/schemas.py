"""Pydantic schemas matching the Codara UI TypeScript types."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class PipelineStage(str, Enum):
    FILE_PROCESS = "file_process"
    SAS_PARTITION = "sas_partition"
    STRATEGY_SELECT = "strategy_select"
    TRANSLATE = "translate"
    VALIDATE = "validate"
    REPAIR = "repair"
    MERGE = "merge"
    FINALIZE = "finalize"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ConversionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class TargetRuntime(str, Enum):
    PYTHON = "python"


class TestCoverage(str, Enum):
    FULL = "full"
    STRUCTURAL_ONLY = "structural_only"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class ServiceStatus(str, Enum):
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class KBAction(str, Enum):
    ADD = "add"
    EDIT = "edit"
    ROLLBACK = "rollback"
    DELETE = "delete"


# ── Request / Response schemas ────────────────────────────────────────────────

class PipelineStageInfo(BaseModel):
    stage: PipelineStage
    status: StageStatus = StageStatus.PENDING
    latency: Optional[float] = None
    retryCount: int = 0
    warnings: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    startedAt: Optional[str] = None
    completedAt: Optional[str] = None


class SasFileOut(BaseModel):
    id: str
    name: str
    size: int
    modules: list[str] = Field(default_factory=list)
    estimatedComplexity: RiskLevel = RiskLevel.LOW
    uploadedAt: str


class ConversionConfig(BaseModel):
    targetRuntime: TargetRuntime = TargetRuntime.PYTHON
    testCoverage: TestCoverage = TestCoverage.FULL


class ConversionOut(BaseModel):
    id: str
    fileName: str
    status: ConversionStatus
    runtime: TargetRuntime
    duration: float = 0.0
    accuracy: float = 0.0
    createdAt: str
    progress: int = 0
    stages: list[PipelineStageInfo] = Field(default_factory=list)
    sasCode: Optional[str] = None
    pythonCode: Optional[str] = None
    validationReport: Optional[str] = None
    mergeReport: Optional[str] = None


class StartConversionRequest(BaseModel):
    fileIds: list[str]
    config: ConversionConfig


class PartitionOut(BaseModel):
    id: str
    conversionId: str
    sasBlock: str
    riskLevel: RiskLevel
    strategy: str
    translatedCode: str


class AuditLogOut(BaseModel):
    id: str
    model: str
    latency: float
    cost: float
    promptHash: str
    success: bool
    timestamp: str


class KnowledgeBaseEntryOut(BaseModel):
    id: str
    sasSnippet: str
    pythonTranslation: str
    category: str
    confidence: float
    createdAt: str
    updatedAt: str


class KBEntryCreate(BaseModel):
    sasSnippet: str
    pythonTranslation: str
    category: str
    confidence: float = 0.9


class KBEntryUpdate(BaseModel):
    sasSnippet: Optional[str] = None
    pythonTranslation: Optional[str] = None
    category: Optional[str] = None
    confidence: Optional[float] = None


class KBChangelogEntryOut(BaseModel):
    id: str
    entryId: str
    action: KBAction
    user: str
    timestamp: str
    description: str


class FileRegistryEntryOut(BaseModel):
    id: str
    fileName: str
    status: ConversionStatus
    dependencies: list[str] = Field(default_factory=list)
    lineage: list[str] = Field(default_factory=list)


class PipelineConfigOut(BaseModel):
    maxRetries: int = 3
    timeout: int = 300
    checkpointInterval: int = 60


class SystemServiceOut(BaseModel):
    name: str
    status: ServiceStatus
    latency: float
    uptime: float


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: UserRole
    conversionCount: int = 0
    status: UserStatus = UserStatus.ACTIVE
    emailVerified: bool = False
    createdAt: str


class UserUpdate(BaseModel):
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None


class CorrectionCreate(BaseModel):
    correctedCode: str
    explanation: str
    category: str


class CorrectionOut(BaseModel):
    id: str
    conversionId: str
    correctedCode: str
    explanation: str
    category: str
    submittedAt: str


class AnalyticsDataOut(BaseModel):
    date: str
    conversions: int
    successRate: float
    avgLatency: float
    failures: int


class FailureModeOut(BaseModel):
    name: str
    value: int


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str


class AuthResponse(BaseModel):
    user: UserOut
    token: str
    emailVerificationRequired: bool = False


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


class PreferencesUpdate(BaseModel):
    defaultRuntime: Optional[TargetRuntime] = None
    emailNotifications: Optional[bool] = None


class NotificationOut(BaseModel):
    id: str
    userId: str
    title: str
    message: str
    type: str = "info"
    read: bool = False
    createdAt: str


class GitHubCallbackRequest(BaseModel):
    code: str
