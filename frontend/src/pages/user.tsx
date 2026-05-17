import React, { useState, useEffect, useRef, useMemo, useCallback, createContext, useContext } from "react";
import type { ReactNode, CSSProperties } from "react";
import { useConversions, useConversionPolling, useAnalytics, useProjects, uploadFiles, startConversion } from "../lib/hooks";
import type { Conversion, UploadedFile } from "../lib/hooks";
import { Icon, StatCard, StatusBadge, Avatar, AreaChart, AnimatedNumber, CodeBlock } from "../components/ui";
import { Constellation, CodaraMascot, Typewriter } from "../components/ambient";

/* ──────────────────────────────────────────────────────────
   User-facing pages: Dashboard, Conversions, Workspace, History,
   Knowledge Base, Analytics, Settings
   ────────────────────────────────────────────────────────── */



/* ─── DASHBOARD (User) ─────────────────────────────────────── */
function UserDashboard({ navigate, user }) {
  const { data: liveConversions } = useConversions();
  const { data: liveAnalytics } = useAnalytics();
  const { data: liveProjects } = useProjects();
  const conversions = (liveConversions || []).map(c => ({
    ...c, coverage: c.accuracy, project: c.runtime,
    lines: c.sasCode ? c.sasCode.split("\n").length : 0,
  })) as any[];
  const analytics = liveAnalytics || [] as any[];
  const projects = liveProjects || [] as any[];

  const total = conversions.length;
  const completed = conversions.filter(c => c.status === "completed").length;
  const running = conversions.filter(c => c.status === "running").length;
  const coverage = conversions.filter(c => (c as any).accuracy > 0).length > 0
    ? Math.round(conversions.filter(c => (c as any).accuracy > 0).reduce((a, c) => a + ((c as any).accuracy || 0), 0) /
                 conversions.filter(c => (c as any).accuracy > 0).length)
    : 0;

  const greeting = (() => {
    const h = new Date().getHours();
    return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  })();

  const last7 = analytics.length > 0 ? analytics.slice(-7) : [{ date: "", conversions: 0, avgLatency: 0, failures: 0, successRate: 0 }];

  // Parallax: hero offset follows cursor subtly
  const heroRef = React.useRef(null);
  const [par, setPar] = React.useState({ x: 0, y: 0 });
  React.useEffect(() => {
    const onMove = (e) => {
      const el = heroRef.current; if (!el) return;
      const r = el.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const nx = (e.clientX - cx) / r.width;
      const ny = (e.clientY - cy) / r.height;
      setPar({ x: Math.max(-1, Math.min(1, nx)), y: Math.max(-1, Math.min(1, ny)) });
    };
    window.addEventListener("pointermove", onMove);
    return () => window.removeEventListener("pointermove", onMove);
  }, []);

  return (
    <div className="page-in" style={{ display: "flex", flexDirection: "column", gap: 22, maxWidth: 1280 }}>
      {/* Hero */}
      <div ref={heroRef} style={{
        position: "relative", overflow: "hidden",
        borderRadius: "var(--radius-xl)",
        background: "linear-gradient(135deg, color-mix(in srgb, var(--accent) 12%, var(--bg-elev)) 0%, color-mix(in srgb, var(--secondary) 8%, var(--bg-elev)) 100%)",
        border: "1px solid var(--border)",
        padding: 28, minHeight: 280,
        display: "grid", gridTemplateColumns: "1fr 280px", gap: 24, alignItems: "center",
      }}>
        {/* Aurora sweep behind everything */}
        <div className="aurora-sweep"/>
        <Constellation density={0.00012} link={120} speed={0.16}/>
        <div className="dot-grid-fine" style={{ position: "absolute", inset: 0, opacity: 0.35, pointerEvents: "none" }}/>

        {/* Parallax orbs */}
        <div style={{
          position: "absolute", right: -60, top: -60, width: 240, height: 240, borderRadius: "50%",
          background: "radial-gradient(circle, color-mix(in srgb, var(--accent) 18%, transparent), transparent 70%)",
          animation: "float 7s ease-in-out infinite",
          transform: `translate3d(${par.x * -12}px, ${par.y * -12}px, 0)`,
          transition: "transform 0.4s var(--ease-out)",
          pointerEvents: "none",
        }}/>
        <div style={{
          position: "absolute", right: 80, bottom: -40, width: 180, height: 180, borderRadius: "50%",
          background: "radial-gradient(circle, color-mix(in srgb, var(--secondary) 14%, transparent), transparent 70%)",
          animation: "float 9s ease-in-out infinite 1s",
          transform: `translate3d(${par.x * 8}px, ${par.y * 8}px, 0)`,
          transition: "transform 0.4s var(--ease-out)",
          pointerEvents: "none",
        }}/>

        <div style={{ position: "relative", zIndex: 2, maxWidth: 620 }}>
          <div className="eyebrow" style={{ color: "var(--accent)" }}>{greeting}</div>
          <h1 style={{ fontSize: "var(--tw-h1)", fontWeight: 600, marginTop: 6, marginBottom: 8 }}>
            {user.name.split(" ")[0]}, you have {running} active conversion{running === 1 ? "" : "s"}.
          </h1>
          <p className="text-muted" style={{ marginBottom: 4, fontSize: 14, minHeight: 22 }}>
            <Typewriter text={`${completed} files converted this month with ${coverage}% average test coverage.`}
                        speed={18}/>
          </p>
          <p className="text-muted" style={{ marginBottom: 18, fontSize: 14 }}>Upload more SAS, or jump back into your workspace.</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn btn-primary btn-lg" onClick={() => navigate("/conversions")}>
              <Icon name="upload" size={14}/> New conversion
            </button>
            <button className="btn btn-lg" onClick={() => navigate("/workspace")}>
              <Icon name="folder" size={14}/> Open workspace
            </button>
            <button className="btn btn-lg btn-ghost" onClick={() => window.codara?.openNewProject()}>
              <Icon name="layers" size={14}/> New project
            </button>
          </div>
        </div>

        {/* Mascot side */}
        <div style={{ position: "relative", zIndex: 2, display: "flex", justifyContent: "center", alignItems: "center",
                       transform: `translate3d(${par.x * 10}px, ${par.y * 10}px, 0)`,
                       transition: "transform 0.5s var(--ease-out)" }}>
          <CodaraMascot size={200}/>
        </div>
      </div>

      {/* Stats row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }} className="stagger">
        <StatCard label="Total conversions" value={total} delta="+18%" deltaType="up" icon="fileCode"
                  sparkData={last7.map(d => d.conversions)} tone="accent"/>
        <StatCard label="Completed" value={completed} delta="+12%" deltaType="up" icon="checkCircle"
                  sparkData={last7.map(d => d.completed)}/>
        <StatCard label="In progress" value={running} icon="clock"
                  sub={running > 0 ? "monthly_rollup.sas" : "All clear"}/>
        <StatCard label="Avg coverage" value={`${coverage}%`} delta="+4pt" deltaType="up" icon="checkCircle"
                  sparkData={[88, 90, 89, 91, 93, 95, coverage]}/>
      </div>

      {/* Pipeline / Recent split */}
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 14 }}>
        {/* How it works — illustrated steps */}
        <div className="panel" style={{ padding: 22 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <h2 style={{ fontSize: "var(--tw-h2)", fontWeight: 600 }}>Your conversion pipeline</h2>
            <span className="badge"><span className="live-dot"/> 8-stage pipeline</span>
          </div>

          <div style={{ position: "relative", display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14 }}>
            {[
              { n: "01", title: "Upload SAS", desc: "Drop .sas files, we'll analyze structure & dependencies", icon: "upload", color: "var(--accent)" },
              { n: "02", title: "Review diff", desc: "Side-by-side SAS → Python with highlighted translations", icon: "git", color: "var(--secondary)" },
              { n: "03", title: "Export Python", desc: "Production-ready code with tests, documented & typed", icon: "rocket", color: "var(--success)" },
            ].map((s, i) => (
              <div key={i} style={{
                position: "relative", padding: 16,
                borderRadius: "var(--radius-lg)",
                background: "var(--bg-elev)",
                border: "1px solid var(--border)",
                overflow: "hidden",
              }}>
                <div className="mono" style={{ fontSize: 32, lineHeight: 1, color: s.color, opacity: 0.18, fontWeight: 700,
                                                position: "absolute", top: 8, right: 12 }}>{s.n}</div>
                <div style={{
                  width: 32, height: 32, borderRadius: "var(--radius)", marginBottom: 12,
                  background: `color-mix(in srgb, ${s.color} 14%, transparent)`,
                  color: s.color, display: "inline-flex", alignItems: "center", justifyContent: "center",
                }}><Icon name={s.icon} size={15}/></div>
                <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>{s.title}</div>
                <div className="text-muted" style={{ fontSize: 12.5, lineHeight: 1.5 }}>{s.desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Sparkline + activity */}
        <div className="panel" style={{ padding: 22 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <h2 style={{ fontSize: "var(--tw-h2)", fontWeight: 600 }}>This week</h2>
            <button className="btn btn-sm btn-ghost" onClick={() => navigate("/analytics")}>
              Analytics <Icon name="arrowRight" size={11}/>
            </button>
          </div>
          <AreaChart
            data={last7}
            keys={[
              { key: "conversions", color: "var(--chart-1)" },
            ]}
            height={140}
            showGrid={false}
            showYAxis={false}
          />
          <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, fontSize: 12 }}>
            <div>
              <div className="text-subtle eyebrow">Files</div>
              <div style={{ fontWeight: 600, fontSize: 18 }}>{last7.reduce((a, d) => a + d.conversions, 0)}</div>
            </div>
            <div>
              <div className="text-subtle eyebrow">Avg latency</div>
              <div style={{ fontWeight: 600, fontSize: 18 }}>
                {(last7.reduce((a, d) => a + d.avgLatency, 0) / last7.length).toFixed(1)}s
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Recent files + Projects */}
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 14 }}>
        <div className="panel" style={{ overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
            <h2 style={{ fontSize: 14, fontWeight: 600 }}>Recent conversions</h2>
            <button className="btn btn-sm btn-ghost" onClick={() => navigate("/history")}>
              View all <Icon name="arrowRight" size={11}/>
            </button>
          </div>
          {conversions.slice(0, 5).map((c, i) => (
            <button key={c.id} onClick={() => navigate(`/workspace/${c.id}`)} className="row-item">
              <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0, flex: 1 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: "var(--radius)",
                  background: "var(--surface-2)", display: "inline-flex", alignItems: "center", justifyContent: "center",
                }}><Icon name="fileCode" size={14} className="text-muted"/></div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 500, fontSize: 13.5 }}>{c.fileName}</div>
                  <div className="text-subtle" style={{ fontSize: 11.5, display: "flex", gap: 10, alignItems: "center" }}>
                    <span>{c.project}</span>
                    <span>·</span>
                    <span className="mono">{c.lines.toLocaleString()} lines</span>
                    <span>·</span>
                    <span>{new Date(c.createdAt).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
                  </div>
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {c.coverage > 0 && <span className="mono text-muted" style={{ fontSize: 11 }}>{c.coverage}%</span>}
                <StatusBadge status={c.status}/>
                <Icon name="chevronRight" size={13} className="text-subtle"/>
              </div>
            </button>
          ))}
          <style>{`
            .row-item {
              width: 100%; padding: 12px 20px; display: flex; align-items: center; gap: 12px;
              border-bottom: 1px solid var(--border);
              transition: background 0.16s var(--ease-out);
            }
            .row-item:last-child { border-bottom: 0; }
            .row-item:hover { background: var(--surface-2); }
          `}</style>
        </div>

        <div className="panel" style={{ padding: 20 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <h2 style={{ fontSize: 14, fontWeight: 600 }}>Projects</h2>
            <button className="btn btn-sm btn-ghost" onClick={() => navigate("/projects")}>
              All <Icon name="arrowRight" size={11}/>
            </button>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {projects.slice(0, 4).map(p => (
              <button key={p.id} onClick={() => navigate("/projects")} style={{
                display: "flex", alignItems: "center", gap: 12, padding: "10px 12px",
                borderRadius: "var(--radius)", border: "1px solid var(--border)",
                background: "var(--bg-elev)", textAlign: "left", width: "100%",
                transition: "transform 0.16s var(--ease-out), border-color 0.16s",
              }} onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--border-strong)"; e.currentTarget.style.transform = "translateY(-1px)"; }}
                 onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.transform = "translateY(0)"; }}>
                <div style={{
                  width: 36, height: 36, borderRadius: "var(--radius)",
                  background: `color-mix(in srgb, var(--${p.color}) 18%, transparent)`,
                  color: `var(--${p.color})`,
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                }}><Icon name="layers" size={14}/></div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, fontSize: 13 }}>{p.name}</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
                    <div style={{ height: 4, background: "var(--surface-2)", borderRadius: 2, flex: 1, overflow: "hidden" }}>
                      <div style={{
                        width: `${p.files > 0 ? (p.converted/p.files)*100 : 0}%`, height: "100%",
                        background: `var(--${p.color || "accent"})`,
                        transition: "width 1s var(--ease-out)",
                      }}/>
                    </div>
                    <span className="text-subtle mono" style={{ fontSize: 10.5 }}>{p.converted}/{p.files}</span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── CONVERSIONS (the magic pipeline moment) ──────────────── */
function ConversionsPage({ navigate }) {
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [conversionId, setConversionId] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [testCoverage, setTestCoverage] = useState("full");
  const [uploadError, setUploadError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: polledConversion } = useConversionPolling(conversionId || undefined);

  const defaultStages = [
    { stage: "file_process", label: "File processing", desc: "Analyzing SAS file structure", status: "pending", latency: null },
    { stage: "sas_partition", label: "Partitioning", desc: "Chunking into translation units", status: "pending", latency: null },
    { stage: "strategy_select", label: "Strategy selection", desc: "Assigning complexity + RAG tier", status: "pending", latency: null },
    { stage: "translate", label: "Translation", desc: "SAS → Python via LLM", status: "pending", latency: null },
    { stage: "validate", label: "Validation", desc: "Sandbox exec + AST checks", status: "pending", latency: null },
    { stage: "repair", label: "Repair", desc: "Reflexion retry on failures", status: "pending", latency: null },
    { stage: "merge", label: "Merge", desc: "Assemble final script + report", status: "pending", latency: null },
    { stage: "finalize", label: "Finalize", desc: "Quality checks + output", status: "pending", latency: null },
  ];
  const stages = polledConversion?.stages || defaultStages;
  const stageIdx = stages.filter(s => s.status === "completed").length;
  const isComplete = polledConversion?.status === "completed" || polledConversion?.status === "partial";
  const progress = polledConversion?.progress || Math.round((stageIdx / stages.length) * 100);

  React.useEffect(() => {
    if (isComplete && isRunning) window.codara?.celebrate();
  }, [isComplete, isRunning]);

  const handleFileDrop = async (fileList: FileList) => {
    setUploadError("");
    try {
      const result = await uploadFiles(fileList);
      setUploadedFiles(prev => [...prev, ...result]);
    } catch (e: any) {
      setUploadError(e.message || "Upload failed");
    }
  };

  const handleStart = async () => {
    if (uploadedFiles.length === 0) return;
    setIsRunning(true);
    try {
      const conv = await startConversion(
        uploadedFiles.map(f => f.id),
        { testCoverage }
      );
      setConversionId(conv.id);
    } catch (e: any) {
      setUploadError(e.message || "Failed to start conversion");
      setIsRunning(false);
    }
  };

  return (
    <div className="page-in" style={{ display: "flex", flexDirection: "column", gap: 22, maxWidth: 980, margin: "0 auto" }}>
      <div>
        <div className="eyebrow">Step 1 of 3</div>
        <h1 style={{ fontSize: "var(--tw-h1)", fontWeight: 600, marginTop: 4 }}>New conversion</h1>
        <p className="text-muted" style={{ marginTop: 4, fontSize: 14 }}>
          Upload SAS files and we'll translate them to production-ready Python.
        </p>
      </div>

      {isRunning ? (
        <PipelineRunner stages={stages} stageIdx={stageIdx} isComplete={isComplete} progress={progress} navigate={navigate}/>
      ) : (
        <>
          {uploadError && (
            <div style={{ padding: "10px 14px", borderRadius: "var(--radius)", background: "color-mix(in srgb, var(--danger) 10%, var(--bg-elev))", border: "1px solid color-mix(in srgb, var(--danger) 30%, transparent)", color: "var(--danger)", fontSize: 12.5 }}>
              {uploadError}
            </div>
          )}
          {/* Drop zone */}
          <input ref={fileInputRef} type="file" accept=".sas" multiple style={{ display: "none" }}
                 onChange={e => { if (e.target.files?.length) handleFileDrop(e.target.files); e.target.value = ""; }}/>
          <div
            onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={e => { e.preventDefault(); setIsDragging(false); if (e.dataTransfer.files.length) handleFileDrop(e.dataTransfer.files); }}
            onClick={() => fileInputRef.current?.click()}
            style={{
              padding: 40, borderRadius: "var(--radius-xl)", position: "relative", overflow: "hidden", cursor: "pointer",
              border: `2px dashed ${isDragging ? "var(--accent)" : "var(--border-strong)"}`,
              background: isDragging ? "color-mix(in srgb, var(--accent) 6%, var(--bg-elev))" : "var(--bg-elev)",
              textAlign: "center", transition: "all 0.2s var(--ease-out)",
              transform: isDragging ? "scale(1.005)" : "scale(1)",
            }}>
            <div className="dot-grid-fine" style={{ position: "absolute", inset: 0, opacity: isDragging ? 0.5 : 0.25 }}/>
            <div style={{ position: "relative" }}>
              <div style={{
                width: 56, height: 56, borderRadius: "var(--radius-lg)", margin: "0 auto 16px",
                background: isDragging ? "var(--accent)" : "var(--surface)",
                color: isDragging ? "var(--accent-fg)" : "var(--accent)",
                border: "1px solid var(--border)",
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                transition: "all 0.2s var(--ease-spring)",
                transform: isDragging ? "translateY(-4px)" : "translateY(0)",
              }}>
                <Icon name="upload" size={22}/>
              </div>
              <div style={{ fontSize: 15, fontWeight: 500, marginBottom: 4 }}>
                Drop .sas files here or <span style={{ color: "var(--accent)", textDecoration: "underline" }}>browse</span>
              </div>
              <div className="text-subtle" style={{ fontSize: 12 }}>Multi-file support · Max 50MB per file · Macros & PROCs supported</div>
            </div>
          </div>

          {/* Uploaded list */}
          {uploadedFiles.length > 0 && (
            <div className="panel" style={{ overflow: "hidden" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderBottom: "1px solid var(--border)" }}>
                <div style={{ fontWeight: 500, fontSize: 13 }}>{uploadedFiles.length} files ready</div>
                <button className="btn btn-sm btn-ghost" onClick={() => setUploadedFiles([])}>Clear</button>
              </div>
              {uploadedFiles.map(f => (
                <div key={f.id} style={{
                  display: "flex", alignItems: "center", gap: 12, padding: "12px 18px",
                  borderBottom: "1px solid var(--border)",
                }}>
                  <Icon name="fileCode" size={16} className="text-accent"/>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 500, fontSize: 13 }}>{f.name}</div>
                    <div style={{ display: "flex", gap: 10, fontSize: 11, color: "var(--fg-subtle)", marginTop: 2 }}>
                      <span className="mono">{(f.size/1024).toFixed(1)} KB</span>
                      {f.modules.length > 0 && <span>{f.modules.join(" · ")}</span>}
                      <span className={
                        f.estimatedComplexity === "high" ? "text-danger" :
                        f.estimatedComplexity === "medium" ? "text-warning" : "text-success"
                      }>{f.estimatedComplexity} complexity</span>
                    </div>
                  </div>
                  <button className="btn btn-icon btn-ghost" onClick={() => setUploadedFiles(uploadedFiles.filter(u => u.id !== f.id))}>
                    <Icon name="x" size={13}/>
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Config */}
          <div className="panel" style={{ padding: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
              <Icon name="settings" size={14} className="text-muted"/>
              <div style={{ fontWeight: 600, fontSize: 13 }}>Configuration</div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
              <div>
                <div className="eyebrow" style={{ marginBottom: 8 }}>Target runtime</div>
                <div style={{
                  padding: "10px 12px", border: "1px solid var(--accent)",
                  background: "var(--accent-soft)", color: "var(--accent)",
                  borderRadius: "var(--radius)", fontSize: 13, fontWeight: 500,
                  display: "flex", alignItems: "center", gap: 8,
                }}>
                  <Icon name="package" size={13}/> Python · pandas
                </div>
              </div>
              <div>
                <div className="eyebrow" style={{ marginBottom: 8 }}>Test coverage</div>
                <div className="toggle-pill" style={{ width: "100%", padding: 3 }}>
                  {["full", "structural", "off"].map(opt => (
                    <button key={opt} onClick={() => setTestCoverage(opt)} aria-selected={testCoverage === opt}
                            style={{ flex: 1, padding: "6px 0", fontSize: 12, textTransform: "capitalize" }}>
                      {opt}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <button className="btn btn-primary btn-lg" onClick={handleStart} disabled={uploadedFiles.length === 0}
                  style={{ width: "100%", padding: "14px", fontSize: 14, fontWeight: 600,
                           opacity: uploadedFiles.length === 0 ? 0.5 : 1,
                           background: "linear-gradient(135deg, var(--accent), var(--secondary))",
                           border: "0", color: "white" }}>
            <Icon name="play" size={14}/> Start conversion
          </button>
        </>
      )}
    </div>
  );
}

/* ─── Pipeline Runner ─── */
function PipelineRunner({ stages, stageIdx, isComplete, progress, navigate }) {
  return (
    <div className="panel" style={{ padding: 28, animation: "growIn 0.32s var(--ease-spring) both" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <div className="eyebrow" style={{ color: isComplete ? "var(--success)" : "var(--accent)" }}>
            {isComplete ? "Conversion complete" : "Converting…"}
          </div>
          <div style={{ fontSize: 20, fontWeight: 600, marginTop: 4 }}>monthly_rollup.sas</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{
            fontSize: 40, fontWeight: 700, fontFamily: "var(--font-display)",
            color: isComplete ? "var(--success)" : "var(--accent)",
            lineHeight: 1, letterSpacing: "-0.03em",
          }}>
            <AnimatedNumber value={isComplete ? 100 : progress}/>%
          </div>
          <div className="text-subtle" style={{ fontSize: 11, marginTop: 2 }}>
            {isComplete ? "47.3s total" : `Stage ${Math.min(stageIdx + 1, stages.length)} of ${stages.length}`}
          </div>
        </div>
      </div>

      {/* Progress bar */}
      <div style={{ height: 8, background: "var(--surface-2)", borderRadius: 999, overflow: "hidden", marginBottom: 26, position: "relative" }}>
        <div style={{
          height: "100%", width: `${isComplete ? 100 : progress}%`,
          background: isComplete ? "var(--success)" : "linear-gradient(90deg, var(--accent), var(--secondary))",
          borderRadius: 999,
          transition: "width 0.8s var(--ease-out)",
          position: "relative", overflow: "hidden",
        }}>
          {!isComplete && (
            <div style={{
              position: "absolute", inset: 0,
              background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.35), transparent)",
              animation: "shimmer 1.5s linear infinite",
            }}/>
          )}
        </div>
      </div>

      {/* Stages */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {stages.map((s, i) => {
          const status = i < stageIdx ? "completed" : i === stageIdx && !isComplete ? "running" : "pending";
          const stageProgress = Math.round(((i + 1) / stages.length) * 100);
          return (
            <div key={s.stage} style={{
              display: "flex", alignItems: "center", gap: 12, padding: "12px 14px",
              borderRadius: "var(--radius)",
              background: status === "running" ? "color-mix(in srgb, var(--accent) 6%, transparent)" : "transparent",
              border: status === "running" ? "1px solid color-mix(in srgb, var(--accent) 22%, transparent)" : "1px solid transparent",
              opacity: status === "pending" ? 0.42 : 1,
              transition: "all 0.32s var(--ease-out)",
            }}>
              {/* Icon */}
              <div style={{ width: 24, height: 24, display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                {status === "completed" && (
                  <div style={{
                    width: 22, height: 22, borderRadius: 999, background: "var(--success-soft)",
                    color: "var(--success)", display: "inline-flex", alignItems: "center", justifyContent: "center",
                    animation: "growIn 0.3s var(--ease-spring) both",
                  }}><Icon name="check" size={13} strokeWidth={2.5}/></div>
                )}
                {status === "running" && (
                  <div style={{
                    width: 22, height: 22, borderRadius: 999,
                    border: "2px solid var(--accent-soft)", borderTopColor: "var(--accent)",
                    animation: "spin 0.9s linear infinite",
                  }}/>
                )}
                {status === "pending" && (
                  <div style={{
                    width: 22, height: 22, borderRadius: 999, border: "1.5px dashed var(--border-strong)",
                  }}/>
                )}
              </div>

              {/* Label */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                  <span style={{
                    fontWeight: 500, fontSize: 13.5,
                    color: status === "running" ? "var(--accent)" : status === "completed" ? "var(--fg)" : "var(--fg-muted)",
                  }}>{s.label}</span>
                  <span className="mono text-subtle" style={{ fontSize: 10.5 }}>{stageProgress}%</span>
                </div>
                <div className="text-muted" style={{ fontSize: 12, marginTop: 2, lineHeight: 1.5 }}>{s.desc}</div>
              </div>

              {/* Latency */}
              {status === "completed" && s.latency && (
                <span className="mono text-subtle" style={{ fontSize: 10.5, flexShrink: 0 }}>
                  {s.latency > 1000 ? `${(s.latency / 1000).toFixed(1)}s` : `${s.latency}ms`}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Complete actions */}
      {isComplete && (
        <div style={{ marginTop: 22, display: "flex", alignItems: "center", gap: 10, animation: "pageIn 0.4s var(--ease-out) both" }}>
          <button className="btn btn-primary btn-lg" onClick={() => navigate("/workspace/cv_8a40")}>
            View diff <Icon name="arrowRight" size={13}/>
          </button>
          <button className="btn btn-lg" onClick={() => navigate("/conversions")}>New conversion</button>
          <div style={{ flex: 1 }}/>
          <div className="text-subtle" style={{ fontSize: 12 }}>96% coverage · 2,104 lines generated</div>
        </div>
      )}
    </div>
  );
}

/* ─── WORKSPACE (centerpiece — diff) ───────────────────────── */
function WorkspacePage({ navigate, conversionId }) {
  const { data: liveConv } = useConversionPolling(conversionId);
  const rawConv = liveConv || { fileName: "loading...", status: "queued", accuracy: 0, duration: 0, sasCode: null, pythonCode: null, stages: [], progress: 0 };
  const conv = { ...rawConv, coverage: rawConv.accuracy, lines: rawConv.sasCode ? rawConv.sasCode.split("\n").length : 0, pyLines: rawConv.pythonCode ? rawConv.pythonCode.split("\n").length : 0, project: rawConv.runtime || "" } as any;
  const [view, setView] = useState("split"); // split | inline | python
  const [activeChunk, setActiveChunk] = useState(0);

  // Mock chunks
  const chunks = [
    { id: 0, name: "Header & libname setup", sasLines: [1, 18], pyLines: [1, 14], status: "ok", coverage: 100 },
    { id: 1, name: "DATA step: claims_clean", sasLines: [19, 48], pyLines: [15, 42], status: "ok", coverage: 98 },
    { id: 2, name: "PROC SQL join → merge", sasLines: [49, 72], pyLines: [43, 58], status: "ok", coverage: 100 },
    { id: 3, name: "%MACRO flag_high", sasLines: [73, 96], pyLines: [59, 82], status: "review", coverage: 86 },
    { id: 4, name: "PROC MEANS rollup", sasLines: [97, 118], pyLines: [83, 102], status: "ok", coverage: 96 },
    { id: 5, name: "Output & finalize", sasLines: [119, 142], pyLines: [103, 124], status: "ok", coverage: 100 },
  ];

  const sasCode = `* claims monthly rollup;
libname raw '/data/insurance/raw';
libname out '/data/insurance/out';

%let cutoff_date = '01JAN2026'd;
%let regions = NE NW SE SW;

data claims_clean;
  set raw.claims;
  where reported_date >= &cutoff_date;
  if missing(loss_amount) then delete;
  loss_band = "low";
  if loss_amount > 5000 then loss_band = "med";
  if loss_amount > 25000 then loss_band = "high";
  format reported_date date9.;
run;

proc sql;
  create table joined as
  select a.*, b.region
  from claims_clean a
  left join raw.geo_lookup b
    on a.zip_code = b.zip_code;
quit;

%macro flag_high(thresh=);
  data flagged;
    set joined;
    high_value = (loss_amount > &thresh);
  run;
%mend;

%flag_high(thresh=10000);

proc means data=flagged noprint;
  class region loss_band;
  var loss_amount;
  output out=rollup
    mean=avg_loss
    sum=total_loss
    n=claim_count;
run;`;

  const pyCode = `"""Monthly claims rollup — translated from claims_etl_v3.sas
Generated by Codara v4.2 · claude-sonnet-4 · 47.3s
"""
import pandas as pd
from pathlib import Path

RAW = Path("/data/insurance/raw")
OUT = Path("/data/insurance/out")

CUTOFF_DATE = pd.Timestamp("2026-01-01")
REGIONS = ["NE", "NW", "SE", "SW"]

def clean_claims(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["reported_date"] >= CUTOFF_DATE]
    df = df.dropna(subset=["loss_amount"])
    df = df.copy()
    df["loss_band"] = "low"
    df.loc[df["loss_amount"] > 5000, "loss_band"] = "med"
    df.loc[df["loss_amount"] > 25000, "loss_band"] = "high"
    return df

def join_geo(claims: pd.DataFrame, geo: pd.DataFrame) -> pd.DataFrame:
    return claims.merge(
        geo[["zip_code", "region"]],
        on="zip_code",
        how="left",
    )

def flag_high(df: pd.DataFrame, thresh: float = 10_000) -> pd.DataFrame:
    out = df.copy()
    out["high_value"] = out["loss_amount"] > thresh
    return out

def rollup(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(["region", "loss_band"])["loss_amount"]
          .agg(avg_loss="mean", total_loss="sum", claim_count="count")
          .reset_index()
    )`;

  const totalChanges = 23;

  return (
    <div className="page-in" style={{ height: "calc(100vh - 60px - 56px)", display: "flex", flexDirection: "column", margin: "-28px -32px -80px", minHeight: 0 }}>
      {/* Workspace header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 24px", borderBottom: "1px solid var(--border)", background: "var(--bg-elev)" }}>
        <button className="btn btn-icon btn-ghost" onClick={() => navigate("/history")}>
          <Icon name="chevronLeft" size={14}/>
        </button>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Icon name="fileCode" size={15} className="text-accent"/>
            <span style={{ fontWeight: 600, fontSize: 14.5 }}>{conv.fileName}</span>
            <StatusBadge status={conv.status}/>
            <span className="badge"><Icon name="git" size={10}/> {totalChanges} translations</span>
          </div>
          <div style={{ fontSize: 11.5, color: "var(--fg-subtle)", marginTop: 2, display: "flex", gap: 10 }}>
            <span>{conv.project}</span>
            <span>·</span>
            <span className="mono">{conv.lines} → {conv.pyLines} lines</span>
            <span>·</span>
            <span>Test coverage: <span className="text-success" style={{ fontWeight: 500 }}>{conv.coverage}%</span></span>
            <span>·</span>
            <span>{conv.duration}s</span>
          </div>
        </div>

        {/* View toggle */}
        <div className="toggle-pill">
          <button onClick={() => setView("split")} aria-selected={view === "split"}>Split</button>
          <button onClick={() => setView("inline")} aria-selected={view === "inline"}>Inline</button>
          <button onClick={() => setView("python")} aria-selected={view === "python"}>Python only</button>
        </div>

        <button className="btn btn-sm"><Icon name="message" size={12}/> Comment</button>
        <button className="btn btn-sm" onClick={() => window.codara?.openShare(conv.fileName)}><Icon name="share" size={12}/> Share</button>
        <button className="btn btn-sm btn-primary" onClick={() => { window.codara?.celebrate(); }}><Icon name="download" size={12}/> Export</button>
      </div>

      {/* Body: chunk list | diff */}
      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", flex: 1, minHeight: 0 }}>
        {/* Chunk navigator */}
        <aside style={{ borderRight: "1px solid var(--border)", overflowY: "auto", background: "var(--bg-elev)" }}>
          <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--border)", position: "sticky", top: 0, background: "var(--bg-elev)", zIndex: 1 }}>
            <div className="eyebrow">Translation units</div>
            <div style={{ fontSize: 11.5, color: "var(--fg-subtle)", marginTop: 2 }}>{chunks.length} chunks · {totalChanges} translations</div>
          </div>
          {chunks.map((c, i) => (
            <button key={c.id} onClick={() => setActiveChunk(i)} style={{
              display: "flex", alignItems: "flex-start", gap: 10, padding: "11px 14px",
              width: "100%", borderLeft: activeChunk === i ? "2px solid var(--accent)" : "2px solid transparent",
              background: activeChunk === i ? "var(--surface)" : "transparent",
              textAlign: "left",
              transition: "background 0.16s var(--ease-out)",
            }}>
              <span style={{
                width: 18, height: 18, borderRadius: 4, flexShrink: 0,
                background: c.status === "ok" ? "var(--success-soft)" : "var(--warning-soft)",
                color: c.status === "ok" ? "var(--success)" : "var(--warning)",
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                fontSize: 9.5, fontWeight: 700,
              }}>{i + 1}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, fontWeight: 500 }}>{c.name}</div>
                <div style={{ fontSize: 10.5, color: "var(--fg-subtle)", marginTop: 2, display: "flex", gap: 8 }}>
                  <span className="mono">L{c.sasLines[0]}–{c.sasLines[1]}</span>
                  <span>·</span>
                  <span>{c.coverage}%</span>
                </div>
              </div>
              {c.status === "review" && <Icon name="alert" size={11} className="text-warning"/>}
            </button>
          ))}

          {/* Mini map */}
          <div style={{ padding: 14, borderTop: "1px solid var(--border)" }}>
            <div className="eyebrow" style={{ marginBottom: 8 }}>Conversion fingerprint</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(20, 1fr)", gap: 2 }}>
              {Array.from({ length: 60 }, (_, i) => {
                const v = (Math.sin(i / 2.4) + 1) / 2;
                return <div key={i} style={{
                  height: 14, borderRadius: 1,
                  background: i % 11 === 5 ? "var(--warning)" : "var(--chart-1)",
                  opacity: 0.2 + v * 0.7,
                  animation: "fadeIn 0.4s ease-out both",
                  animationDelay: `${i * 8}ms`,
                }}/>;
              })}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, color: "var(--fg-subtle)", marginTop: 4 }}>
              <span>L1</span><span>L{conv.lines}</span>
            </div>
          </div>
        </aside>

        {/* Diff body */}
        <div style={{ display: "grid", gridTemplateColumns: view === "split" ? "1fr 1fr" : "1fr", flex: 1, minHeight: 0 }}>
          {view !== "python" && (
            <div style={{ display: "flex", flexDirection: "column", minHeight: 0, borderRight: view === "split" ? "1px solid var(--border)" : "0" }}>
              <div style={{
                padding: "10px 16px", borderBottom: "1px solid var(--border)",
                display: "flex", alignItems: "center", gap: 8, background: "var(--bg-elev)",
              }}>
                <span className="badge"><Icon name="tag" size={9}/> SAS</span>
                <span className="text-muted" style={{ fontSize: 11.5 }}>{conv.fileName}</span>
                <div style={{ flex: 1 }}/>
                <button className="btn btn-icon btn-ghost"><Icon name="copy" size={12}/></button>
              </div>
              <div style={{ flex: 1, minHeight: 0, overflow: "auto", background: "var(--bg-elev)" }}>
                <CodeBlock code={sasCode} lang="sas"
                           highlightLines={chunks[activeChunk] ? Array.from(
                             { length: chunks[activeChunk].sasLines[1] - chunks[activeChunk].sasLines[0] + 1 },
                             (_, i) => chunks[activeChunk].sasLines[0] + i
                           ) : []}/>
              </div>
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
            <div style={{
              padding: "10px 16px", borderBottom: "1px solid var(--border)",
              display: "flex", alignItems: "center", gap: 8, background: "var(--bg-elev)",
            }}>
              <span className="badge badge-accent"><Icon name="package" size={9}/> Python</span>
              <span className="text-muted" style={{ fontSize: 11.5 }}>{conv.fileName.replace(".sas", ".py")}</span>
              <span className="badge badge-success"><Icon name="check" size={9}/> Generated</span>
              <div style={{ flex: 1 }}/>
              <button className="btn btn-icon btn-ghost"><Icon name="copy" size={12}/></button>
            </div>
            <div style={{ flex: 1, minHeight: 0, overflow: "auto", background: "var(--bg-elev)" }}>
              <CodeBlock code={pyCode} lang="py"
                         highlightLines={chunks[activeChunk] ? Array.from(
                           { length: chunks[activeChunk].pyLines[1] - chunks[activeChunk].pyLines[0] + 1 },
                           (_, i) => chunks[activeChunk].pyLines[0] + i
                         ) : []}/>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom strip — chunk info */}
      <div style={{
        height: 56, flexShrink: 0, padding: "0 24px",
        borderTop: "1px solid var(--border)", background: "var(--bg-elev)",
        display: "flex", alignItems: "center", gap: 16,
      }}>
        <span className="eyebrow">Translation rationale</span>
        <span style={{ fontSize: 12.5, color: "var(--fg-muted)", flex: 1 }}>
          {chunks[activeChunk] ?
            `${chunks[activeChunk].name} · ${chunks[activeChunk].coverage}% test coverage · Applied KB pattern: ${
              activeChunk === 1 ? "DATA step → vectorized pandas" :
              activeChunk === 2 ? "PROC SQL JOIN → DataFrame.merge" :
              activeChunk === 3 ? "%MACRO → typed function" :
              activeChunk === 4 ? "PROC MEANS → groupby.agg" : "Direct translation"
            }` : ""}
        </span>
        <button className="btn btn-sm"><Icon name="book" size={11}/> View pattern</button>
        <button className="btn btn-sm"><Icon name="refresh" size={11}/> Re-translate</button>
        <button className="btn btn-sm"><Icon name="checkCircle" size={11}/> Approve chunk</button>
      </div>
    </div>
  );
}

/* ─── HISTORY ─────────────────────────────────────────────── */
function HistoryPage({ navigate }) {
  const { data: liveConversions } = useConversions();
  const conversions = (liveConversions || []).map(c => ({
    ...c, coverage: c.accuracy, project: c.runtime,
    lines: c.sasCode ? c.sasCode.split("\n").length : 0,
  })) as any[];
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const filtered = conversions.filter(c =>
    (filter === "all" || c.status === filter) &&
    (q === "" || c.fileName.toLowerCase().includes(q.toLowerCase()) || (c.project || "").toLowerCase().includes(q.toLowerCase()))
  );

  return (
    <div className="page-in" style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 1280 }}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: "var(--tw-h1)", fontWeight: 600 }}>History</h1>
          <p className="text-muted" style={{ marginTop: 4, fontSize: 14 }}>
            All your conversions, searchable and filterable.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate("/conversions")}>
          <Icon name="plus" size={13}/> New conversion
        </button>
      </div>

      {/* Filters */}
      <div className="panel" style={{ padding: "10px 14px", display: "flex", gap: 10, alignItems: "center" }}>
        <Icon name="search" size={14} className="text-muted"/>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search files, projects…"
               style={{ flex: 1, fontSize: 13, padding: "4px 0" }}/>
        <div style={{ width: 1, height: 20, background: "var(--border)" }}/>
        <div className="toggle-pill">
          {["all", "completed", "running", "partial", "failed"].map(s => (
            <button key={s} onClick={() => setFilter(s)} aria-selected={filter === s}
                    style={{ textTransform: "capitalize" }}>{s}</button>
          ))}
        </div>
        <button className="btn btn-sm btn-ghost"><Icon name="filter" size={12}/> More</button>
      </div>

      {/* Table */}
      <div className="panel" style={{ overflow: "hidden" }}>
        <div style={{
          display: "grid", gridTemplateColumns: "minmax(260px, 1.5fr) 1fr 90px 110px 90px 120px 36px",
          padding: "10px 18px", borderBottom: "1px solid var(--border)",
          fontSize: 11, fontWeight: 600, color: "var(--fg-muted)",
          textTransform: "uppercase", letterSpacing: "0.04em",
        }}>
          <div>File</div>
          <div>Project</div>
          <div className="mono">Lines</div>
          <div>Coverage</div>
          <div className="mono">Time</div>
          <div>Status</div>
          <div></div>
        </div>
        {filtered.map((c, i) => (
          <button key={c.id} onClick={() => navigate(`/workspace/${c.id}`)} style={{
            display: "grid", gridTemplateColumns: "minmax(260px, 1.5fr) 1fr 90px 110px 90px 120px 36px",
            padding: "12px 18px", borderBottom: "1px solid var(--border)",
            alignItems: "center", width: "100%", textAlign: "left",
            animation: "pageIn 0.32s var(--ease-out) both", animationDelay: `${i * 24}ms`,
            transition: "background 0.16s",
          }} onMouseEnter={e => e.currentTarget.style.background = "var(--surface-2)"}
             onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
              <Icon name="fileCode" size={14} className="text-accent"/>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 500, fontSize: 13 }}>{c.fileName}</div>
                <div className="text-subtle" style={{ fontSize: 11 }}>{new Date(c.createdAt).toLocaleString()}</div>
              </div>
            </div>
            <div style={{ fontSize: 12.5, color: "var(--fg-muted)" }}>{c.project}</div>
            <div className="mono" style={{ fontSize: 12 }}>{c.lines.toLocaleString()}</div>
            <div>
              {c.coverage > 0 ? (
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ width: 50, height: 4, background: "var(--surface-2)", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{ width: `${c.coverage}%`, height: "100%",
                                  background: c.coverage > 90 ? "var(--success)" : c.coverage > 75 ? "var(--warning)" : "var(--danger)"}}/>
                  </div>
                  <span className="mono" style={{ fontSize: 11.5 }}>{c.coverage}%</span>
                </div>
              ) : <span className="text-subtle mono" style={{ fontSize: 11 }}>—</span>}
            </div>
            <div className="mono" style={{ fontSize: 12 }}>{c.duration > 0 ? `${c.duration}s` : "—"}</div>
            <div><StatusBadge status={c.status}/></div>
            <div><Icon name="more" size={14} className="text-subtle"/></div>
          </button>
        ))}
      </div>
    </div>
  );
}
export { UserDashboard, ConversionsPage, PipelineRunner, WorkspacePage, HistoryPage };
