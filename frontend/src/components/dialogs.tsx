import React, { useState, useEffect, useRef, useMemo, useCallback, createContext, useContext } from "react";
import type { ReactNode, CSSProperties } from "react";
import { Icon } from "./ui";
import { Modal, useToast } from "./ambient";

/* ──────────────────────────────────────────────────────────
   Dialogs — wired, real interactions
   ────────────────────────────────────────────────────────── */

/* ── New Project dialog ─────────────────────────────────── */
function NewProjectDialog({ open, onClose, onCreated }) {
  const [name, setName] = useState("");
  const [color, setColor] = useState("chart-1");
  const [target, setTarget] = useState("python");
  const [desc, setDesc] = useState("");
  const toast = useToast();

  const reset = () => { setName(""); setDesc(""); setColor("chart-1"); setTarget("python"); };
  const handleClose = () => { onClose(); setTimeout(reset, 250); };

  const submit = () => {
    if (!name.trim()) {
      toast("Project needs a name", { kind: "warning", icon: "alert" });
      return;
    }
    toast(`Project "${name}" created`, { kind: "success", icon: "checkCircle" });
    onCreated && onCreated({ name, color, target, desc });
    handleClose();
  };

  const colors = ["chart-1", "chart-2", "chart-3", "chart-4", "chart-5"];

  return (
    <Modal
      open={open} onClose={handleClose}
      title="New project" subtitle="Group related SAS files for batch conversion"
      icon="layers" width={520}
      footer={
        <>
          <button className="btn" onClick={handleClose}>Cancel</button>
          <button className="btn btn-primary" onClick={submit}>
            <Icon name="plus" size={12}/> Create project
          </button>
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Name</div>
          <input
            autoFocus
            className="input"
            placeholder="e.g. Claims pipeline 2026"
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === "Enter" && submit()}
            style={{ width: "100%", height: 38 }}
          />
        </div>

        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Description</div>
          <textarea
            className="input"
            placeholder="Short description visible to the team"
            value={desc}
            onChange={e => setDesc(e.target.value)}
            rows={3}
            style={{ width: "100%", padding: 10, resize: "vertical", lineHeight: 1.5 }}
          />
        </div>

        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Color</div>
          <div style={{ display: "flex", gap: 8 }}>
            {colors.map(c => (
              <button key={c} onClick={() => setColor(c)} aria-label={c} style={{
                width: 30, height: 30, borderRadius: 999,
                background: `var(--${c})`,
                border: color === c ? "2.5px solid var(--fg)" : "2px solid var(--border)",
                outline: color === c ? "2px solid var(--bg)" : "none",
                outlineOffset: -3,
                transition: "transform 0.15s var(--ease-spring)",
                transform: color === c ? "scale(1.08)" : "scale(1)",
              }}/>
            ))}
          </div>
        </div>

        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Target runtime</div>
          <div className="toggle-pill" style={{ width: "100%", padding: 3 }}>
            {[
              { v: "python", l: "Python · pandas" },
              { v: "polars", l: "Python · polars" },
            ].map(o => (
              <button key={o.v} aria-selected={target === o.v}
                      onClick={() => setTarget(o.v)}
                      style={{ flex: 1, padding: "7px 0", fontSize: 12 }}>{o.l}</button>
            ))}
          </div>
        </div>

        <div style={{
          padding: 12, background: "var(--bg-elev)", borderRadius: "var(--radius)",
          border: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10,
        }}>
          <Icon name="sparkles" size={14} className="text-accent"/>
          <div style={{ fontSize: 12, lineHeight: 1.5 }}>
            <span style={{ fontWeight: 500 }}>Auto-detect KB patterns </span>
            <span className="text-muted">— we'll suggest existing translations as you convert files in this project.</span>
          </div>
        </div>
      </div>
    </Modal>
  );
}

/* ── Keyboard shortcuts modal ───────────────────────────── */
function ShortcutsDialog({ open, onClose }) {
  const sections = [
    { title: "Navigation", items: [
      { keys: ["⌘", "K"], label: "Open command palette" },
      { keys: ["G", "D"], label: "Go to dashboard" },
      { keys: ["G", "W"], label: "Go to workspace" },
      { keys: ["G", "H"], label: "Go to history" },
      { keys: ["?"],      label: "Show shortcuts" },
    ]},
    { title: "Conversion", items: [
      { keys: ["U"],       label: "Upload new files" },
      { keys: ["⌘", "↵"],  label: "Start conversion" },
      { keys: ["⌘", "/"],  label: "Toggle diff view" },
      { keys: ["J", "K"],  label: "Next / previous chunk" },
    ]},
    { title: "Workspace", items: [
      { keys: ["A"],       label: "Approve chunk" },
      { keys: ["R"],       label: "Re-translate chunk" },
      { keys: ["C"],       label: "Add comment" },
      { keys: ["⌘", "S"],  label: "Save / export" },
    ]},
  ];
  return (
    <Modal open={open} onClose={onClose} title="Keyboard shortcuts" icon="command" width={560}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        {sections.map((s, i) => (
          <div key={i}>
            <div className="eyebrow" style={{ marginBottom: 10 }}>{s.title}</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {s.items.map((it, j) => (
                <div key={j} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "4px 0", fontSize: 12.5,
                }}>
                  <span className="text-muted">{it.label}</span>
                  <span style={{ display: "flex", gap: 4 }}>
                    {it.keys.map((k, n) => <kbd key={n}>{k}</kbd>)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Modal>
  );
}

/* ── What's new dialog ──────────────────────────────────── */
function WhatsNewDialog({ open, onClose }) {
  const items = [
    { date: "May 12", tag: "NEW", title: "Cost dashboard", body: "Track LLM spend by model with budget alerts.", icon: "dollar" },
    { date: "May 09", tag: "NEW", title: "Error triage queue", body: "Failed conversions in one inbox with one-click retries.", icon: "alert" },
    { date: "May 02", tag: "IMPROVED", title: "Faster pipeline", body: "Average conversion now 32% faster on >500 LOC files.", icon: "zap" },
    { date: "Apr 24", tag: "NEW", title: "Prompt templates", body: "Version-controlled LLM prompts powering each pipeline stage.", icon: "terminal" },
    { date: "Apr 18", tag: "IMPROVED", title: "Diff annotations", body: "Inline KB pattern badges show which rule applied where.", icon: "git" },
  ];
  return (
    <Modal open={open} onClose={onClose} title="What's new" subtitle="Recent shipped changes" icon="sparkles" width={520}>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {items.map((it, i) => (
          <div key={i} style={{
            display: "flex", gap: 12, padding: 12,
            background: "var(--bg-elev)", borderRadius: "var(--radius)",
            border: "1px solid var(--border)",
            animation: "pageIn 0.32s var(--ease-out) both",
            animationDelay: `${i * 60}ms`,
          }}>
            <div style={{
              width: 30, height: 30, borderRadius: "var(--radius)", flexShrink: 0,
              background: it.tag === "NEW" ? "var(--accent-soft)" : "var(--success-soft)",
              color: it.tag === "NEW" ? "var(--accent)" : "var(--success)",
              display: "inline-flex", alignItems: "center", justifyContent: "center",
            }}><Icon name={it.icon} size={14}/></div>
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ fontWeight: 600, fontSize: 13 }}>{it.title}</span>
                <span className={`badge ${it.tag === "NEW" ? "badge-accent" : "badge-success"}`}
                      style={{ fontSize: 9.5 }}>{it.tag}</span>
                <span style={{ flex: 1 }}/>
                <span className="text-subtle mono" style={{ fontSize: 10.5 }}>{it.date}</span>
              </div>
              <div className="text-muted" style={{ fontSize: 12, lineHeight: 1.5 }}>{it.body}</div>
            </div>
          </div>
        ))}
      </div>
    </Modal>
  );
}

/* ── Share dialog ───────────────────────────────────────── */
function ShareDialog({ open, onClose, fileName }) {
  const [copied, setCopied] = useState(false);
  const link = `https://codara.dev/share/${(fileName || "conversion").replace(/\W/g, "-")}-${Math.random().toString(36).slice(2, 8)}`;
  const toast = useToast();
  const copy = () => {
    try { navigator.clipboard?.writeText(link); } catch {}
    setCopied(true);
    toast("Share link copied", { kind: "success", icon: "copy" });
    setTimeout(() => setCopied(false), 1800);
  };
  return (
    <Modal open={open} onClose={onClose} title="Share conversion"
           subtitle={fileName || "Anyone with the link can view"} icon="share" width={520}>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Share link</div>
          <div style={{ display: "flex", gap: 8 }}>
            <input className="input mono" value={link} readOnly style={{ flex: 1, fontSize: 11.5 }}/>
            <button className="btn btn-primary" onClick={copy}>
              <Icon name={copied ? "check" : "copy"} size={12}/> {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </div>
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Access</div>
          <div className="toggle-pill" style={{ width: "100%", padding: 3 }}>
            <button aria-selected="true" style={{ flex: 1, padding: "7px 0", fontSize: 12 }}>Anyone with link</button>
            <button style={{ flex: 1, padding: "7px 0", fontSize: 12 }}>Team only</button>
            <button style={{ flex: 1, padding: "7px 0", fontSize: 12 }}>Specific people</button>
          </div>
        </div>
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Send to</div>
          <input className="input" placeholder="name@company.com, comma-separated"
                 style={{ width: "100%", height: 38 }}/>
        </div>
      </div>
    </Modal>
  );
}

/* ── Invite teammates dialog ────────────────────────────── */
function InviteDialog({ open, onClose }) {
  const [emails, setEmails] = useState("");
  const toast = useToast();
  const send = () => {
    const n = emails.split(",").filter(e => e.trim()).length;
    if (!n) { toast("Add at least one email", { kind: "warning", icon: "alert" }); return; }
    toast(`Sent ${n} invite${n === 1 ? "" : "s"}`, { kind: "success", icon: "send" });
    setEmails("");
    onClose();
  };
  return (
    <Modal open={open} onClose={onClose} title="Invite teammates"
           subtitle="They'll get an email with a sign-in link" icon="users" width={520}
           footer={
             <>
               <button className="btn" onClick={onClose}>Cancel</button>
               <button className="btn btn-primary" onClick={send}>
                 <Icon name="send" size={12}/> Send invites
               </button>
             </>
           }>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Emails</div>
          <textarea className="input"
                    placeholder="ada@company.com, grace@company.com"
                    value={emails} onChange={e => setEmails(e.target.value)}
                    rows={3} style={{ width: "100%", padding: 10, resize: "vertical" }}/>
        </div>
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Role</div>
          <div className="toggle-pill" style={{ width: "100%", padding: 3 }}>
            <button style={{ flex: 1, padding: "7px 0", fontSize: 12 }}>Viewer</button>
            <button aria-selected="true" style={{ flex: 1, padding: "7px 0", fontSize: 12 }}>Editor</button>
            <button style={{ flex: 1, padding: "7px 0", fontSize: 12 }}>Admin</button>
          </div>
        </div>
      </div>
    </Modal>
  );
}



/* ── Talk to sales ──────────────────────────────────────── */
function SalesDialog({ open, onClose, planSeed }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [size, setSize] = useState("11-50");
  const [plan, setPlan] = useState(planSeed || "Enterprise");
  const [msg, setMsg] = useState("");
  const [sent, setSent] = useState(false);
  const toast = useToast();

  useEffect(() => { if (planSeed) setPlan(planSeed); }, [planSeed]);
  useEffect(() => { if (!open) { setSent(false); } }, [open]);

  const send = () => {
    if (!email.trim() || !name.trim()) {
      toast("Name and email required", { kind: "warning", icon: "alert" });
      return;
    }
    setSent(true);
    toast("Thanks — we'll be in touch within 1 business day", { kind: "success", icon: "send" });
    setTimeout(() => onClose(), 2400);
  };

  return (
    <Modal open={open} onClose={onClose} width={620} icon="message"
           title="Talk to sales"
           subtitle="Volume pricing, security review, on-prem deployment — let's chat"
           footer={!sent && (
             <>
               <button className="btn" onClick={onClose}>Cancel</button>
               <button className="btn btn-primary" onClick={send}>
                 <Icon name="send" size={12}/> Request a call
               </button>
             </>
           )}>
      {sent ? (
        <div style={{ textAlign: "center", padding: "30px 10px", animation: "growIn 0.4s var(--ease-spring) both" }}>
          <div style={{
            width: 64, height: 64, borderRadius: "50%", margin: "0 auto 16px",
            background: "var(--success-soft)", color: "var(--success)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
          }}><Icon name="check" size={28} strokeWidth={2.5}/></div>
          <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 6 }}>Request received</h3>
          <p className="text-muted" style={{ fontSize: 13 }}>
            A solutions engineer will reach out to <span className="mono" style={{ color: "var(--fg)" }}>{email}</span> shortly.
          </p>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Name</div>
            <input className="input" value={name} onChange={e => setName(e.target.value)}
                   placeholder="Maya Chen" style={{ width: "100%", height: 38 }}/>
          </div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Work email</div>
            <input className="input" value={email} onChange={e => setEmail(e.target.value)}
                   placeholder="maya@company.com" style={{ width: "100%", height: 38 }}/>
          </div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Company</div>
            <input className="input" value={company} onChange={e => setCompany(e.target.value)}
                   placeholder="Acme Insurance" style={{ width: "100%", height: 38 }}/>
          </div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Team size</div>
            <div className="toggle-pill" style={{ width: "100%", padding: 3 }}>
              {["1-10", "11-50", "51-200", "200+"].map(s => (
                <button key={s} aria-selected={size === s} onClick={() => setSize(s)}
                        style={{ flex: 1, padding: "6px 0", fontSize: 11.5 }}>{s}</button>
              ))}
            </div>
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Interested plan</div>
            <div className="toggle-pill" style={{ width: "100%", padding: 3 }}>
              {["Pro", "Team", "Enterprise"].map(p => (
                <button key={p} aria-selected={plan === p} onClick={() => setPlan(p)}
                        style={{ flex: 1, padding: "7px 0", fontSize: 12 }}>{p}</button>
              ))}
            </div>
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <div className="eyebrow" style={{ marginBottom: 6 }}>What are you trying to migrate?</div>
            <textarea className="input" value={msg} onChange={e => setMsg(e.target.value)} rows={3}
                      placeholder="~600 SAS files, mostly DATA steps and PROC SQL, due Q3..."
                      style={{ width: "100%", padding: 10, resize: "vertical", lineHeight: 1.5 }}/>
          </div>
        </div>
      )}
    </Modal>
  );
}
export { NewProjectDialog, ShortcutsDialog, WhatsNewDialog, ShareDialog, InviteDialog, SalesDialog };
