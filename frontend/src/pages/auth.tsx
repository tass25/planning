import React, { useState, useEffect, useRef, useMemo, useCallback, createContext, useContext } from "react";
import type { ReactNode, CSSProperties } from "react";
import { useAuth } from "../lib/auth-context";
import { useCostSummary, useErrorQueue, retryConversion, dismissError, usePromptTemplates, updatePromptTemplate } from "../lib/hooks";
import type { PromptTemplate } from "../lib/hooks";
import { Icon, StatCard, StatusBadge, AnimatedNumber, Sparkline, CodeBlock, AreaChart } from "../components/ui";
import { CodaraLogo } from "../components/layout";

/* ──────────────────────────────────────────────────────────
   New admin pages: Cost dashboard, Prompt templates, Error queue
   + Auth: Login, Signup, Verify, Onboarding
   ────────────────────────────────────────────────────────── */

/* ─── COST DASHBOARD (NEW) ───────────────────────────────── */
function CostDashboardPage() {
  const { data: liveCost } = useCostSummary();
  const byModel = liveCost?.byModel || [];
  const data = liveCost?.daily || [];
  const totalCost = liveCost?.totalCost || 0;
  const totalCalls = liveCost?.totalCalls || 0;
  const totalTokens = liveCost?.totalTokens || 0;

  return (
    <div className="page-in" style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 1400 }}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
            <h1 style={{ fontSize: "var(--tw-h1)", fontWeight: 600 }}>Cost dashboard</h1>
            <span className="badge badge-accent">NEW</span>
          </div>
          <p className="text-muted" style={{ fontSize: 14, marginTop: 4 }}>
            Token spend, model breakdown, and per-conversion economics
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn"><Icon name="download" size={12}/> Export CSV</button>
          <button className="btn"><Icon name="settings" size={12}/> Budgets & alerts</button>
        </div>
      </div>

      {/* Top KPIs */}
      <div className="stagger" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
        <StatCard label="Spend (30d)" value={`$${totalCost.toFixed(0)}`} delta="-12%" deltaType="up" icon="dollar" tone="accent"
                  sparkData={data.map(d => d.cost)} sub="$48.21 saved vs budget"/>
        <StatCard label="LLM calls" value={totalCalls.toLocaleString()} delta="+8%" deltaType="up" icon="zap"/>
        <StatCard label="Tokens" value={`${(totalTokens/1e6).toFixed(0)}M`} delta="+11%" deltaType="up" icon="cpu"/>
        <StatCard label="Cost / conversion" value={`$${(totalCost/142).toFixed(2)}`} delta="-$0.18" deltaType="up" icon="trending"/>
      </div>

      {/* Spend over time + Budget gauge */}
      <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 14 }}>
        <div className="panel" style={{ padding: 20 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <h2 style={{ fontSize: "var(--tw-h2)", fontWeight: 600 }}>Daily spend</h2>
            <div style={{ display: "flex", gap: 14, fontSize: 11 }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--chart-1)" }}/> Actual
              </span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                <span style={{ width: 8, height: 2, background: "var(--chart-5)" }}/> Daily budget
              </span>
            </div>
          </div>
          <AreaChart data={data} height={220}
                     keys={[{ key: "cost", color: "var(--chart-1)" }]}/>
        </div>

        <div className="panel" style={{ padding: 20 }}>
          <h2 style={{ fontSize: "var(--tw-h2)", fontWeight: 600, marginBottom: 14 }}>Monthly budget</h2>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
            <BudgetGauge value={totalCost} max={2000}/>
            <div style={{ textAlign: "center" }}>
              <div className="mono" style={{ fontSize: 22, fontWeight: 700, fontFamily: "var(--font-display)" }}>
                $<AnimatedNumber value={Math.round(totalCost)}/> <span className="text-subtle" style={{ fontSize: 14 }}>/ $2,000</span>
              </div>
              <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>17 days remaining · on track</div>
            </div>
          </div>

          <div style={{ marginTop: 18, display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
              <span className="text-muted">Daily average</span>
              <span className="mono">${(totalCost/30).toFixed(2)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
              <span className="text-muted">Projected (EOM)</span>
              <span className="mono text-success">${(totalCost * 1.05).toFixed(0)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
              <span className="text-muted">Most expensive day</span>
              <span className="mono">${data.length > 0 ? Math.max(...data.map(d => d.cost)).toFixed(2) : "0.00"}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Model breakdown table */}
      <div className="panel" style={{ overflow: "hidden" }}>
        <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
          <h2 style={{ fontSize: "var(--tw-h2)", fontWeight: 600 }}>Spend by model</h2>
        </div>
        <div style={{
          display: "grid", gridTemplateColumns: "minmax(260px, 1.4fr) 120px 130px 130px 1fr",
          padding: "10px 20px", borderBottom: "1px solid var(--border)",
          fontSize: 11, fontWeight: 600, color: "var(--fg-muted)",
          textTransform: "uppercase", letterSpacing: "0.04em",
        }}>
          <div>Model</div><div className="mono">Calls</div><div className="mono">Tokens</div><div className="mono">Cost</div><div>Share</div>
        </div>
        {byModel.map((m, i) => {
          const color = `var(--chart-${(i % 6) + 1})`;
          return (
          <div key={m.model} style={{
            display: "grid", gridTemplateColumns: "minmax(260px, 1.4fr) 120px 130px 130px 1fr",
            padding: "14px 20px", borderBottom: "1px solid var(--border)", alignItems: "center", gap: 14,
            animation: "pageIn 0.32s var(--ease-out) both", animationDelay: `${i * 50}ms`,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: color }}/>
              <span style={{ fontWeight: 500, fontSize: 13 }} className="mono">{m.model}</span>
            </div>
            <div className="mono">{m.calls.toLocaleString()}</div>
            <div className="mono">{(m.tokens/1e6).toFixed(1)}M</div>
            <div className="mono" style={{ fontWeight: 600 }}>${m.cost.toFixed(2)}</div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ flex: 1, height: 6, background: "var(--surface-2)", borderRadius: 2, overflow: "hidden" }}>
                <div style={{
                  width: `${totalCost > 0 ? (m.cost/totalCost)*100 : 0}%`, height: "100%", background: color,
                  transition: "width 1s var(--ease-out)",
                }}/>
              </div>
              <span className="mono text-muted" style={{ fontSize: 11, width: 36, textAlign: "right" }}>{totalCost > 0 ? ((m.cost/totalCost)*100).toFixed(0) : 0}%</span>
            </div>
          </div>
          );
        })}
      </div>
    </div>
  );
}

function BudgetGauge({ value, max }) {
  const pct = Math.min(1, value / max);
  const r = 70, c = 2 * Math.PI * r;
  const arc = c * 0.75;
  const offset = arc * (1 - pct);
  const color = pct < 0.6 ? "var(--success)" : pct < 0.85 ? "var(--warning)" : "var(--danger)";
  return (
    <svg width={170} height={120} style={{ display: "block" }}>
      <circle cx="85" cy="85" r={r} fill="none" stroke="var(--surface-2)" strokeWidth="12"
              strokeDasharray={`${arc} ${c}`} strokeLinecap="round"
              transform="rotate(135 85 85)"/>
      <circle cx="85" cy="85" r={r} fill="none" stroke={color} strokeWidth="12"
              strokeDasharray={`${arc} ${c}`} strokeLinecap="round" strokeDashoffset={offset}
              transform="rotate(135 85 85)"
              style={{ transition: "stroke-dashoffset 1.4s var(--ease-out)" }}/>
    </svg>
  );
}

/* ─── PROMPT TEMPLATES (NEW) ─────────────────────────────── */
function PromptTemplatesPage() {
  const { data: liveTemplates, refetch } = usePromptTemplates();
  const templates = (liveTemplates || []).map(t => ({
    id: t.id, name: t.displayName, version: t.version, model: t.model,
    status: t.status, uses: t.uses, lastEdited: t.lastEdited,
    content: t.content, variables: t.variables,
    avgLatency: t.avgLatency, successRate: t.successRate,
    description: t.description, category: t.category,
  }));
  const [active, setActive] = useState<typeof templates[number] | null>(null);
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (templates.length > 0 && !active) setActive(templates[0]);
  }, [templates.length]);

  const handleEdit = () => { if (active) { setEditContent(active.content); setEditing(true); } };
  const handleSave = async () => {
    if (!active) return;
    setSaving(true);
    try {
      await updatePromptTemplate(active.id, { content: editContent });
      setEditing(false);
      refetch();
    } finally { setSaving(false); }
  };

  const formatDate = (iso: string) => {
    try { const d = new Date(iso); const days = Math.floor((Date.now() - d.getTime()) / 86400000); return days < 1 ? "today" : days < 7 ? `${days}d ago` : `${Math.floor(days/7)}w ago`; }
    catch { return iso; }
  };

  return (
    <div className="page-in" style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 1400, height: "calc(100vh - 60px - 56px - 28px)" }}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
            <h1 style={{ fontSize: "var(--tw-h1)", fontWeight: 600 }}>Prompt templates</h1>
            <span className="badge badge-accent">{templates.length}</span>
          </div>
          <p className="text-muted" style={{ fontSize: 14, marginTop: 4 }}>
            Version-controlled LLM prompts powering each pipeline stage
          </p>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: 14, flex: 1, minHeight: 0 }}>
        {/* List */}
        <div className="panel" style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
          <div style={{ padding: 14, borderBottom: "1px solid var(--border)" }}>
            <div className="eyebrow">Templates</div>
          </div>
          <div style={{ flex: 1, overflowY: "auto" }}>
            {templates.map((t, i) => (
              <button key={t.id} onClick={() => { setActive(t); setEditing(false); }} style={{
                width: "100%", padding: "14px", textAlign: "left",
                borderBottom: "1px solid var(--border)",
                borderLeft: active?.id === t.id ? "2px solid var(--accent)" : "2px solid transparent",
                background: active?.id === t.id ? "var(--surface-2)" : "transparent",
                animation: "pageIn 0.3s var(--ease-out) both", animationDelay: `${i * 30}ms`,
              }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                  <div style={{ fontWeight: 500, fontSize: 13 }}>{t.name}</div>
                  <StatusBadge status={t.status}/>
                </div>
                <div style={{ display: "flex", gap: 8, fontSize: 11, color: "var(--fg-subtle)" }}>
                  <span className="mono">{t.version}</span>
                  <span>·</span>
                  <span className="mono">{t.model}</span>
                </div>
                <div className="text-subtle" style={{ fontSize: 11, marginTop: 4 }}>
                  {t.uses.toLocaleString()} uses · {formatDate(t.lastEdited)}
                </div>
              </button>
            ))}
            {templates.length === 0 && (
              <div className="text-muted" style={{ padding: 20, textAlign: "center", fontSize: 13 }}>No templates found</div>
            )}
          </div>
        </div>

        {/* Detail */}
        {active && (
          <div className="panel" style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: 8 }}>
                <div>
                  <div className="eyebrow">{active.model}</div>
                  <h2 style={{ fontSize: 18, fontWeight: 600, marginTop: 4 }}>{active.name}</h2>
                  <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
                    <span className="mono">{active.version}</span> · {active.category} · {formatDate(active.lastEdited)}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  {editing ? (
                    <>
                      <button className="btn btn-sm" onClick={() => setEditing(false)}>Cancel</button>
                      <button className="btn btn-sm btn-primary" onClick={handleSave} disabled={saving}>
                        <Icon name="check" size={12}/> {saving ? "Saving..." : "Save"}
                      </button>
                    </>
                  ) : (
                    <button className="btn btn-sm" onClick={handleEdit}><Icon name="edit" size={12}/> Edit</button>
                  )}
                </div>
              </div>
              <div style={{ display: "flex", gap: 14, fontSize: 11.5 }}>
                <span><span className="text-subtle">Uses </span><span className="mono" style={{ fontWeight: 600 }}>{active.uses.toLocaleString()}</span></span>
                <span><span className="text-subtle">Avg latency </span><span className="mono" style={{ fontWeight: 600 }}>{active.avgLatency.toFixed(0)}ms</span></span>
                <span><span className="text-subtle">Success rate </span><span className="mono text-success" style={{ fontWeight: 600 }}>{active.successRate.toFixed(1)}%</span></span>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", flex: 1, minHeight: 0 }}>
              <div style={{ overflow: "auto", borderRight: "1px solid var(--border)" }}>
                {editing ? (
                  <textarea value={editContent} onChange={e => setEditContent(e.target.value)} style={{
                    width: "100%", height: "100%", padding: 16, fontFamily: "var(--font-mono)", fontSize: 12,
                    background: "var(--bg-elev)", color: "var(--fg)", border: "none", resize: "none", outline: "none",
                  }}/>
                ) : (
                  <CodeBlock code={active.content} lang="py"/>
                )}
              </div>
              <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 16, overflow: "auto" }}>
                <div>
                  <div className="eyebrow" style={{ marginBottom: 8 }}>Description</div>
                  <p className="text-muted" style={{ fontSize: 12 }}>{active.description}</p>
                </div>

                <div>
                  <div className="eyebrow" style={{ marginBottom: 8 }}>Variables ({active.variables.length})</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {active.variables.map(v => (
                      <div key={v} style={{
                        display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
                        background: "var(--bg-elev)", borderRadius: "var(--radius-sm)", fontSize: 12,
                      }}>
                        <span className="mono" style={{ color: "var(--secondary)" }}>{`{{ ${v} }}`}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── ERROR QUEUE (NEW) ──────────────────────────────────── */
function ErrorQueuePage() {
  const { data: liveErrors } = useErrorQueue();
  const errs = (liveErrors || []).map(e => ({ id: e.id, file: e.fileName, stage: e.stage, error: e.error, model: e.model, retries: e.retries, age: e.createdAt, severity: e.severity, author: e.userName || "" }));
  const [active, setActive] = useState(null);

  useEffect(() => {
    if (errs.length > 0 && !active) setActive(errs[0]);
  }, [errs.length]);

  return (
    <div className="page-in" style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 1400 }}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
            <h1 style={{ fontSize: "var(--tw-h1)", fontWeight: 600 }}>Error triage</h1>
            <span className="badge badge-accent">NEW</span>
            <span className="badge badge-danger">{errs.length} open</span>
          </div>
          <p className="text-muted" style={{ fontSize: 14, marginTop: 4 }}>
            Failed conversions awaiting human review · Retry, reassign, or close
          </p>
        </div>
      </div>

      <div className="stagger" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        <StatCard label="Open" value={errs.length} icon="alert" tone="accent"/>
        <StatCard label="High severity" value={errs.filter(e => e.severity === "high").length} icon="flame"/>
        <StatCard label="Avg time to resolve" value="34m" icon="clock"/>
        <StatCard label="Auto-resolved (7d)" value="18" delta="+6" deltaType="up" icon="checkCircle"/>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div className="panel" style={{ overflow: "hidden" }}>
          <div style={{ padding: "12px 18px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ fontWeight: 600, fontSize: 13 }}>Queue</div>
            <button className="btn btn-sm"><Icon name="refresh" size={11}/> Retry all</button>
          </div>
          {errs.map((e, i) => (
            <button key={e.id} onClick={() => setActive(e)} style={{
              width: "100%", padding: "14px 18px", textAlign: "left",
              borderBottom: "1px solid var(--border)",
              borderLeft: active?.id === e.id ? "3px solid var(--accent)" : "3px solid transparent",
              background: active?.id === e.id ? "var(--surface-2)" : "transparent",
              animation: "pageIn 0.3s var(--ease-out) both", animationDelay: `${i * 30}ms`,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                <span style={{
                  width: 7, height: 7, borderRadius: 999,
                  background: e.severity === "high" ? "var(--danger)" : e.severity === "medium" ? "var(--warning)" : "var(--info)",
                  animation: e.severity === "high" ? "pulseSoft 1.4s ease-in-out infinite" : "none",
                }}/>
                <span style={{ fontWeight: 500, fontSize: 13 }}>{e.file}</span>
                <span style={{ flex: 1 }}/>
                <span className="text-subtle mono" style={{ fontSize: 11 }}>{e.age}</span>
              </div>
              <div className="text-muted" style={{ fontSize: 12, marginBottom: 6 }}>{e.error}</div>
              <div style={{ display: "flex", gap: 6 }}>
                <span className="badge" style={{ fontSize: 10 }}>{e.stage}</span>
                {e.model !== "—" && <span className="badge" style={{ fontSize: 10 }}>{e.model}</span>}
                <span className="badge" style={{ fontSize: 10 }}>retries: {e.retries}</span>
              </div>
            </button>
          ))}
        </div>

        {active && (
          <div className="panel" style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{ padding: 20, borderBottom: "1px solid var(--border)" }}>
              <div className="eyebrow" style={{ color: "var(--danger)" }}>Open · {active.severity} severity</div>
              <h2 style={{ fontSize: 18, fontWeight: 600, marginTop: 4 }}>{active.file}</h2>
              <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
                Failed at stage <span className="mono">{active.stage}</span> · owner: {active.author} · {active.age} ago
              </div>
            </div>

            <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16, flex: 1 }}>
              <div>
                <div className="eyebrow" style={{ marginBottom: 6 }}>Error</div>
                <div style={{
                  padding: 12, background: "color-mix(in srgb, var(--danger) 8%, transparent)",
                  border: "1px solid color-mix(in srgb, var(--danger) 18%, transparent)",
                  borderRadius: "var(--radius)", color: "var(--danger)",
                  fontSize: 12.5, fontFamily: "var(--font-mono)",
                }}>{active.error}</div>
              </div>

              <div>
                <div className="eyebrow" style={{ marginBottom: 6 }}>Suggested fixes</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {[
                    { i: "refresh", t: "Retry with claude-sonnet-4", d: "Higher capability model · est cost $0.18" },
                    { i: "settings", t: "Increase per-stage timeout to 120s", d: "Affects only this conversion" },
                    { i: "git", t: "Switch to fallback prompt v3.8", d: "Stable baseline · slightly lower coverage" },
                  ].map((s, i) => (
                    <button key={i} className="panel-flat" style={{
                      padding: 10, textAlign: "left", display: "flex", alignItems: "center", gap: 10,
                      background: "var(--bg-elev)",
                    }}>
                      <Icon name={s.i} size={14} className="text-accent"/>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 500, fontSize: 12.5 }}>{s.t}</div>
                        <div className="text-muted" style={{ fontSize: 11.5 }}>{s.d}</div>
                      </div>
                      <Icon name="arrowRight" size={12} className="text-subtle"/>
                    </button>
                  ))}
                </div>
              </div>

              <div style={{ flex: 1 }}/>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-primary" style={{ flex: 1 }}><Icon name="refresh" size={12}/> Retry now</button>
                <button className="btn"><Icon name="user" size={12}/> Reassign</button>
                <button className="btn"><Icon name="x" size={12}/> Close</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── LOGIN / SIGNUP / VERIFY ────────────────────────────── */
function AuthShell({ children, side = "right" }) {
  return (
    <div style={{
      position: "fixed", inset: 0, display: "grid", gridTemplateColumns: "1fr 1fr",
      background: "var(--bg)",
    }}>
      {/* Visual side */}
      <div style={{
        position: "relative", overflow: "hidden",
        background: "linear-gradient(135deg, color-mix(in srgb, var(--accent) 14%, var(--bg-elev)), color-mix(in srgb, var(--secondary) 10%, var(--bg-elev)))",
        padding: 48, display: "flex", flexDirection: "column", justifyContent: "space-between",
        order: side === "right" ? 0 : 1,
      }}>
        <div className="dot-grid-fine" style={{ position: "absolute", inset: 0, opacity: 0.4, pointerEvents: "none" }}/>
        <div style={{
          position: "absolute", top: -100, right: -100, width: 360, height: 360, borderRadius: "50%",
          background: "radial-gradient(circle, color-mix(in srgb, var(--accent) 20%, transparent), transparent 70%)",
          animation: "float 8s ease-in-out infinite",
        }}/>
        <div style={{
          position: "absolute", bottom: -50, left: -50, width: 280, height: 280, borderRadius: "50%",
          background: "radial-gradient(circle, color-mix(in srgb, var(--secondary) 18%, transparent), transparent 70%)",
          animation: "float 10s ease-in-out infinite 1s",
        }}/>

        <div style={{ position: "relative", zIndex: 1 }}>
          <CodaraLogo size={28}/>
        </div>

        <div style={{ position: "relative", zIndex: 1, maxWidth: 460 }}>
          <div className="eyebrow" style={{ color: "var(--accent)", marginBottom: 12 }}>SAS → Python · faster than you'd think</div>
          <h2 style={{ fontSize: 36, fontWeight: 600, lineHeight: 1.1, letterSpacing: "-0.025em", marginBottom: 16 }}>
            Ship modernized Python in minutes, not months.
          </h2>
          <p className="text-muted" style={{ fontSize: 15, lineHeight: 1.6 }}>
            Codara translates SAS into production-grade Python with line-by-line provenance, full test coverage, and a knowledge base your team owns.
          </p>

          {/* Mini animated stat strip */}
          <div style={{ display: "flex", gap: 14, marginTop: 28 }}>
            <Mini label="Avg coverage" value="96%"/>
            <Mini label="Lines translated" value="2.4M"/>
            <Mini label="Time saved" value="180h"/>
          </div>
        </div>

        <div style={{ position: "relative", zIndex: 1, fontSize: 11, color: "var(--fg-subtle)" }}>
          © 2026 Codara · SOC 2 Type II · Enterprise-ready
        </div>
      </div>

      {/* Form side */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "center", padding: 48,
        order: side === "right" ? 1 : 0,
      }}>
        <div style={{ width: "100%", maxWidth: 380, animation: "pageIn 0.5s var(--ease-out) both" }}>
          {children}
        </div>
      </div>
    </div>
  );
}

const Mini = ({ label, value }) => (
  <div className="panel" style={{ padding: 12, flex: 1, background: "color-mix(in srgb, var(--surface) 70%, transparent)" }}>
    <div className="eyebrow">{label}</div>
    <div style={{ fontSize: 18, fontWeight: 600, fontFamily: "var(--font-display)", marginTop: 4 }}>{value}</div>
  </div>
);

function LoginPage({ navigate }) {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch (e: any) {
      setError(e.message || "Invalid credentials");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => { if (e.key === "Enter") handleLogin(); };

  return (
    <AuthShell>
      <h1 style={{ fontSize: 24, fontWeight: 600, marginBottom: 6 }}>Welcome back</h1>
      <p className="text-muted" style={{ fontSize: 13.5, marginBottom: 24 }}>Sign in to continue your conversions</p>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <button className="btn btn-lg" style={{ width: "100%" }}>
          <Icon name="globe" size={14}/> Continue with Google
        </button>
        <button className="btn btn-lg" style={{ width: "100%" }}>
          <Icon name="git" size={14}/> Continue with GitHub
        </button>
        <button className="btn btn-lg" style={{ width: "100%" }}>
          <Icon name="key" size={14}/> Continue with SSO
        </button>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "22px 0", color: "var(--fg-subtle)", fontSize: 11 }}>
        <div style={{ flex: 1, height: 1, background: "var(--border)" }}/> OR <div style={{ flex: 1, height: 1, background: "var(--border)" }}/>
      </div>

      {error && (
        <div style={{ padding: "10px 14px", borderRadius: "var(--radius)", background: "color-mix(in srgb, var(--danger) 10%, var(--bg-elev))", border: "1px solid color-mix(in srgb, var(--danger) 30%, transparent)", color: "var(--danger)", fontSize: 12.5, marginBottom: 8 }}>
          {error}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Email</div>
          <input className="input" placeholder="you@company.com" style={{ width: "100%", height: 38 }}
                 value={email} onChange={e => setEmail(e.target.value)} onKeyDown={handleKeyDown}/>
        </div>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
            <div className="eyebrow">Password</div>
            <a style={{ fontSize: 11, color: "var(--accent)" }}>Forgot?</a>
          </div>
          <input className="input" type="password" placeholder="••••••••" style={{ width: "100%", height: 38 }}
                 value={password} onChange={e => setPassword(e.target.value)} onKeyDown={handleKeyDown}/>
        </div>
        <button className="btn btn-primary btn-lg" onClick={handleLogin} disabled={loading} style={{ width: "100%", marginTop: 6 }}>
          {loading ? "Signing in…" : "Sign in"} <Icon name="arrowRight" size={13}/>
        </button>
      </div>

      <div style={{ marginTop: 28, fontSize: 12.5, color: "var(--fg-muted)", textAlign: "center" }}>
        Don't have an account? <a onClick={() => navigate("/signup")} style={{ color: "var(--accent)", fontWeight: 500 }}>Create one</a>
      </div>
    </AuthShell>
  );
}

function SignupPage({ navigate }) {
  const { signup } = useAuth();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const strength = useMemo(() => {
    let s = 0;
    if (password.length >= 8) s++;
    if (/[A-Z]/.test(password)) s++;
    if (/[0-9]/.test(password)) s++;
    if (/[^a-zA-Z0-9]/.test(password)) s++;
    return s;
  }, [password]);

  const handleSignup = async () => {
    setError("");
    if (!firstName || !email || !password) { setError("Please fill in all fields"); return; }
    setLoading(true);
    try {
      const name = [firstName, lastName].filter(Boolean).join(" ");
      const res = await signup(email, password, name);
      if (res.emailVerificationRequired) navigate("/verify-email");
      else navigate("/dashboard");
    } catch (e: any) {
      setError(e.message || "Signup failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell side="left">
      <h1 style={{ fontSize: 24, fontWeight: 600, marginBottom: 6 }}>Create your account</h1>
      <p className="text-muted" style={{ fontSize: 13.5, marginBottom: 24 }}>Free trial · 50 conversions included</p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
        <button className="btn btn-lg"><Icon name="globe" size={13}/> Google</button>
        <button className="btn btn-lg"><Icon name="git" size={13}/> GitHub</button>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "16px 0", color: "var(--fg-subtle)", fontSize: 11 }}>
        <div style={{ flex: 1, height: 1, background: "var(--border)" }}/> OR <div style={{ flex: 1, height: 1, background: "var(--border)" }}/>
      </div>

      {error && (
        <div style={{ padding: "10px 14px", borderRadius: "var(--radius)", background: "color-mix(in srgb, var(--danger) 10%, var(--bg-elev))", border: "1px solid color-mix(in srgb, var(--danger) 30%, transparent)", color: "var(--danger)", fontSize: 12.5, marginBottom: 8 }}>
          {error}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>First name</div>
            <input className="input" style={{ width: "100%", height: 38 }} value={firstName} onChange={e => setFirstName(e.target.value)}/>
          </div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Last name</div>
            <input className="input" style={{ width: "100%", height: 38 }} value={lastName} onChange={e => setLastName(e.target.value)}/>
          </div>
        </div>
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Work email</div>
          <input className="input" placeholder="you@company.com" style={{ width: "100%", height: 38 }} value={email} onChange={e => setEmail(e.target.value)}/>
        </div>
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Password</div>
          <input className="input" type="password" placeholder="••••••••" style={{ width: "100%", height: 38 }} value={password} onChange={e => setPassword(e.target.value)}/>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 4, marginTop: 6 }}>
            {[0, 1, 2, 3].map((v) => (
              <div key={v} style={{ height: 3, borderRadius: 2,
                background: v < strength ? "var(--success)" : "var(--surface-3)" }}/>
            ))}
          </div>
          <div className="text-subtle" style={{ fontSize: 11, marginTop: 4 }}>{strength < 2 ? "Weak" : strength < 4 ? "Good" : "Strong"} password</div>
        </div>
        <button className="btn btn-primary btn-lg" onClick={handleSignup} disabled={loading} style={{ width: "100%", marginTop: 6 }}>
          {loading ? "Creating…" : "Create account"} <Icon name="arrowRight" size={13}/>
        </button>
      </div>

      <div style={{ marginTop: 22, fontSize: 11.5, color: "var(--fg-subtle)", textAlign: "center", lineHeight: 1.6 }}>
        By signing up you agree to our Terms of Service and Privacy Policy.
        <br/>Already have an account? <a onClick={() => navigate("/login")} style={{ color: "var(--accent)", fontWeight: 500 }}>Sign in</a>
      </div>
    </AuthShell>
  );
}

function VerifyEmailPage({ navigate }) {
  const [digits, setDigits] = useState(["", "", "", "", "", ""]);
  return (
    <AuthShell>
      <div style={{
        width: 56, height: 56, borderRadius: "var(--radius-lg)", marginBottom: 18,
        background: "var(--accent-soft)", color: "var(--accent)",
        display: "inline-flex", alignItems: "center", justifyContent: "center",
      }}>
        <Icon name="mail" size={24}/>
      </div>
      <h1 style={{ fontSize: 24, fontWeight: 600, marginBottom: 6 }}>Check your email</h1>
      <p className="text-muted" style={{ fontSize: 13.5, marginBottom: 24 }}>
        We sent a 6-digit code to <span style={{ color: "var(--fg)" }} className="mono">m••••@codara.dev</span>
      </p>

      <div style={{ display: "flex", gap: 8 }}>
        {digits.map((d, i) => (
          <input key={i} className="input mono" value={d}
                 onChange={e => {
                   const next = [...digits];
                   next[i] = e.target.value.slice(-1);
                   setDigits(next);
                 }}
                 style={{ width: 48, height: 56, textAlign: "center", fontSize: 22, fontWeight: 600,
                          background: d ? "var(--accent-soft)" : "var(--bg-elev)",
                          color: d ? "var(--accent)" : "var(--fg)",
                          borderColor: d ? "var(--accent)" : "var(--border)" }}/>
        ))}
      </div>

      <button className="btn btn-primary btn-lg" onClick={() => navigate("/dashboard")} style={{ width: "100%", marginTop: 24 }}>
        Verify <Icon name="arrowRight" size={13}/>
      </button>

      <div style={{ marginTop: 18, fontSize: 12.5, color: "var(--fg-muted)", textAlign: "center" }}>
        Didn't get the email? <a style={{ color: "var(--accent)", fontWeight: 500 }}>Resend</a> in 0:42
      </div>
    </AuthShell>
  );
}

/* ─── ONBOARDING (NEW) ──────────────────────────────────── */
function OnboardingModal({ open, onClose, navigate }) {
  const [step, setStep] = useState(0);
  const steps = [
    {
      icon: "sparkles", title: "Welcome to Codara",
      body: "Translate SAS to production-ready Python in three steps. Let's take a 30-second tour.",
      illustration: "welcome",
    },
    {
      icon: "upload", title: "Upload your SAS",
      body: "Drag any .sas file — DATA steps, PROC SQL, macros — we'll parse the whole thing and chunk it intelligently.",
      illustration: "upload",
    },
    {
      icon: "git", title: "Review the diff",
      body: "Side-by-side SAS → Python with line-level provenance. Approve chunks, leave comments, or re-translate.",
      illustration: "diff",
    },
    {
      icon: "rocket", title: "Export & ship",
      body: "Production-ready Python with tests, type hints, and full traceability. Connect to GitHub for one-click PRs.",
      illustration: "ship",
    },
  ];

  if (!open) return null;
  const s = steps[step];

  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, background: "rgba(8,8,12,0.5)", zIndex: 200,
      display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
      animation: "fadeIn 0.2s ease-out both", backdropFilter: "blur(8px)",
    }}>
      <div onClick={e => e.stopPropagation()} className="panel-pop" style={{
        width: 720, maxWidth: "100%", overflow: "hidden",
        animation: "growIn 0.32s var(--ease-spring) both",
      }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1.2fr" }}>
          {/* Illustration */}
          <div style={{
            position: "relative", overflow: "hidden",
            background: "linear-gradient(135deg, color-mix(in srgb, var(--accent) 14%, var(--surface-2)), color-mix(in srgb, var(--secondary) 10%, var(--surface-2)))",
            display: "flex", alignItems: "center", justifyContent: "center", minHeight: 360,
          }}>
            <div className="dot-grid-fine" style={{ position: "absolute", inset: 0, opacity: 0.4 }}/>
            <OnboardingIllustration kind={s.illustration} stepKey={step}/>
          </div>

          {/* Content */}
          <div style={{ padding: 28, display: "flex", flexDirection: "column" }}>
            <div style={{ flex: 1 }}>
              <div className="eyebrow" style={{ color: "var(--accent)" }}>Step {step + 1} of {steps.length}</div>
              <div style={{
                width: 44, height: 44, borderRadius: "var(--radius-lg)", marginTop: 12,
                background: "var(--accent-soft)", color: "var(--accent)",
                display: "inline-flex", alignItems: "center", justifyContent: "center",
              }}><Icon name={s.icon} size={20}/></div>
              <h2 style={{ fontSize: 22, fontWeight: 600, marginTop: 14, marginBottom: 8 }}>{s.title}</h2>
              <p className="text-muted" style={{ fontSize: 13.5, lineHeight: 1.6 }}>{s.body}</p>
            </div>

            {/* Progress dots */}
            <div style={{ display: "flex", gap: 6, marginTop: 20, marginBottom: 16 }}>
              {steps.map((_, i) => (
                <div key={i} style={{
                  flex: i === step ? 3 : 1, height: 4, borderRadius: 2,
                  background: i <= step ? "var(--accent)" : "var(--surface-2)",
                  transition: "all 0.4s var(--ease-out)",
                }}/>
              ))}
            </div>

            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <button className="btn btn-ghost" onClick={onClose}>Skip tour</button>
              <div style={{ display: "flex", gap: 8 }}>
                {step > 0 && <button className="btn" onClick={() => setStep(step - 1)}>
                  <Icon name="chevronLeft" size={12}/> Back
                </button>}
                {step < steps.length - 1 ? (
                  <button className="btn btn-primary" onClick={() => setStep(step + 1)}>
                    Next <Icon name="arrowRight" size={12}/>
                  </button>
                ) : (
                  <button className="btn btn-primary" onClick={() => { onClose(); navigate("/conversions"); }}>
                    Start your first conversion <Icon name="arrowRight" size={12}/>
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function OnboardingIllustration({ kind, stepKey }) {
  // Different abstract illustrations per step
  return (
    <div key={stepKey} style={{
      width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center",
      animation: "growIn 0.5s var(--ease-spring) both",
    }}>
      {kind === "welcome" && (
        <svg width="220" height="220" viewBox="0 0 220 220">
          <circle cx="110" cy="110" r="90" fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeDasharray="4 6"
                  style={{ animation: "spin 30s linear infinite", transformOrigin: "110px 110px" }}/>
          <circle cx="110" cy="110" r="60" fill="none" stroke="var(--secondary)" strokeWidth="1.5" strokeDasharray="2 4"
                  style={{ animation: "spin 22s linear infinite reverse", transformOrigin: "110px 110px" }}/>
          <circle cx="110" cy="110" r="36" fill="var(--accent-soft)"/>
          <path d="M125 95 L95 110 L125 125" fill="none" stroke="var(--accent)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      )}
      {kind === "upload" && (
        <svg width="220" height="220" viewBox="0 0 220 220">
          {[0, 1, 2].map(i => (
            <rect key={i} x={50 + i * 12} y={70 + i * 12} width="120" height="80" rx="6"
                  fill="var(--surface)" stroke="var(--border-strong)" strokeWidth="1"
                  style={{ animation: `float 3s ease-in-out infinite ${i * 0.3}s`, transformOrigin: "center" }}/>
          ))}
          <path d="M110 50 L110 90 M95 65 L110 50 L125 65" stroke="var(--accent)" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
          <text x="110" y="125" fontFamily="var(--font-mono)" fontSize="11" textAnchor="middle" fill="var(--fg-muted)">claims_etl.sas</text>
        </svg>
      )}
      {kind === "diff" && (
        <svg width="220" height="220" viewBox="0 0 220 220">
          <rect x="20" y="50" width="80" height="120" rx="6" fill="var(--surface)" stroke="var(--border-strong)"/>
          <rect x="120" y="50" width="80" height="120" rx="6" fill="var(--surface)" stroke="var(--border-strong)"/>
          {[0, 1, 2, 3, 4].map(i => (
            <g key={i}>
              <rect x="30" y={62 + i * 18} width={50 + Math.sin(i) * 10} height="6" rx="1" fill={i === 2 ? "var(--danger)" : "var(--fg-subtle)"} opacity={i === 2 ? 0.4 : 0.3}/>
              <rect x="130" y={62 + i * 18} width={48 + Math.cos(i) * 14} height="6" rx="1" fill={i === 2 ? "var(--success)" : "var(--fg-subtle)"} opacity={i === 2 ? 0.5 : 0.3}/>
            </g>
          ))}
          <path d="M100 110 L120 110" stroke="var(--accent)" strokeWidth="2" strokeDasharray="3 3" style={{ animation: "dash 1s linear infinite" }}/>
          <circle cx="110" cy="110" r="12" fill="var(--accent-soft)" stroke="var(--accent)" strokeWidth="1.5"/>
          <path d="M104 110 L108 114 L116 106" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      )}
      {kind === "ship" && (
        <svg width="220" height="220" viewBox="0 0 220 220">
          <circle cx="110" cy="110" r="80" fill="var(--success-soft)" opacity="0.6"/>
          <circle cx="110" cy="110" r="50" fill="var(--success-soft)"/>
          <path d="M85 110 L105 130 L140 90" fill="none" stroke="var(--success)" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round"
                style={{ strokeDasharray: 100, strokeDashoffset: 100, animation: "drawLine 0.8s var(--ease-out) 0.3s forwards" }}/>
        </svg>
      )}
    </div>
  );
}
export { CostDashboardPage, PromptTemplatesPage, ErrorQueuePage, LoginPage, SignupPage, VerifyEmailPage, OnboardingModal };
