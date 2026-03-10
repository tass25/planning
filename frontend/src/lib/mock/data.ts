import type {
  Conversion, AuditLog, KnowledgeBaseEntry, KBChangelogEntry,
  FileRegistryEntry, SystemService, User, AnalyticsData, Partition
} from "@/types";

const SAS_SAMPLE = `/* Sample SAS Program */
data work.customers;
  set sasdata.raw_customers;
  where age >= 18 and status = 'active';
  length full_name $100;
  full_name = catx(' ', first_name, last_name);
  
  if income > 100000 then segment = 'Premium';
  else if income > 50000 then segment = 'Standard';
  else segment = 'Basic';
  
  format join_date mmddyy10.;
run;

proc sql;
  create table work.summary as
  select segment,
         count(*) as customer_count,
         mean(income) as avg_income,
         sum(total_spend) as total_revenue
  from work.customers
  group by segment
  order by total_revenue desc;
quit;

proc print data=work.summary noobs;
  title 'Customer Segment Summary';
run;`;

const PYTHON_SAMPLE = `# Converted Python Code
import pandas as pd
from typing import Optional

def process_customers(raw_customers: pd.DataFrame) -> pd.DataFrame:
    """Process raw customer data with segmentation."""
    customers = raw_customers[
        (raw_customers['age'] >= 18) & 
        (raw_customers['status'] == 'active')
    ].copy()
    
    customers['full_name'] = (
        customers['first_name'] + ' ' + customers['last_name']
    )
    
    conditions = [
        customers['income'] > 100000,
        customers['income'] > 50000,
    ]
    choices = ['Premium', 'Standard']
    customers['segment'] = pd.np.select(
        conditions, choices, default='Basic'
    )
    
    customers['join_date'] = pd.to_datetime(
        customers['join_date']
    ).dt.strftime('%m/%d/%Y')
    
    return customers


def create_summary(customers: pd.DataFrame) -> pd.DataFrame:
    """Create customer segment summary."""
    summary = (
        customers
        .groupby('segment')
        .agg(
            customer_count=('segment', 'count'),
            avg_income=('income', 'mean'),
            total_revenue=('total_spend', 'sum')
        )
        .sort_values('total_revenue', ascending=False)
        .reset_index()
    )
    
    print("Customer Segment Summary")
    print(summary.to_string(index=False))
    
    return summary`;

const stages = ["file_process","sas_partition","strategy_select","translate","validate","repair","merge","finalize"] as const;

function makeStages(status: "completed" | "running" | "failed") {
  const completedCount = status === "completed" ? 8 : status === "running" ? Math.floor(Math.random() * 5) + 2 : Math.floor(Math.random() * 4) + 1;
  return stages.map((s, i) => ({
    stage: s,
    status: i < completedCount ? "completed" as const : i === completedCount ? (status === "running" ? "running" as const : "failed" as const) : "pending" as const,
    latency: i < completedCount ? Math.floor(Math.random() * 3000) + 500 : undefined,
    retryCount: Math.random() > 0.8 ? 1 : 0,
    warnings: Math.random() > 0.7 ? ["Potential data type mismatch detected"] : [],
  }));
}

export const mockConversions: Conversion[] = [
  { id: "conv-001", fileName: "customer_segmentation.sas", status: "completed", runtime: "python", duration: 45.2, accuracy: 97.3, createdAt: "2026-03-07T14:23:00Z", stages: makeStages("completed"), sasCode: SAS_SAMPLE, pythonCode: PYTHON_SAMPLE, validationReport: "All 24 test cases passed.\nCode coverage: 94%\nNo runtime errors detected.\n\nStructural validation: PASS\nSemantic validation: PASS\nOutput comparison: PASS", mergeReport: "3 modules merged successfully.\nNo conflicts detected.\nDependency graph resolved." },
  { id: "conv-002", fileName: "risk_model_v3.sas", status: "completed", runtime: "python", duration: 128.7, accuracy: 94.1, createdAt: "2026-03-07T10:15:00Z", stages: makeStages("completed"), sasCode: SAS_SAMPLE, pythonCode: PYTHON_SAMPLE },
  { id: "conv-003", fileName: "etl_pipeline_main.sas", status: "running", runtime: "python", duration: 0, accuracy: 0, createdAt: "2026-03-08T08:00:00Z", stages: makeStages("running") },
  { id: "conv-004", fileName: "quarterly_report.sas", status: "completed", runtime: "python", duration: 22.1, accuracy: 99.1, createdAt: "2026-03-06T16:45:00Z", stages: makeStages("completed"), sasCode: SAS_SAMPLE, pythonCode: PYTHON_SAMPLE },
  { id: "conv-005", fileName: "data_validation_checks.sas", status: "failed", runtime: "python", duration: 67.8, accuracy: 0, createdAt: "2026-03-06T09:30:00Z", stages: makeStages("failed") },
  { id: "conv-006", fileName: "macro_library.sas", status: "completed", runtime: "python", duration: 89.3, accuracy: 91.5, createdAt: "2026-03-05T11:20:00Z", stages: makeStages("completed"), sasCode: SAS_SAMPLE, pythonCode: PYTHON_SAMPLE },
  { id: "conv-007", fileName: "statistical_analysis.sas", status: "partial", runtime: "python", duration: 55.0, accuracy: 78.2, createdAt: "2026-03-05T08:10:00Z", stages: makeStages("completed") },
  { id: "conv-008", fileName: "format_catalog.sas", status: "completed", runtime: "python", duration: 15.4, accuracy: 98.7, createdAt: "2026-03-04T14:00:00Z", stages: makeStages("completed"), sasCode: SAS_SAMPLE, pythonCode: PYTHON_SAMPLE },
  { id: "conv-009", fileName: "ods_output_gen.sas", status: "completed", runtime: "python", duration: 33.2, accuracy: 95.8, createdAt: "2026-03-04T09:45:00Z", stages: makeStages("completed") },
  { id: "conv-010", fileName: "proc_mixed_model.sas", status: "completed", runtime: "python", duration: 71.6, accuracy: 92.4, createdAt: "2026-03-03T15:30:00Z", stages: makeStages("completed") },
];

export const mockPartitions: Partition[] = [
  { id: "part-001", conversionId: "conv-001", sasBlock: "data work.customers;\n  set sasdata.raw_customers;\n  where age >= 18;\nrun;", riskLevel: "low", strategy: "direct_translation", translatedCode: "customers = raw_customers[raw_customers['age'] >= 18].copy()" },
  { id: "part-002", conversionId: "conv-001", sasBlock: "proc sql;\n  create table summary as\n  select segment, count(*) as n\n  from customers\n  group by segment;\nquit;", riskLevel: "medium", strategy: "pandas_groupby", translatedCode: "summary = customers.groupby('segment').size().reset_index(name='n')" },
  { id: "part-003", conversionId: "conv-001", sasBlock: "%macro generate_report(ds=, var=);\n  proc means data=&ds;\n    var &var;\n  run;\n%mend;", riskLevel: "high", strategy: "function_conversion", translatedCode: "def generate_report(ds: pd.DataFrame, var: str):\n    return ds[var].describe()" },
];

export const mockAuditLogs: AuditLog[] = Array.from({ length: 25 }, (_, i) => ({
  id: `audit-${String(i + 1).padStart(3, "0")}`,
  model: ["gpt-4-turbo", "claude-3.5-sonnet", "codellama-70b", "deepseek-coder"][i % 4],
  latency: Math.floor(Math.random() * 5000) + 800,
  cost: parseFloat((Math.random() * 0.5 + 0.01).toFixed(4)),
  promptHash: `0x${Math.random().toString(16).slice(2, 10)}`,
  success: Math.random() > 0.15,
  timestamp: new Date(Date.now() - i * 3600000).toISOString(),
}));

export const mockKnowledgeBase: KnowledgeBaseEntry[] = [
  { id: "kb-001", sasSnippet: "proc sort data=mydata; by var1 var2; run;", pythonTranslation: "mydata = mydata.sort_values(['var1', 'var2'])", category: "data_manipulation", confidence: 0.98, createdAt: "2026-02-01T10:00:00Z", updatedAt: "2026-03-01T10:00:00Z" },
  { id: "kb-002", sasSnippet: "proc means data=mydata mean std; var income; run;", pythonTranslation: "mydata['income'].agg(['mean', 'std'])", category: "statistics", confidence: 0.95, createdAt: "2026-02-05T10:00:00Z", updatedAt: "2026-02-28T10:00:00Z" },
  { id: "kb-003", sasSnippet: "proc freq data=mydata; tables var1*var2 / chisq; run;", pythonTranslation: "pd.crosstab(mydata['var1'], mydata['var2'])\nfrom scipy.stats import chi2_contingency", category: "statistics", confidence: 0.89, createdAt: "2026-02-10T10:00:00Z", updatedAt: "2026-02-25T10:00:00Z" },
  { id: "kb-004", sasSnippet: "data out; merge a(in=ina) b(in=inb); by id; if ina and inb; run;", pythonTranslation: "out = pd.merge(a, b, on='id', how='inner')", category: "data_manipulation", confidence: 0.97, createdAt: "2026-02-12T10:00:00Z", updatedAt: "2026-03-05T10:00:00Z" },
  { id: "kb-005", sasSnippet: "%let threshold = 0.05;", pythonTranslation: "threshold = 0.05", category: "macro", confidence: 0.99, createdAt: "2026-02-15T10:00:00Z", updatedAt: "2026-02-15T10:00:00Z" },
  { id: "kb-006", sasSnippet: "proc transpose data=long out=wide; by group; id time; var value; run;", pythonTranslation: "wide = long.pivot(index='group', columns='time', values='value')", category: "data_manipulation", confidence: 0.93, createdAt: "2026-02-18T10:00:00Z", updatedAt: "2026-03-02T10:00:00Z" },
];

export const mockKBChangelog: KBChangelogEntry[] = [
  { id: "cl-001", entryId: "kb-004", action: "edit", user: "sarah.chen@codara.dev", timestamp: "2026-03-05T10:00:00Z", description: "Updated merge translation to use how='inner' explicitly" },
  { id: "cl-002", entryId: "kb-003", action: "edit", user: "marcus.johnson@codara.dev", timestamp: "2026-02-28T14:30:00Z", description: "Added chi-squared test import from scipy" },
  { id: "cl-003", entryId: "kb-006", action: "add", user: "sarah.chen@codara.dev", timestamp: "2026-02-18T10:00:00Z", description: "Added PROC TRANSPOSE to pivot translation" },
  { id: "cl-004", entryId: "kb-002", action: "rollback", user: "admin@codara.dev", timestamp: "2026-02-15T16:00:00Z", description: "Rolled back incorrect agg syntax" },
  { id: "cl-005", entryId: "kb-005", action: "add", user: "marcus.johnson@codara.dev", timestamp: "2026-02-15T10:00:00Z", description: "Added macro variable assignment pattern" },
];

export const mockFileRegistry: FileRegistryEntry[] = [
  { id: "fr-001", fileName: "customer_segmentation.sas", status: "completed", dependencies: ["format_catalog.sas", "macro_library.sas"], lineage: ["raw_customers.csv"] },
  { id: "fr-002", fileName: "risk_model_v3.sas", status: "completed", dependencies: ["statistical_analysis.sas"], lineage: ["risk_factors.csv", "historical_data.csv"] },
  { id: "fr-003", fileName: "etl_pipeline_main.sas", status: "running", dependencies: ["format_catalog.sas", "data_validation_checks.sas"], lineage: ["source_system_a.db", "source_system_b.db"] },
  { id: "fr-004", fileName: "macro_library.sas", status: "completed", dependencies: [], lineage: [] },
  { id: "fr-005", fileName: "data_validation_checks.sas", status: "failed", dependencies: ["macro_library.sas"], lineage: ["validation_rules.json"] },
];

export const mockSystemServices: SystemService[] = [
  { name: "Redis", status: "online", latency: 2, uptime: 99.97 },
  { name: "DuckDB", status: "online", latency: 8, uptime: 99.95 },
  { name: "LLM Provider (OpenAI)", status: "online", latency: 340, uptime: 99.8 },
  { name: "LLM Provider (Anthropic)", status: "degraded", latency: 1200, uptime: 98.5 },
  { name: "Object Storage", status: "online", latency: 15, uptime: 99.99 },
  { name: "Task Queue", status: "online", latency: 5, uptime: 99.92 },
];

export const mockUsers: User[] = [
  { id: "u-001", email: "sarah.chen@acme.com", name: "Sarah Chen", role: "admin", conversionCount: 142, status: "active", createdAt: "2025-11-01T10:00:00Z" },
  { id: "u-002", email: "marcus.johnson@acme.com", name: "Marcus Johnson", role: "user", conversionCount: 87, status: "active", createdAt: "2025-12-15T10:00:00Z" },
  { id: "u-003", email: "aisha.patel@acme.com", name: "Aisha Patel", role: "user", conversionCount: 234, status: "active", createdAt: "2025-11-20T10:00:00Z" },
  { id: "u-004", email: "james.wu@acme.com", name: "James Wu", role: "viewer", conversionCount: 12, status: "inactive", createdAt: "2026-01-10T10:00:00Z" },
  { id: "u-005", email: "elena.rodriguez@acme.com", name: "Elena Rodriguez", role: "user", conversionCount: 56, status: "active", createdAt: "2026-01-25T10:00:00Z" },
  { id: "u-006", email: "dev.team@acme.com", name: "Dev Team (Service)", role: "admin", conversionCount: 1024, status: "active", createdAt: "2025-10-01T10:00:00Z" },
];

export const mockAnalytics: AnalyticsData[] = Array.from({ length: 30 }, (_, i) => {
  const date = new Date(2026, 1, 7 + i);
  return {
    date: date.toISOString().split("T")[0],
    conversions: Math.floor(Math.random() * 30) + 10,
    successRate: parseFloat((Math.random() * 15 + 82).toFixed(1)),
    avgLatency: parseFloat((Math.random() * 40 + 20).toFixed(1)),
    failures: Math.floor(Math.random() * 5),
  };
});

export const failureModes = [
  { name: "Unsupported PROC", value: 35 },
  { name: "Macro complexity", value: 25 },
  { name: "Data type mismatch", value: 18 },
  { name: "Missing dependency", value: 12 },
  { name: "Syntax ambiguity", value: 10 },
];
