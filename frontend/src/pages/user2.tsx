import React, { useState, useEffect, useRef, useMemo, useCallback, createContext, useContext } from "react";
import type { ReactNode, CSSProperties } from "react";
import { useKnowledgeBase, useAnalytics, useNotifications, useConversions, useProjects } from "../lib/hooks";
import { useAuth } from "../lib/auth-context";
import { Icon, StatCard, StatusBadge, Avatar, AreaChart, BarChart, DonutChart, Sparkline, CalendarHeatmap, AnimatedNumber, ProgressBar, CodeBlock } from "../components/ui";

/* ──────────────────────────────────────────────────────────
   More user pages: KB, Analytics, Settings, Projects, Notifications
   ────────────────────────────────────────────────────────── */

/* ─── KNOWLEDGE BASE ──────────────────────────────────────── */
function KnowledgeBasePage({ navigate }) {
  const { data: liveKB } = useKnowledgeBase();
  const patterns = (liveKB || []).map(e => ({ id: e.id, title: `${e.category} pattern`, category: e.category, sas: e.sasSnippet, py: e.pythonTranslation, uses: 0, coverage: e.confidence, updated: e.updatedAt, status: "stable" }));
  const [active, setActive] = useState(null);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("all");

  useEffect(() => {
    if (patterns.length > 0 && !active) setActive(patterns[0]);
  }, [patterns.length]);
  const categories = ["all", ...new Set(patterns.map(p => p.category))];
  const filtered = patterns.filter(p =>
    (cat === "all" || p.category === cat) &&
    (q === "" || p.title.toLowerCase().includes(q.toLowerCase()))
  );

  return (
    <div className="page-in" style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 1400 }}>
      <div>
        <h1 style={{ fontSize: "var(--tw-h1)", fontWeight: 600 }}>Knowledge Base</h1>
        <p className="text-muted" style={{ marginTop: 4, fontSize: 14 }}>
          {patterns.length} translation patterns powering every conversion · Curated by your team
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: 14, minHeight: 580 }}>
        {/* List */}
        <div className="panel" style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{ padding: 14, borderBottom: "1px solid var(--border)" }}>
            <div style={{
              display: "flex", alignItems: "center", gap: 8, padding: "8px 10px",
              background: "var(--bg-elev)", borderRadius: "var(--radius)", border: "1px solid var(--border)",
            }}>
              <Icon name="search" size={13} className="text-muted"/>
              <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search patterns…"
                     style={{ flex: 1, fontSize: 12.5 }}/>
            </div>
            <div style={{ display: "flex", gap: 4, marginTop: 10, flexWrap: "wrap" }}>
              {categories.map(c => (
                <button key={c} onClick={() => setCat(c)} className="badge" style={{
                  background: cat === c ? "var(--accent-soft)" : "var(--surface-2)",
                  color: cat === c ? "var(--accent)" : "var(--fg-muted)",
                  cursor: "default", border: 0, textTransform: "capitalize", fontSize: 10.5,
                }}>{c}</button>
              ))}
            </div>
          </div>
          <div style={{ flex: 1, overflowY: "auto" }}>
            {filtered.map((p, i) => (
              <button key={p.id} onClick={() => setActive(p)} style={{
                width: "100%", padding: "12px 14px", textAlign: "left",
                borderBottom: "1px solid var(--border)",
                borderLeft: active?.id === p.id ? "2px solid var(--accent)" : "2px solid transparent",
                background: active?.id === p.id ? "var(--surface-2)" : "transparent",
                animation: "pageIn 0.3s var(--ease-out) both", animationDelay: `${i * 30}ms`,
              }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                  <div style={{ fontWeight: 500, fontSize: 13 }}>{p.title}</div>
                  <StatusBadge status={p.status}/>
                </div>
                <div style={{ display: "flex", gap: 10, fontSize: 11, color: "var(--fg-subtle)" }}>
                  <span>{p.category}</span>
                  <span>·</span>
                  <span className="mono">{p.uses.toLocaleString()} uses</span>
                  <span>·</span>
                  <span className="mono">{Math.round(p.coverage * 100)}% cov</span>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Detail */}
        {active && (
          <div className="panel" style={{ overflow: "auto" }}>
            <div style={{ padding: "20px 22px", borderBottom: "1px solid var(--border)" }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                <div>
                  <div className="eyebrow">{active.category}</div>
                  <h2 style={{ fontSize: 20, fontWeight: 600, marginTop: 4 }}>{active.title}</h2>
                </div>
                <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                  <button className="btn btn-sm"><Icon name="edit" size={12}/> Edit</button>
                  <button className="btn btn-sm"><Icon name="copy" size={12}/> Fork</button>
                </div>
              </div>
              <div style={{ display: "flex", gap: 18, marginTop: 14, fontSize: 12 }}>
                <div><span className="text-subtle">Uses </span><span className="mono" style={{ fontWeight: 600 }}>{active.uses.toLocaleString()}</span></div>
                <div><span className="text-subtle">Coverage </span><span className="mono" style={{ fontWeight: 600 }}>{Math.round(active.coverage * 100)}%</span></div>
                <div><span className="text-subtle">Updated </span><span className="mono">{active.updated}</span></div>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
              <div style={{ borderRight: "1px solid var(--border)" }}>
                <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="badge"><Icon name="tag" size={9}/> SAS</span>
                  <span className="text-muted" style={{ fontSize: 11.5 }}>source pattern</span>
                </div>
                <div style={{ padding: "8px 0" }}>
                  <CodeBlock code={active.sas} lang="sas"/>
                </div>
              </div>
              <div>
                <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="badge badge-accent"><Icon name="package" size={9}/> Python</span>
                  <span className="text-muted" style={{ fontSize: 11.5 }}>translation</span>
                </div>
                <div style={{ padding: "8px 0" }}>
                  <CodeBlock code={active.py} lang="py"/>
                </div>
              </div>
            </div>

            <AppliedInSection navigate={navigate}/>
          </div>
        )}
      </div>
    </div>
  );
}

function AppliedInSection({ navigate }) {
  const { data: convs } = useConversions();
  const items = (convs || []).slice(0, 5);
  if (items.length === 0) return null;
  return (
    <div style={{ padding: 20, borderTop: "1px solid var(--border)" }}>
      <div className="eyebrow" style={{ marginBottom: 10 }}>Applied in</div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {items.map(c => (
          <button key={c.id} className="badge" style={{ cursor: "default" }}
                  onClick={() => navigate(`/workspace/${c.id}`)}>
            <Icon name="fileCode" size={10}/> {c.fileName}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ─── ANALYTICS ───────────────────────────────────────────── */
function AnalyticsPage() {
  const { data: liveAnalytics } = useAnalytics();
  const data = (liveAnalytics || []).map(d => ({ ...d, completed: d.conversions - d.failures, partial: 0, cost: 0, tokens: 0 }));
  const [range, setRange] = useState("30d");
  const visible = range === "7d" ? data.slice(-7) : range === "14d" ? data.slice(-14) : data;

  const totalConv = visible.reduce((a, d) => a + d.conversions, 0);
  const totalFail = visible.reduce((a, d) => a + d.failures, 0);
  const totalCost = visible.reduce((a, d) => a + d.cost, 0);
  const successRate = totalConv > 0 ? ((1 - totalFail / totalConv) * 100).toFixed(1) : "0.0";
  const totalTokens = visible.reduce((a, d) => a + d.tokens, 0);

  const byHour = Array.from({ length: 24 }, (_, h) => ({
    h, value: Math.round(2 + Math.sin(h / 24 * Math.PI * 2 - 1.5) * 4 + Math.random() * 3 + (h >= 9 && h <= 17 ? 6 : 0))
  }));

  return (
    <div className="page-in" style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 1400 }}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: "var(--tw-h1)", fontWeight: 600 }}>Analytics</h1>
          <p className="text-muted" style={{ marginTop: 4, fontSize: 14 }}>
            Your conversion patterns, success rates, and performance over time
          </p>
        </div>
        <div className="toggle-pill">
          {["7d", "14d", "30d"].map(r => (
            <button key={r} onClick={() => setRange(r)} aria-selected={range === r}>{r}</button>
          ))}
        </div>
      </div>

      {/* KPIs */}
      <div className="stagger" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
        <StatCard label="Conversions" value={totalConv} delta="+18%" deltaType="up" icon="fileCode"
                  sparkData={visible.map(d => d.conversions)} tone="accent"/>
        <StatCard label="Success rate" value={`${successRate}%`} delta="+2.4pt" deltaType="up" icon="checkCircle"/>
        <StatCard label="LLM cost" value={`$${totalCost.toFixed(0)}`} delta="-12%" deltaType="up" icon="dollar"
                  sparkData={visible.map(d => d.cost)}/>
        <StatCard label="Tokens used" value={`${(totalTokens/1e6).toFixed(1)}M`} icon="zap"
                  sparkData={visible.map(d => d.tokens / 1000)}/>
      </div>

      {/* Conversions over time */}
      <div className="panel" style={{ padding: 20 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <h2 style={{ fontSize: "var(--tw-h2)", fontWeight: 600 }}>Conversion volume & failures</h2>
          <div style={{ display: "flex", gap: 14, fontSize: 11 }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--chart-1)" }}/> Completed
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--chart-5)" }}/> Failed
            </span>
          </div>
        </div>
        <AreaChart data={visible} height={220}
                   keys={[
                     { key: "conversions", color: "var(--chart-1)" },
                     { key: "failures", color: "var(--chart-5)" },
                   ]}/>
      </div>

      {/* Pattern breakdown + Latency */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div className="panel" style={{ padding: 20 }}>
          <h2 style={{ fontSize: "var(--tw-h2)", fontWeight: 600, marginBottom: 14 }}>Average latency (sec)</h2>
          <BarChart data={visible} valueKey="avgLatency" color="var(--chart-2)" height={200}/>
        </div>
        <div className="panel" style={{ padding: 20 }}>
          <h2 style={{ fontSize: "var(--tw-h2)", fontWeight: 600, marginBottom: 14 }}>Activity heatmap</h2>
          <CalendarHeatmap data={visible.map(d => ({ label: d.date, value: d.conversions }))}
                           cols={Math.ceil(visible.length / 1)} rows={1} color="var(--chart-1)"/>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 16, fontSize: 11, color: "var(--fg-subtle)" }}>
            <span>{visible.length > 0 ? visible[0].date : ""}</span>
            <span>{visible.length > 0 ? visible[visible.length-1].date : ""}</span>
          </div>
          <div style={{ marginTop: 22 }}>
            <div className="eyebrow" style={{ marginBottom: 8 }}>By hour (last 24h)</div>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 60 }}>
              {byHour.map((h, i) => (
                <div key={i} style={{
                  flex: 1, background: "var(--chart-2)", borderRadius: 2,
                  height: `${(h.value / Math.max(...byHour.map(b => b.value))) * 100}%`,
                  opacity: 0.55 + (h.value / Math.max(...byHour.map(b => b.value))) * 0.45,
                  animation: "growBar 0.5s var(--ease-spring) both",
                  animationDelay: `${i * 20}ms`,
                  transformOrigin: "bottom",
                }} title={`${h.h}:00 — ${h.value}`}/>
              ))}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 10, color: "var(--fg-subtle)" }}>
              <span>0:00</span><span>12:00</span><span>23:00</span>
            </div>
          </div>
        </div>
      </div>

      {/* Pattern usage */}
      <TopPatternsSection/>
    </div>
  );
}

function TopPatternsSection() {
  const { data: liveKB } = useKnowledgeBase();
  const kbPatterns = (liveKB || []).map(e => ({ id: e.id, title: `${e.category} pattern`, category: e.category, uses: 0 }));
  const top5 = kbPatterns.slice(0, 5);
  const totalUses = kbPatterns.reduce((a, p) => a + p.uses, 0);
  return (
    <div className="panel" style={{ padding: 20 }}>
      <h2 style={{ fontSize: "var(--tw-h2)", fontWeight: 600, marginBottom: 14 }}>Top translation patterns</h2>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32, alignItems: "center" }}>
        <DonutChart size={200} thickness={28}
          data={top5.map((p, i) => ({
            value: Math.max(p.uses, 1), color: `var(--chart-${i + 1})`, label: p.title
          }))}
          center={
            <>
              <div className="eyebrow">Patterns used</div>
              <div style={{ fontSize: 28, fontWeight: 700, fontFamily: "var(--font-display)" }}>
                <AnimatedNumber value={totalUses}/>
              </div>
              <div className="text-subtle" style={{ fontSize: 11 }}>this period</div>
            </>
          }/>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {top5.map((p, i) => (
            <div key={p.id} style={{
              display: "flex", alignItems: "center", gap: 12, padding: "8px 12px",
              borderRadius: "var(--radius)", background: "var(--bg-elev)", border: "1px solid var(--border)",
            }}>
              <div style={{ width: 10, height: 10, borderRadius: 2, background: `var(--chart-${i + 1})` }}/>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 500, fontSize: 12.5 }}>{p.title}</div>
                <div className="text-subtle" style={{ fontSize: 11 }}>{p.category}</div>
              </div>
              <div className="mono" style={{ fontSize: 13, fontWeight: 500 }}>{p.uses.toLocaleString()}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ─── SETTINGS ────────────────────────────────────────────── */
function SettingsPage() {
  const [tab, setTab] = useState("profile");
  const { user: authUser } = useAuth();
  const u = authUser ? { name: authUser.name, email: authUser.email, role: authUser.role, joined: authUser.createdAt || new Date().toISOString(), timezone: "UTC" } : { name: "", email: "", role: "user", joined: new Date().toISOString(), timezone: "UTC" };

  return (
    <div className="page-in" style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 920 }}>
      <div>
        <h1 style={{ fontSize: "var(--tw-h1)", fontWeight: 600 }}>Settings</h1>
        <p className="text-muted" style={{ marginTop: 4, fontSize: 14 }}>
          Manage your profile, API keys, and notification preferences
        </p>
      </div>

      <div className="tabs">
        {["profile", "api keys", "notifications", "preferences", "billing"].map(t => (
          <button key={t} className="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                  style={{ textTransform: "capitalize" }}>{t}</button>
        ))}
      </div>

      {tab === "profile" && (
        <div className="panel" style={{ padding: 24, display: "flex", flexDirection: "column", gap: 18 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <Avatar name={u.name} size={56}/>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{u.name}</div>
              <div className="text-muted" style={{ fontSize: 13 }}>{u.email}</div>
              <div style={{ marginTop: 6, display: "flex", gap: 6 }}>
                <span className="badge badge-accent" style={{ textTransform: "capitalize" }}>{u.role}</span>
                <span className="badge">Joined {new Date(u.joined).toLocaleDateString(undefined, { month: "short", year: "numeric" })}</span>
              </div>
            </div>
            <button className="btn">Edit photo</button>
          </div>

          <div style={{ height: 1, background: "var(--border)" }}/>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
            <Field label="Display name" value={u.name}/>
            <Field label="Email" value={u.email}/>
            <Field label="Timezone" value={u.timezone}/>
            <Field label="Default project" value="Claims Pipeline 2026"/>
          </div>

          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button className="btn">Discard</button>
            <button className="btn btn-primary">Save changes</button>
          </div>
        </div>
      )}

      {tab === "api keys" && (
        <div className="panel" style={{ overflow: "hidden" }}>
          <div style={{ padding: 20, borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>API keys</div>
              <div className="text-muted" style={{ fontSize: 12, marginTop: 2 }}>
                Use these to run conversions programmatically via the Codara API
              </div>
            </div>
            <button className="btn btn-primary"><Icon name="plus" size={12}/> Create key</button>
          </div>
          {[
            { name: "CI/CD pipeline", prefix: "cdr_live_", masked: "9f2a…b41c", created: "2026-03-12", last: "2m ago" },
            { name: "Local dev", prefix: "cdr_test_", masked: "0c8d…a92e", created: "2026-04-08", last: "1h ago" },
            { name: "Notebooks", prefix: "cdr_live_", masked: "5b1f…d4a8", created: "2026-01-22", last: "3d ago" },
          ].map((k, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 220px 130px 130px 60px", gap: 14, padding: "14px 20px",
                                  borderBottom: "1px solid var(--border)", alignItems: "center" }}>
              <div>
                <div style={{ fontWeight: 500, fontSize: 13 }}>{k.name}</div>
              </div>
              <div className="mono" style={{ fontSize: 12, color: "var(--fg-muted)" }}>{k.prefix}{k.masked}</div>
              <div style={{ fontSize: 12 }}>{k.created}</div>
              <div style={{ fontSize: 12, color: "var(--fg-muted)" }}>Used {k.last}</div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 4 }}>
                <button className="btn btn-icon btn-ghost"><Icon name="copy" size={12}/></button>
                <button className="btn btn-icon btn-ghost"><Icon name="trash" size={12}/></button>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "notifications" && (
        <div className="panel" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 12 }}>
          {[
            { l: "Conversion complete", d: "When one of your conversions finishes", on: true },
            { l: "Conversion failed", d: "When a conversion fails or partially completes", on: true },
            { l: "Comments & mentions", d: "When someone @-mentions you in a workspace", on: true },
            { l: "KB pattern published", d: "When admins publish or update KB patterns", on: false },
            { l: "Weekly digest", d: "A Monday summary of your conversions & usage", on: true },
          ].map((n, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px",
                                  borderRadius: "var(--radius)", border: "1px solid var(--border)" }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 500, fontSize: 13 }}>{n.l}</div>
                <div className="text-muted" style={{ fontSize: 12 }}>{n.d}</div>
              </div>
              <Toggle on={n.on}/>
            </div>
          ))}
        </div>
      )}

      {tab === "preferences" && (
        <div className="panel" style={{ padding: 24, display: "flex", flexDirection: "column", gap: 18 }}>
          <Field label="Default target runtime" value="Python · pandas"/>
          <Field label="Default test coverage" value="Full"/>
          <Field label="Diff view default" value="Split"/>
          <Field label="Code font" value="JetBrains Mono"/>
        </div>
      )}

      {tab === "billing" && (
        <div className="panel" style={{ padding: 24 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <div>
              <div className="eyebrow">Current plan</div>
              <div style={{ fontSize: 22, fontWeight: 600, marginTop: 4 }}>Team · $99/month</div>
            </div>
            <button className="btn">Manage plan</button>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
            <StatCard label="Conversions this month" value="142" sub="of 500 included"/>
            <StatCard label="Tokens this month" value="3.2M" sub="of 10M included"/>
            <StatCard label="Bill to date" value="$42.18"/>
          </div>
        </div>
      )}
    </div>
  );
}

const Field = ({ label, value }) => (
  <div>
    <div className="eyebrow" style={{ marginBottom: 6 }}>{label}</div>
    <input className="input" defaultValue={value} style={{ width: "100%", height: 36 }}/>
  </div>
);

const Toggle = ({ on }) => {
  const [v, setV] = useState(on);
  return (
    <button onClick={() => setV(!v)} style={{
      width: 36, height: 20, borderRadius: 999, padding: 2,
      background: v ? "var(--accent)" : "var(--surface-3)",
      transition: "background 0.2s var(--ease-out)",
      position: "relative",
    }}>
      <span style={{
        display: "block", width: 16, height: 16, borderRadius: 999, background: "white",
        transform: v ? "translateX(16px)" : "translateX(0)",
        transition: "transform 0.22s var(--ease-spring)",
        boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
      }}/>
    </button>
  );
};

/* ─── PROJECTS (NEW) ─────────────────────────────────────── */
function ProjectsPage({ navigate }) {
  const { data: liveProjects } = useProjects();
  const projects = (liveProjects || []).map(p => ({ ...p, owner: p.ownerName || "", updated: p.updatedAt || "" }));

  return (
    <div className="page-in" style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 1280 }}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <h1 style={{ fontSize: "var(--tw-h1)", fontWeight: 600 }}>Projects</h1>
            <span className="badge badge-accent">NEW</span>
          </div>
          <p className="text-muted" style={{ fontSize: 14 }}>
            Group related SAS files. Track progress as you migrate entire codebases.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => window.codara?.openNewProject()}><Icon name="plus" size={13}/> New project</button>
      </div>

      <div className="stagger" style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14 }}>
        {projects.map(p => {
          const pct = p.files > 0 ? Math.round((p.converted/p.files)*100) : 0;
          return (
            <div key={p.id} className="panel" style={{ padding: 18, position: "relative", overflow: "hidden", cursor: "default",
                                                       transition: "transform 0.18s var(--ease-out)" }}
                 onMouseEnter={e => e.currentTarget.style.transform = "translateY(-2px)"}
                 onMouseLeave={e => e.currentTarget.style.transform = "translateY(0)"}>
              <div style={{
                position: "absolute", top: 0, right: 0, width: 100, height: 100,
                background: `radial-gradient(circle at top right, color-mix(in srgb, var(--${p.color}) 22%, transparent), transparent 70%)`,
              }}/>
              <div style={{ position: "relative" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
                  <div style={{
                    width: 40, height: 40, borderRadius: "var(--radius)",
                    background: `color-mix(in srgb, var(--${p.color}) 16%, var(--surface-2))`,
                    color: `var(--${p.color})`,
                    display: "inline-flex", alignItems: "center", justifyContent: "center",
                  }}><Icon name="layers" size={16}/></div>
                  <StatusBadge status={p.status}/>
                </div>
                <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4 }}>{p.name}</div>
                <div className="text-subtle" style={{ fontSize: 11.5, marginBottom: 16 }}>
                  Owner: {p.owner} · Updated {p.updated}
                </div>
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 6 }}>
                  <span className="eyebrow">Migration progress</span>
                  <span className="mono" style={{ fontWeight: 600 }}>{pct}%</span>
                </div>
                <div style={{ height: 6, background: "var(--surface-2)", borderRadius: 999, overflow: "hidden", marginBottom: 6 }}>
                  <div style={{ width: `${pct}%`, height: "100%", background: `var(--${p.color})`,
                                transition: "width 1.2s var(--ease-out)" }}/>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--fg-subtle)" }}>
                  <span><span className="mono">{p.converted}</span> converted</span>
                  <span><span className="mono">{p.files - p.converted}</span> remaining</span>
                </div>

                <div style={{ marginTop: 14, display: "flex", gap: 6 }}>
                  <button className="btn btn-sm" style={{ flex: 1 }}>Open <Icon name="arrowRight" size={11}/></button>
                  <button className="btn btn-sm btn-icon"><Icon name="more" size={12}/></button>
                </div>
              </div>
            </div>
          );
        })}

        {/* New project card */}
        <button className="panel" onClick={() => window.codara?.openNewProject()} style={{
          padding: 18, border: "1.5px dashed var(--border-strong)", background: "transparent",
          display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 10,
          minHeight: 200, color: "var(--fg-muted)", cursor: "default",
          transition: "border-color 0.18s, color 0.18s",
        }} onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--accent)"; e.currentTarget.style.color = "var(--accent)"; }}
           onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border-strong)"; e.currentTarget.style.color = "var(--fg-muted)"; }}>
          <Icon name="plus" size={20}/>
          <span style={{ fontSize: 13 }}>New project</span>
        </button>
      </div>
    </div>
  );
}

/* ─── NOTIFICATIONS (NEW) ─────────────────────────────────── */
function NotificationsPage({ navigate }) {
  const { data: liveNotifs, markRead, markAllRead } = useNotifications();
  const ns = (liveNotifs || []).map(n => ({ id: n.id, kind: n.type, title: n.title, body: n.message, at: n.createdAt, read: n.read, link: "/dashboard" }));
  const [filter, setFilter] = useState("all");
  const visible = ns.filter(n => filter === "all" || (filter === "unread" && !n.read));

  const iconFor = (k) => k === "success" ? "checkCircle" : k === "warning" ? "alert" :
                        k === "danger" || k === "error" ? "xCircle" : "bell";
  const colorFor = (k) => k === "success" ? "var(--success)" : k === "warning" ? "var(--warning)" :
                          k === "danger" || k === "error" ? "var(--danger)" : "var(--info)";

  return (
    <div className="page-in" style={{ display: "flex", flexDirection: "column", gap: 18, maxWidth: 760 }}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
            <h1 style={{ fontSize: "var(--tw-h1)", fontWeight: 600 }}>Notifications</h1>
            <span className="badge badge-accent">NEW</span>
          </div>
          <p className="text-muted" style={{ fontSize: 14, marginTop: 4 }}>
            Conversion outcomes, mentions, and team activity in one place
          </p>
        </div>
        <button className="btn btn-sm">Mark all read</button>
      </div>

      <div className="toggle-pill" style={{ alignSelf: "flex-start" }}>
        {["all", "unread"].map(f => (
          <button key={f} onClick={() => setFilter(f)} aria-selected={filter === f}
                  style={{ textTransform: "capitalize" }}>
            {f} {f === "unread" && `(${ns.filter(n => !n.read).length})`}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {visible.map((n, i) => (
          <button key={n.id} onClick={() => navigate(n.link)} className="panel" style={{
            padding: "14px 18px", textAlign: "left",
            display: "flex", alignItems: "flex-start", gap: 14, width: "100%",
            background: n.read ? "var(--surface)" : "var(--bg-elev)",
            animation: "pageIn 0.32s var(--ease-out) both", animationDelay: `${i * 30}ms`,
            transition: "border-color 0.16s, transform 0.16s",
          }} onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--border-strong)"; e.currentTarget.style.transform = "translateX(2px)"; }}
             onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.transform = "translateX(0)"; }}>
            <div style={{
              width: 32, height: 32, borderRadius: "var(--radius)",
              background: `color-mix(in srgb, ${colorFor(n.kind)} 14%, transparent)`,
              color: colorFor(n.kind),
              display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
            }}><Icon name={iconFor(n.kind)} size={15}/></div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 2 }}>
                <span style={{ fontWeight: 500, fontSize: 13.5 }}>{n.title}</span>
                {!n.read && <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--accent)" }}/>}
                <div style={{ flex: 1 }}/>
                <span className="text-subtle mono" style={{ fontSize: 10.5 }}>{n.at}</span>
              </div>
              <div className="text-muted" style={{ fontSize: 12.5, lineHeight: 1.5 }}>{n.body}</div>
            </div>
            <Icon name="chevronRight" size={13} className="text-subtle" style={{ alignSelf: "center" }}/>
          </button>
        ))}
      </div>
    </div>
  );
}
export { KnowledgeBasePage, AnalyticsPage, SettingsPage, ProjectsPage, NotificationsPage };
