/* Mock data for Codara prototype */

const MockData = (() => {

  // ── Conversions ──────────────────────────────────────────────
  const conversions = [
    {
      id: "cv_8a3f",
      fileName: "claims_etl_v3.sas",
      status: "completed",
      createdAt: "2026-05-13T09:42:00Z",
      duration: 47.3,
      runtime: "Python · pandas",
      complexity: "high",
      lines: 1842,
      pyLines: 2104,
      coverage: 96,
      modules: ["data step", "proc sql", "macro"],
      author: "Maya Chen",
      project: "Claims Pipeline 2026",
    },
    {
      id: "cv_8a40",
      fileName: "monthly_rollup.sas",
      status: "running",
      createdAt: "2026-05-13T10:11:00Z",
      duration: 0,
      runtime: "Python · pandas",
      complexity: "medium",
      lines: 612,
      pyLines: 0,
      coverage: 0,
      modules: ["data step", "proc means"],
      author: "Maya Chen",
      project: "Claims Pipeline 2026",
    },
    {
      id: "cv_8a3e",
      fileName: "risk_scoring.sas",
      status: "completed",
      createdAt: "2026-05-12T16:20:00Z",
      duration: 28.1,
      runtime: "Python · pandas",
      complexity: "medium",
      lines: 904,
      pyLines: 1086,
      coverage: 91,
      modules: ["proc sql", "data step"],
      author: "David Park",
      project: "Risk Model R-12",
    },
    {
      id: "cv_8a3d",
      fileName: "policy_eligibility.sas",
      status: "partial",
      createdAt: "2026-05-12T14:05:00Z",
      duration: 51.8,
      runtime: "Python · pandas",
      complexity: "high",
      lines: 1428,
      pyLines: 1620,
      coverage: 78,
      modules: ["macro", "data step", "proc sql"],
      author: "Maya Chen",
      project: "Claims Pipeline 2026",
    },
    {
      id: "cv_8a3c",
      fileName: "actuarial_lookup.sas",
      status: "completed",
      createdAt: "2026-05-12T11:30:00Z",
      duration: 12.4,
      runtime: "Python · pandas",
      complexity: "low",
      lines: 234,
      pyLines: 287,
      coverage: 99,
      modules: ["data step"],
      author: "Priya Iyer",
      project: "Risk Model R-12",
    },
    {
      id: "cv_8a3b",
      fileName: "premium_calc.sas",
      status: "failed",
      createdAt: "2026-05-11T18:42:00Z",
      duration: 8.2,
      runtime: "Python · pandas",
      complexity: "high",
      lines: 2104,
      pyLines: 0,
      coverage: 0,
      modules: ["macro", "data step", "proc sql", "proc means"],
      author: "David Park",
      project: "Premium 2026",
    },
    {
      id: "cv_8a3a",
      fileName: "geo_segmentation.sas",
      status: "completed",
      createdAt: "2026-05-11T13:15:00Z",
      duration: 33.7,
      runtime: "Python · pandas",
      complexity: "medium",
      lines: 718,
      pyLines: 842,
      coverage: 94,
      modules: ["proc sql", "data step"],
      author: "Priya Iyer",
      project: "Premium 2026",
    },
    {
      id: "cv_8a39",
      fileName: "loss_triangles.sas",
      status: "completed",
      createdAt: "2026-05-10T17:50:00Z",
      duration: 89.2,
      runtime: "Python · pandas",
      complexity: "high",
      lines: 2870,
      pyLines: 3214,
      coverage: 88,
      modules: ["macro", "data step", "proc sql", "proc transpose"],
      author: "Maya Chen",
      project: "Reserves Q2",
    },
  ];

  // ── Pipeline stages for active conversion ───────────────────
  const pipelineStages = [
    { stage: "file_process", label: "File Analysis", desc: "Parsing 612 lines of SAS, mapping macro scope", status: "completed", latency: 412 },
    { stage: "sas_partition", label: "Code Chunking", desc: "Split into 7 logical units (data steps, procs, macros)", status: "completed", latency: 218 },
    { stage: "strategy_select", label: "Dependency Resolution", desc: "Resolved 14 cross-references, ordered execution graph", status: "completed", latency: 891 },
    { stage: "translate", label: "Data Lineage", desc: "Traced WORK.* → final outputs, 23 intermediate tables", status: "completed", latency: 1340 },
    { stage: "validate", label: "LLM Translation", desc: "Calling claude-haiku-4-5 on chunk 4 of 7…", status: "running", latency: null },
    { stage: "repair", label: "Syntax Validation", desc: "Waiting to validate generated Python AST", status: "pending", latency: null },
    { stage: "merge", label: "Module Assembly", desc: "Waiting to assemble final module", status: "pending", latency: null },
    { stage: "finalize", label: "Finalization", desc: "Waiting to package results & write artifacts", status: "pending", latency: null },
  ];

  // ── Users ─────────────────────────────────────────────────────
  const users = [
    { id: "u_001", name: "Maya Chen", email: "maya.chen@codara.dev", role: "admin", status: "active", lastSeen: "now", conversions: 142, joined: "2025-09-12" },
    { id: "u_002", name: "David Park", email: "david.park@codara.dev", role: "user", status: "active", lastSeen: "2m ago", conversions: 87, joined: "2025-11-04" },
    { id: "u_003", name: "Priya Iyer", email: "priya.iyer@codara.dev", role: "user", status: "active", lastSeen: "14m ago", conversions: 51, joined: "2026-01-18" },
    { id: "u_004", name: "Jonas Albrecht", email: "jonas@codara.dev", role: "user", status: "active", lastSeen: "1h ago", conversions: 33, joined: "2026-02-22" },
    { id: "u_005", name: "Lin Wei", email: "lin.wei@codara.dev", role: "user", status: "active", lastSeen: "3h ago", conversions: 21, joined: "2026-03-08" },
    { id: "u_006", name: "Camille Roux", email: "camille@codara.dev", role: "user", status: "invited", lastSeen: "—", conversions: 0, joined: "2026-05-09" },
    { id: "u_007", name: "Sam Okafor", email: "sam.okafor@codara.dev", role: "user", status: "suspended", lastSeen: "12d ago", conversions: 8, joined: "2026-01-30" },
  ];

  // ── 30-day analytics ────────────────────────────────────────
  const analytics = (() => {
    const out = [];
    const start = new Date("2026-04-14T00:00:00Z");
    for (let i = 0; i < 30; i++) {
      const d = new Date(start.getTime() + i * 86400000);
      const base = 8 + Math.sin(i / 3.4) * 3 + i * 0.4;
      const conv = Math.max(3, Math.round(base + (Math.random() - 0.5) * 4));
      const fail = Math.max(0, Math.round(conv * (0.04 + Math.random() * 0.05)));
      const partial = Math.max(0, Math.round(conv * (0.06 + Math.random() * 0.04)));
      const lat = 18 + Math.sin(i / 5) * 6 + Math.random() * 5;
      const cost = conv * (0.18 + Math.random() * 0.12);
      out.push({
        date: d.toISOString().slice(0, 10),
        conversions: conv,
        failures: fail,
        partial,
        completed: conv - fail - partial,
        avgLatency: +lat.toFixed(1),
        cost: +cost.toFixed(2),
        tokens: Math.round(conv * (3800 + Math.random() * 1200)),
      });
    }
    return out;
  })();

  // ── System services ─────────────────────────────────────────
  const services = [
    { name: "Translation Worker", status: "online", latency: 142, uptime: 99.97, region: "us-east-1" },
    { name: "Validation Engine", status: "online", latency: 89, uptime: 99.99, region: "us-east-1" },
    { name: "Knowledge Base API", status: "online", latency: 56, uptime: 100.0, region: "us-east-1" },
    { name: "LLM Gateway · Anthropic", status: "online", latency: 412, uptime: 99.92, region: "global" },
    { name: "LLM Gateway · OpenAI", status: "degraded", latency: 1830, uptime: 98.4, region: "global" },
    { name: "Storage · S3", status: "online", latency: 34, uptime: 99.99, region: "us-east-1" },
    { name: "Postgres Primary", status: "online", latency: 12, uptime: 100.0, region: "us-east-1" },
    { name: "Redis Cache", status: "online", latency: 4, uptime: 100.0, region: "us-east-1" },
  ];

  // ── Audit log entries ───────────────────────────────────────
  const auditLogs = (() => {
    const verbs = [
      { v: "translate", model: "claude-haiku-4-5", who: "system" },
      { v: "validate", model: "claude-haiku-4-5", who: "system" },
      { v: "repair", model: "claude-sonnet-4", who: "system" },
      { v: "user.login", model: "—", who: "Maya Chen" },
      { v: "kb.publish", model: "—", who: "Maya Chen" },
      { v: "user.invite", model: "—", who: "Maya Chen" },
      { v: "translate", model: "claude-sonnet-4", who: "system" },
      { v: "translate", model: "claude-haiku-4-5", who: "system" },
      { v: "pipeline.config.update", model: "—", who: "Maya Chen" },
    ];
    const out = [];
    for (let i = 0; i < 38; i++) {
      const v = verbs[i % verbs.length];
      const t = new Date(Date.now() - i * 420000 - Math.random() * 90000);
      out.push({
        id: "log_" + (8000 - i),
        timestamp: t.toISOString(),
        action: v.v,
        model: v.model,
        actor: v.who,
        tokensIn: v.model === "—" ? 0 : Math.round(2000 + Math.random() * 6000),
        tokensOut: v.model === "—" ? 0 : Math.round(1100 + Math.random() * 4000),
        cost: v.model === "—" ? 0 : +(0.018 + Math.random() * 0.14).toFixed(3),
        latency: v.model === "—" ? 0 : Math.round(280 + Math.random() * 2400),
        status: i % 13 === 6 ? "failed" : "ok",
        target: ["claims_etl_v3.sas","monthly_rollup.sas","risk_scoring.sas","policy_eligibility.sas"][i % 4],
      });
    }
    return out;
  })();

  // ── Knowledge Base patterns ──────────────────────────────────
  const kbPatterns = [
    {
      id: "kb_001",
      title: "PROC MEANS → pandas groupby.agg",
      category: "Aggregation",
      sas: "proc means data=claims;\n  class region;\n  var loss_amount;\n  output out=summary mean=avg_loss sum=total_loss;\nrun;",
      py: "summary = (\n    claims.groupby('region')['loss_amount']\n    .agg(avg_loss='mean', total_loss='sum')\n    .reset_index()\n)",
      uses: 1842,
      coverage: 0.98,
      updated: "2026-04-22",
      status: "stable",
    },
    {
      id: "kb_002",
      title: "PROC SQL JOIN → DataFrame merge",
      category: "Joins",
      sas: "proc sql;\n  create table joined as\n  select a.*, b.region\n  from claims a\n  left join geo b on a.zip = b.zip;\nquit;",
      py: "joined = claims.merge(\n    geo[['zip', 'region']],\n    on='zip',\n    how='left',\n)",
      uses: 1204,
      coverage: 0.99,
      updated: "2026-04-19",
      status: "stable",
    },
    {
      id: "kb_003",
      title: "%MACRO with parameters → Python function",
      category: "Macros",
      sas: "%macro flag_high(thresh=);\n  data flagged;\n    set claims;\n    high = (loss_amount > &thresh);\n  run;\n%mend;",
      py: "def flag_high(claims, thresh):\n    out = claims.copy()\n    out['high'] = out['loss_amount'] > thresh\n    return out",
      uses: 612,
      coverage: 0.94,
      updated: "2026-05-02",
      status: "stable",
    },
    {
      id: "kb_004",
      title: "PROC TRANSPOSE → pivot/melt",
      category: "Reshape",
      sas: "proc transpose data=monthly out=wide;\n  by policy_id;\n  id month;\n  var amount;\nrun;",
      py: "wide = monthly.pivot(\n    index='policy_id',\n    columns='month',\n    values='amount',\n).reset_index()",
      uses: 487,
      coverage: 0.96,
      updated: "2026-04-11",
      status: "stable",
    },
    {
      id: "kb_005",
      title: "DATA step RETAIN → cumulative groupby",
      category: "Stateful",
      sas: "data running;\n  set sales;\n  retain cum 0;\n  cum + amount;\nrun;",
      py: "running = sales.copy()\nrunning['cum'] = running['amount'].cumsum()",
      uses: 318,
      coverage: 0.88,
      updated: "2026-03-28",
      status: "review",
    },
    {
      id: "kb_006",
      title: "PROC FREQ → value_counts + crosstab",
      category: "Frequency",
      sas: "proc freq data=claims;\n  tables region * loss_band;\nrun;",
      py: "freq = pd.crosstab(\n    claims['region'],\n    claims['loss_band'],\n)",
      uses: 264,
      coverage: 0.97,
      updated: "2026-04-04",
      status: "stable",
    },
  ];

  // ── Notifications (NEW) ─────────────────────────────────────
  const notifications = [
    { id: "n1", kind: "success", title: "claims_etl_v3.sas converted", body: "96% test coverage · 47s · Ready to review", at: "2m", read: false, link: "/workspace/cv_8a3f" },
    { id: "n2", kind: "warning", title: "policy_eligibility.sas — partial conversion", body: "3 macro warnings need review", at: "1h", read: false, link: "/workspace/cv_8a3d" },
    { id: "n3", kind: "info", title: "New KB pattern published", body: "Maya added “PROC TABULATE → pivot_table”", at: "3h", read: false, link: "/knowledge-base" },
    { id: "n4", kind: "danger", title: "premium_calc.sas failed at chunk 4", body: "LLM Gateway · OpenAI returned 503 — retry queued", at: "1d", read: true, link: "/admin/error-queue" },
    { id: "n5", kind: "info", title: "Comment from David Park", body: "“Nice catch on the retain block — merging.”", at: "1d", read: true, link: "/workspace/cv_8a3e" },
    { id: "n6", kind: "success", title: "Monthly cost report ready", body: "May tracking 22% under budget", at: "2d", read: true, link: "/admin/cost" },
  ];

  // ── Projects (NEW) — group related .sas files ─────────────
  const projects = [
    { id: "p1", name: "Claims Pipeline 2026", files: 28, converted: 24, owner: "Maya Chen", color: "accent", updated: "2m ago", status: "active" },
    { id: "p2", name: "Risk Model R-12", files: 14, converted: 12, owner: "David Park", color: "secondary", updated: "3h ago", status: "active" },
    { id: "p3", name: "Premium 2026", files: 11, converted: 7, owner: "Priya Iyer", color: "info", updated: "1d ago", status: "active" },
    { id: "p4", name: "Reserves Q2", files: 9, converted: 9, owner: "Maya Chen", color: "success", updated: "4d ago", status: "shipped" },
    { id: "p5", name: "Legacy ETL 2018", files: 42, converted: 8, owner: "Jonas Albrecht", color: "warning", updated: "1w ago", status: "active" },
  ];

  // ── Error queue (NEW) ───────────────────────────────────────
  const errorQueue = [
    { id: "e1", file: "premium_calc.sas", stage: "translate", error: "LLM Gateway timeout (chunk 4/12)", model: "gpt-4o", retries: 2, age: "12m", severity: "high", author: "David Park" },
    { id: "e2", file: "legacy_macro_bundle.sas", stage: "sas_partition", error: "Unresolved macro %include path", model: "—", retries: 0, age: "1h", severity: "medium", author: "Jonas Albrecht" },
    { id: "e3", file: "annuity_calc.sas", stage: "validate", error: "Generated Python failed AST parse", model: "claude-haiku-4-5", retries: 1, age: "3h", severity: "medium", author: "Priya Iyer" },
    { id: "e4", file: "reserves_old.sas", stage: "merge", error: "Module assembly: 2 functions named `compute`", model: "—", retries: 0, age: "4h", severity: "low", author: "Maya Chen" },
  ];

  // ── Prompt templates (NEW) ──────────────────────────────────
  const promptTemplates = [
    { id: "pt1", name: "DATA-step translation", version: "v4.2", model: "claude-sonnet-4", uses: 4_812, lastEdited: "2d ago", author: "Maya Chen", status: "active" },
    { id: "pt2", name: "PROC SQL translation", version: "v3.1", model: "claude-haiku-4-5", uses: 3_211, lastEdited: "5d ago", author: "Maya Chen", status: "active" },
    { id: "pt3", name: "Macro expansion", version: "v2.0", model: "claude-sonnet-4", uses: 980, lastEdited: "1w ago", author: "David Park", status: "active" },
    { id: "pt4", name: "Syntax repair", version: "v1.8", model: "claude-haiku-4-5", uses: 712, lastEdited: "2w ago", author: "Maya Chen", status: "active" },
    { id: "pt5", name: "DATA-step translation (experimental)", version: "v5.0-beta", model: "claude-sonnet-4-5", uses: 84, lastEdited: "3h ago", author: "Maya Chen", status: "experiment" },
  ];

  // ── KB changelog ────────────────────────────────────────────
  const kbChangelog = [
    { id: "c1", at: "2m ago", who: "Maya Chen", action: "published", target: "PROC TABULATE → pivot_table", note: "Closes 4 long-standing partial conversions" },
    { id: "c2", at: "3h ago", who: "system", action: "auto-suggested", target: "DO loop with %SCAN", note: "Pattern observed in 18 conversions over 30d" },
    { id: "c3", at: "1d ago", who: "David Park", action: "updated", target: "PROC MEANS → groupby.agg", note: "Fixed multi-key class handling" },
    { id: "c4", at: "2d ago", who: "Maya Chen", action: "deprecated", target: "PROC TRANSPOSE (no BY)", note: "Replaced by pivot_table pattern" },
    { id: "c5", at: "3d ago", who: "Priya Iyer", action: "reviewed", target: "RETAIN → cumsum", note: "Flagged for re-review on stateful logic" },
  ];

  // ── Current user ───────────────────────────────────────────
  const currentUser = {
    name: "Maya Chen",
    email: "maya.chen@codara.dev",
    role: "admin",
    initials: "MC",
    timezone: "America/New_York",
    joined: "2025-09-12",
  };

  // ── Cost breakdown (NEW admin) ─────────────────────────────
  const costByModel = [
    { model: "claude-haiku-4-5", calls: 18420, tokens: 92_410_000, cost: 412.84, color: "var(--chart-1)" },
    { model: "claude-sonnet-4",  calls: 4_210,  tokens: 31_240_000, cost: 968.12, color: "var(--chart-2)" },
    { model: "gpt-4o",           calls: 1_122,  tokens: 8_410_000,  cost: 312.04, color: "var(--chart-3)" },
    { model: "claude-sonnet-4-5 (exp)", calls: 84, tokens: 612_000, cost: 21.40, color: "var(--chart-4)" },
  ];

  return {
    conversions, pipelineStages, users, analytics, services,
    auditLogs, kbPatterns, notifications, projects, errorQueue,
    promptTemplates, kbChangelog, currentUser, costByModel,
  };
})();

export const mockData = MockData;
export default MockData;
