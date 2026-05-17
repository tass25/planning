import React, { useState, useEffect, useRef, useMemo, useCallback, createContext, useContext } from "react";
import type { ReactNode, CSSProperties } from "react";

/* ──────────────────────────────────────────────────────────
   Shared components for Codara prototype
   Icons (Lucide-style minimal SVGs), Charts, Cards, Badges, etc.
   ────────────────────────────────────────────────────────── */

/* ============================================================
   Icons — inline minimal SVGs (Lucide style)
   ============================================================ */
const Icon = ({ name, size = 16, strokeWidth = 1.7, className = "", style }) => {
  const paths = ICONS[name] || ICONS["square"];
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth={strokeWidth}
      strokeLinecap="round" strokeLinejoin="round"
      className={className} style={style}
      aria-hidden="true"
    >{paths}</svg>
  );
};

const ICONS = {
  square:        <rect x="3" y="3" width="18" height="18" rx="2" />,
  dashboard:     <g><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></g>,
  fileCode:      <g><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="m10 13-2 2 2 2"/><path d="m14 17 2-2-2-2"/></g>,
  folder:        <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>,
  history:       <g><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/></g>,
  book:          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/>,
  bar:           <g><path d="M3 21h18"/><rect x="6" y="11" width="3" height="8"/><rect x="11" y="6" width="3" height="13"/><rect x="16" y="14" width="3" height="5"/></g>,
  shield:        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>,
  settings:      <g><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></g>,
  upload:        <g><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></g>,
  rocket:        <g><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></g>,
  sparkles:      <g><path d="M9.94 14.34 8 21l-1.94-6.66L0 12l6.06-2.34L8 3l1.94 6.66L16 12z"/><path d="m19 4 1 2 2 1-2 1-1 2-1-2-2-1 2-1z"/></g>,
  check:         <path d="m20 6-11 11-5-5"/>,
  checkCircle:   <g><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></g>,
  x:             <g><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></g>,
  xCircle:       <g><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></g>,
  alert:         <g><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></g>,
  clock:         <g><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></g>,
  loader:        <line x1="12" y1="2" x2="12" y2="6"/>,
  search:        <g><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></g>,
  user:          <g><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></g>,
  users:         <g><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></g>,
  bell:          <g><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></g>,
  arrowRight:    <g><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></g>,
  arrowUpRight:  <g><line x1="7" y1="17" x2="17" y2="7"/><polyline points="7 7 17 7 17 17"/></g>,
  arrowDown:     <polyline points="6 9 12 15 18 9"/>,
  plus:          <g><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></g>,
  download:      <g><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></g>,
  play:          <polygon points="5 3 19 12 5 21 5 3"/>,
  pause:         <g><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></g>,
  logout:        <g><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></g>,
  chevronLeft:   <polyline points="15 18 9 12 15 6"/>,
  chevronRight:  <polyline points="9 18 15 12 9 6"/>,
  chevronUp:     <polyline points="18 15 12 9 6 15"/>,
  chevronDown:   <polyline points="6 9 12 15 18 9"/>,
  more:          <g><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></g>,
  dollar:        <g><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></g>,
  activity:      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>,
  zap:           <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>,
  cpu:           <g><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="15" x2="23" y2="15"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="15" x2="4" y2="15"/></g>,
  filter:        <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>,
  inbox:         <g><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></g>,
  layers:        <g><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></g>,
  database:      <g><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/></g>,
  git:           <g><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 0 1 2 2v7"/><line x1="6" y1="9" x2="6" y2="21"/></g>,
  mail:          <g><rect x="2" y="4" width="20" height="16" rx="2"/><polyline points="22 6 12 13 2 6"/></g>,
  key:           <g><circle cx="8" cy="15" r="4"/><path d="m10.85 12.15 7.4-7.4M18 8l3 3M16 10l3 3"/></g>,
  command:       <path d="M18 3a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3 3 3 0 0 0 3-3 3 3 0 0 0-3-3H6a3 3 0 0 0-3 3 3 3 0 0 0 3 3 3 3 0 0 0 3-3V6a3 3 0 0 0-3-3 3 3 0 0 0-3 3 3 3 0 0 0 3 3h12a3 3 0 0 0 3-3 3 3 0 0 0-3-3z"/>,
  flame:         <g><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></g>,
  package:       <g><line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></g>,
  branch:        <g><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></g>,
  refresh:       <g><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></g>,
  tag:           <g><path d="M20.59 13.41 13.42 20.58a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></g>,
  link:          <g><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></g>,
  trending:      <g><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></g>,
  globe:         <g><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></g>,
  copy:          <g><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></g>,
  externalLink:  <g><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></g>,
  star:          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>,
  pin:           <g><line x1="12" y1="17" x2="12" y2="22"/><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24z"/></g>,
  trash:         <g><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></g>,
  edit:          <g><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4z"/></g>,
  eye:           <g><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></g>,
  sun:           <g><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></g>,
  moon:          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>,
  terminal:      <g><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></g>,
  message:       <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>,
  share:         <g><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></g>,
  bookmark:      <path d="m19 21-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>,
  send:          <g><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></g>,
  panelLeft:     <g><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></g>,
};

/* ============================================================
   StatCard — number with optional trend + sparkline
   ============================================================ */
const StatCard = ({ label, value, delta, deltaType = "neutral", icon, sparkData, tone = "default", sub, onClick }) => {
  const isPos = deltaType === "up";
  const isNeg = deltaType === "down";
  return (
    <div className="panel" style={{
      padding: 16, position: "relative", overflow: "hidden", cursor: onClick ? "default" : undefined,
    }} onClick={onClick}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <span className="eyebrow">{label}</span>
        {icon ? (
          <div style={{
            width: 26, height: 26, borderRadius: "var(--radius-sm)",
            background: tone === "accent" ? "var(--accent-soft)" : "var(--surface-2)",
            color: tone === "accent" ? "var(--accent)" : "var(--fg-muted)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
          }}><Icon name={icon} size={14} /></div>
        ) : null}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10 }}>
        <AnimatedNumber value={value} className="" style={{
          fontFamily: "var(--font-display)", fontSize: 26, fontWeight: 600, letterSpacing: "-0.02em", lineHeight: 1.1,
        }} />
        {delta != null && (
          <span style={{
            fontSize: "var(--tw-tiny)", fontWeight: 500,
            color: isPos ? "var(--success)" : isNeg ? "var(--danger)" : "var(--fg-muted)",
            display: "inline-flex", alignItems: "center", gap: 2,
          }}>
            <Icon name={isPos ? "trending" : isNeg ? "trending" : "arrowRight"} size={11}
                  style={isNeg ? { transform: "scaleY(-1)" } : {}}/>
            {delta}
          </span>
        )}
      </div>
      {sub && <div className="text-subtle" style={{ fontSize: "var(--tw-tiny)", marginTop: 4 }}>{sub}</div>}
      {sparkData && (
        <div className="spark-bar" style={{ marginTop: 14 }}>
          {sparkData.map((v, i) => {
            const max = Math.max(...sparkData);
            const h = max > 0 ? (v / max) * 100 : 0;
            return <i key={i} style={{ height: `${Math.max(8, h)}%`, animationDelay: `${i * 28}ms`, opacity: 0.45 + (h/100)*0.55 }}/>;
          })}
        </div>
      )}
    </div>
  );
};

/* ============================================================
   AnimatedNumber — count up
   ============================================================ */
function AnimatedNumber({ value, style, className, format }) {
  const [display, setDisplay] = useState(value);
  const prev = useRef(typeof value === "number" ? value : 0);
  useEffect(() => {
    if (typeof value !== "number") { setDisplay(value); return; }
    const start = performance.now();
    const dur = 520;
    const from = prev.current;
    const to = value;
    let raf;
    const step = (now) => {
      const t = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - t, 3);
      const v = from + (to - from) * eased;
      setDisplay(Number.isInteger(to) ? Math.round(v) : +v.toFixed(1));
      if (t < 1) raf = requestAnimationFrame(step);
      else prev.current = to;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <span className={className} style={style}>{format ? format(display) : display}</span>;
}

/* ============================================================
   StatusBadge
   ============================================================ */
const StatusBadge = ({ status }) => {
  const map = {
    completed: { cls: "badge-success", label: "Completed", dot: "var(--success)" },
    running:   { cls: "badge-accent",  label: "Running",   dot: "var(--accent)" },
    queued:    { cls: "badge-info",    label: "Queued",    dot: "var(--info)" },
    partial:   { cls: "badge-warning", label: "Partial",   dot: "var(--warning)" },
    failed:    { cls: "badge-danger",  label: "Failed",    dot: "var(--danger)" },
    online:    { cls: "badge-success", label: "Online",    dot: "var(--success)" },
    degraded:  { cls: "badge-warning", label: "Degraded",  dot: "var(--warning)" },
    offline:   { cls: "badge-danger",  label: "Offline",   dot: "var(--danger)" },
    active:    { cls: "badge-success", label: "Active",    dot: "var(--success)" },
    invited:   { cls: "badge-info",    label: "Invited",   dot: "var(--info)" },
    suspended: { cls: "badge-danger",  label: "Suspended", dot: "var(--danger)" },
    shipped:   { cls: "badge-success", label: "Shipped",   dot: "var(--success)" },
    experiment:{ cls: "badge-warning", label: "Experiment", dot: "var(--warning)" },
    stable:    { cls: "badge-success", label: "Stable",    dot: "var(--success)" },
    review:    { cls: "badge-warning", label: "In Review", dot: "var(--warning)" },
    ok:        { cls: "badge-success", label: "OK",        dot: "var(--success)" },
  };
  const m = map[status] || { cls: "", label: status, dot: "var(--fg-muted)" };
  const isRunning = status === "running";
  return (
    <span className={`badge ${m.cls}`}>
      <span style={{
        width: 5, height: 5, borderRadius: 999, background: m.dot,
        animation: isRunning ? "pulseSoft 1.4s ease-in-out infinite" : "none",
      }}/>
      {m.label}
    </span>
  );
};

/* ============================================================
   Avatar
   ============================================================ */
const Avatar = ({ name, size = 28, color }) => {
  const initials = name.split(" ").map(p => p[0]).slice(0, 2).join("").toUpperCase();
  const hash = name.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  const tones = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];
  const bg = color || tones[hash % tones.length];
  return (
    <span className="avatar" style={{
      width: size, height: size, fontSize: size * 0.4,
      background: `color-mix(in srgb, ${bg} 18%, var(--surface-2))`,
      color: bg, borderColor: `color-mix(in srgb, ${bg} 20%, var(--border))`,
    }}>{initials}</span>
  );
};

/* ============================================================
   AreaChart (svg, animated)
   ============================================================ */
function AreaChart({ data, keys, height = 200, showXAxis = true, showYAxis = true, showGrid = true, gradient = true }) {
  const ref = useRef(null);
  const [w, setW] = useState(600);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) setW(e.contentRect.width);
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  const pad = { l: showYAxis ? 36 : 8, r: 10, t: 14, b: showXAxis ? 22 : 6 };
  const innerW = Math.max(1, w - pad.l - pad.r);
  const innerH = Math.max(1, height - pad.t - pad.b);
  const allVals = data.flatMap(d => keys.map(k => d[k.key])).filter(v => typeof v === "number");
  const maxV = Math.max(1, ...allVals) * 1.15;
  const minV = 0;
  const x = i => pad.l + (data.length <= 1 ? innerW/2 : (i / (data.length - 1)) * innerW);
  const y = v => pad.t + innerH - ((v - minV) / (maxV - minV)) * innerH;
  const yTicks = 4;
  const ticks = Array.from({ length: yTicks + 1 }, (_, i) => Math.round((maxV / yTicks) * i));

  const pathFor = (k) => {
    const pts = data.map((d, i) => [x(i), y(d[k] || 0)]);
    let p = `M ${pts[0][0]} ${pts[0][1]}`;
    for (let i = 1; i < pts.length; i++) {
      const [px, py] = pts[i - 1]; const [cx, cy] = pts[i];
      const mx = (px + cx) / 2;
      p += ` C ${mx} ${py} ${mx} ${cy} ${cx} ${cy}`;
    }
    return p;
  };
  const areaFor = (k) => {
    const top = pathFor(k);
    return `${top} L ${x(data.length - 1)} ${pad.t + innerH} L ${x(0)} ${pad.t + innerH} Z`;
  };

  return (
    <div ref={ref} style={{ width: "100%", height }}>
      <svg width={w} height={height} style={{ display: "block", overflow: "visible" }}>
        {gradient && (
          <defs>
            {keys.map((k, i) => (
              <linearGradient key={i} id={`grad-${k.key}-${i}-${Math.round(w)}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={k.color} stopOpacity="0.32"/>
                <stop offset="100%" stopColor={k.color} stopOpacity="0"/>
              </linearGradient>
            ))}
          </defs>
        )}

        {showGrid && ticks.map((t, i) => (
          <line key={i} x1={pad.l} x2={w - pad.r} y1={y(t)} y2={y(t)}
                stroke="var(--grid-line)" strokeWidth="1" strokeDasharray="2 4" opacity="0.5"/>
        ))}

        {showYAxis && ticks.map((t, i) => (
          <text key={i} x={pad.l - 8} y={y(t) + 3} textAnchor="end"
                fontSize="10" fill="var(--fg-subtle)" fontFamily="var(--font-mono)">{t}</text>
        ))}

        {showXAxis && data.map((d, i) => {
          const step = Math.max(1, Math.floor(data.length / 6));
          if (i % step !== 0 && i !== data.length - 1) return null;
          const label = d.label || (d.date ? d.date.slice(5) : "");
          return (
            <text key={i} x={x(i)} y={height - pad.b + 14} textAnchor="middle"
                  fontSize="10" fill="var(--fg-subtle)" fontFamily="var(--font-mono)">{label}</text>
          );
        })}

        {keys.map((k, i) => (
          <g key={k.key}>
            {gradient && (
              <path d={areaFor(k.key)} fill={`url(#grad-${k.key}-${i}-${Math.round(w)})`}
                    style={{ animation: "fadeIn 0.7s ease-out both", animationDelay: `${i * 80}ms` }}/>
            )}
            <path d={pathFor(k.key)} fill="none" stroke={k.color} strokeWidth="2"
                  strokeLinecap="round" strokeLinejoin="round"
                  style={{
                    strokeDasharray: 2000, strokeDashoffset: 2000,
                    animation: "drawLine 1.1s var(--ease-out) forwards",
                    animationDelay: `${i * 120}ms`,
                    "--dash-len": 2000,
                  }}/>
          </g>
        ))}
      </svg>
    </div>
  );
}

/* ============================================================
   BarChart (animated)
   ============================================================ */
function BarChart({ data, valueKey = "value", labelKey = "label", height = 180, color = "var(--chart-2)" }) {
  const ref = useRef(null);
  const [w, setW] = useState(400);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) setW(e.contentRect.width);
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  const pad = { l: 32, r: 10, t: 10, b: 22 };
  const innerW = Math.max(1, w - pad.l - pad.r);
  const innerH = Math.max(1, height - pad.t - pad.b);
  const max = Math.max(1, ...data.map(d => d[valueKey])) * 1.15;
  const barW = innerW / data.length * 0.72;
  const gap = innerW / data.length * 0.28;
  return (
    <div ref={ref} style={{ width: "100%", height }}>
      <svg width={w} height={height}>
        {[0, 0.25, 0.5, 0.75, 1].map((p, i) => (
          <line key={i} x1={pad.l} x2={w - pad.r}
                y1={pad.t + innerH - p * innerH} y2={pad.t + innerH - p * innerH}
                stroke="var(--grid-line)" strokeDasharray="2 4" opacity="0.5"/>
        ))}
        {[0, 0.25, 0.5, 0.75, 1].map((p, i) => (
          <text key={i} x={pad.l - 6} y={pad.t + innerH - p * innerH + 3} textAnchor="end"
                fontSize="10" fill="var(--fg-subtle)" fontFamily="var(--font-mono)">{Math.round(max * p)}</text>
        ))}
        {data.map((d, i) => {
          const h = (d[valueKey] / max) * innerH;
          const x = pad.l + (innerW / data.length) * i + gap / 2;
          const y = pad.t + innerH - h;
          return (
            <g key={i}>
              <rect x={x} y={y} width={barW} height={h} rx="3" fill={color}
                    style={{
                      transformOrigin: `${x + barW/2}px ${pad.t + innerH}px`,
                      animation: "growBar 0.55s var(--ease-spring) both",
                      animationDelay: `${i * 30}ms`,
                    }}/>
              {(i % Math.max(1, Math.floor(data.length / 8)) === 0 || i === data.length - 1) && (
                <text x={x + barW/2} y={height - pad.b + 14} textAnchor="middle"
                      fontSize="10" fill="var(--fg-subtle)" fontFamily="var(--font-mono)">
                  {d[labelKey] || (d.date ? d.date.slice(5) : "")}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/* ============================================================
   DonutChart (animated)
   ============================================================ */
function DonutChart({ data, size = 160, thickness = 16, center }) {
  const total = data.reduce((s, d) => s + d.value, 0);
  const r = size/2 - thickness/2;
  const c = 2 * Math.PI * r;
  let cum = 0;
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--surface-2)" strokeWidth={thickness}/>
        {data.map((d, i) => {
          const frac = d.value / total;
          const len = frac * c;
          const off = cum * c;
          cum += frac;
          return (
            <circle key={i} cx={size/2} cy={size/2} r={r} fill="none"
              stroke={d.color} strokeWidth={thickness}
              strokeDasharray={`${len} ${c - len}`}
              strokeDashoffset={-off}
              style={{
                opacity: 0,
                animation: "fadeIn 0.5s ease-out forwards",
                animationDelay: `${i * 120 + 80}ms`,
              }}/>
          );
        })}
      </svg>
      {center && (
        <div style={{
          position: "absolute", inset: 0, display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center", textAlign: "center", pointerEvents: "none"
        }}>
          {center}
        </div>
      )}
    </div>
  );
}

/* ============================================================
   Sparkline (mini line)
   ============================================================ */
function Sparkline({ data, w = 80, h = 24, color = "var(--accent)" }) {
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const pad = 2;
  const x = i => pad + (i / (data.length - 1)) * (w - 2 * pad);
  const y = v => pad + (h - 2 * pad) - ((v - min) / (max - min || 1)) * (h - 2 * pad);
  const pts = data.map((v, i) => [x(i), y(v)]);
  let path = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [px, py] = pts[i - 1]; const [cx, cy] = pts[i];
    const mx = (px + cx) / 2;
    path += ` C ${mx} ${py} ${mx} ${cy} ${cx} ${cy}`;
  }
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      <path d={path} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round"/>
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2" fill={color}/>
    </svg>
  );
}

/* ============================================================
   Progress (animated)
   ============================================================ */
const ProgressBar = ({ value, max = 100, color = "var(--accent)", height = 6, label, animated = true }) => (
  <div>
    {label && <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: "var(--tw-tiny)" }}>
      <span className="text-muted">{label}</span>
      <span className="mono" style={{ color: "var(--fg)" }}>{value}/{max}</span>
    </div>}
    <div style={{ height, background: "var(--surface-2)", borderRadius: 999, overflow: "hidden" }}>
      <div style={{
        height: "100%", width: `${(value/max)*100}%`,
        background: color, borderRadius: 999,
        transition: animated ? "width 1.2s cubic-bezier(0.16, 1, 0.3, 1)" : "none",
      }}/>
    </div>
  </div>
);

/* ============================================================
   Sheet / Drawer (right slide)
   ============================================================ */
const Sheet = ({ open, onClose, title, children, width = 480 }) => {
  return (
    <>
      <div onClick={onClose} style={{
        position: "fixed", inset: 0, background: "rgba(8,8,12,0.36)", zIndex: 60,
        opacity: open ? 1 : 0, pointerEvents: open ? "auto" : "none",
        transition: "opacity 0.28s var(--ease-out)",
      }}/>
      <aside style={{
        position: "fixed", top: 0, right: 0, bottom: 0, width, maxWidth: "92vw",
        background: "var(--surface)", borderLeft: "1px solid var(--border)",
        boxShadow: "var(--shadow-pop)", zIndex: 61,
        transform: open ? "translateX(0)" : "translateX(100%)",
        transition: "transform 0.36s var(--ease-out)",
        display: "flex", flexDirection: "column",
      }}>
        <header style={{
          padding: "14px 18px", borderBottom: "1px solid var(--border)",
          display: "flex", alignItems: "center", justifyContent: "space-between"
        }}>
          <h3 style={{ fontSize: 14, fontWeight: 600 }}>{title}</h3>
          <button className="btn btn-icon btn-ghost" onClick={onClose} aria-label="Close">
            <Icon name="x" size={14}/>
          </button>
        </header>
        <div style={{ flex: 1, overflowY: "auto", padding: 18 }}>{children}</div>
      </aside>
    </>
  );
};

/* ============================================================
   Command palette (cmd-k)
   ============================================================ */
const CommandPalette = ({ open, onClose, onNavigate }) => {
  const [q, setQ] = useState("");
  const items = useMemo(() => [
    { id: "/dashboard", label: "Dashboard", icon: "dashboard", group: "Pages" },
    { id: "/conversions", label: "New conversion", icon: "upload", group: "Pages" },
    { id: "/workspace", label: "Workspace", icon: "folder", group: "Pages" },
    { id: "/history", label: "History", icon: "history", group: "Pages" },
    { id: "/knowledge-base", label: "Knowledge Base", icon: "book", group: "Pages" },
    { id: "/analytics", label: "Analytics", icon: "bar", group: "Pages" },
    { id: "/projects", label: "Projects", icon: "layers", group: "Pages" },
    { id: "/notifications", label: "Notifications", icon: "bell", group: "Pages" },
    { id: "/settings", label: "Settings", icon: "settings", group: "Pages" },
    { id: "/admin", label: "Admin overview", icon: "shield", group: "Admin" },
    { id: "/admin/users", label: "Users", icon: "users", group: "Admin" },
    { id: "/admin/audit-logs", label: "Audit logs", icon: "history", group: "Admin" },
    { id: "/admin/system-health", label: "System health", icon: "activity", group: "Admin" },
    { id: "/admin/pipeline-config", label: "Pipeline config", icon: "git", group: "Admin" },
    { id: "/admin/file-registry", label: "File registry", icon: "database", group: "Admin" },
    { id: "/admin/kb-management", label: "KB management", icon: "book", group: "Admin" },
    { id: "/admin/kb-changelog", label: "KB changelog", icon: "history", group: "Admin" },
    { id: "/admin/cost", label: "Cost dashboard", icon: "dollar", group: "Admin · New" },
    { id: "/admin/prompts", label: "Prompt templates", icon: "terminal", group: "Admin · New" },
    { id: "/admin/error-queue", label: "Error triage queue", icon: "alert", group: "Admin · New" },
  ], []);
  const filtered = items.filter(i => i.label.toLowerCase().includes(q.toLowerCase()));
  const groups = filtered.reduce((acc, it) => { (acc[it.group] = acc[it.group] || []).push(it); return acc; }, {});

  if (!open) return null;
  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, background: "rgba(8,8,12,0.45)", zIndex: 100,
      display: "flex", alignItems: "flex-start", justifyContent: "center", paddingTop: "14vh",
      animation: "fadeIn 0.18s ease-out both",
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        width: 560, maxWidth: "92vw", background: "var(--surface)",
        border: "1px solid var(--border)", borderRadius: "var(--radius-lg)",
        boxShadow: "var(--shadow-pop)", overflow: "hidden",
        animation: "growIn 0.22s var(--ease-spring) both",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 14px", borderBottom: "1px solid var(--border)" }}>
          <Icon name="search" size={14} className="text-muted"/>
          <input autoFocus value={q} onChange={e => setQ(e.target.value)}
                 placeholder="Search pages, conversions, KB patterns…"
                 style={{ flex: 1, fontSize: 14, padding: "4px 0" }}/>
          <kbd>Esc</kbd>
        </div>
        <div style={{ maxHeight: 380, overflowY: "auto", padding: 6 }}>
          {Object.entries(groups).map(([g, items]) => (
            <div key={g} style={{ padding: "6px 6px 4px" }}>
              <div className="eyebrow" style={{ padding: "4px 8px" }}>{g}</div>
              {items.map(it => (
                <button key={it.id} onClick={() => { onNavigate(it.id); onClose(); }}
                  className="cmd-item" style={{
                    display: "flex", alignItems: "center", gap: 10, width: "100%",
                    padding: "8px 10px", borderRadius: "var(--radius)", color: "var(--fg)",
                  }}>
                  <Icon name={it.icon} size={14} className="text-muted"/>
                  <span style={{ flex: 1, textAlign: "left" }}>{it.label}</span>
                  <Icon name="arrowRight" size={12} className="text-subtle"/>
                </button>
              ))}
            </div>
          ))}
          {filtered.length === 0 && (
            <div style={{ padding: 24, textAlign: "center", color: "var(--fg-subtle)", fontSize: 13 }}>
              No matches for “{q}”
            </div>
          )}
        </div>
      </div>
      <style>{`.cmd-item:hover { background: var(--surface-2); }`}</style>
    </div>
  );
};

/* ============================================================
   Code diff line renderer
   ============================================================ */
function CodeBlock({ code, lang = "py", highlightLines = [], deletedLines = [], addedLines = [] }) {
  const lines = code.split("\n");

  // tiny syntax highlighter for SAS and Python
  const highlight = (line, lang) => {
    if (lang === "sas") {
      const kws = /\b(data|set|run|proc|by|class|var|where|output|out|input|merge|format|if|then|else|do|end|retain|sum|mean|first|last|drop|keep|select|case|create|table|from|left|join|inner|on|quit|macro|mend|format|libname)\b/gi;
      const strs = /'[^']*'|"[^"]*"/g;
      const nums = /\b\d+(\.\d+)?\b/g;
      const coms = /(\*[^;]*;|\/\*[\s\S]*?\*\/)/g;
      const escaped = line.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      return escaped
        .replace(coms, '<span class="com">$1</span>')
        .replace(strs, m => `<span class="str">${m}</span>`)
        .replace(kws, '<span class="kw">$&</span>')
        .replace(nums, '<span class="num">$&</span>');
    }
    // python
    const kws = /\b(def|return|if|elif|else|for|in|while|import|from|as|with|class|try|except|finally|raise|yield|pass|continue|break|lambda|None|True|False|and|or|not|is)\b/g;
    const fns = /\b(pd|np|groupby|agg|merge|pivot|reset_index|crosstab|cumsum|copy|read_csv|to_csv|sum|mean|apply|map|filter)\b/g;
    const strs = /'[^']*'|"[^"]*"/g;
    const nums = /\b\d+(\.\d+)?\b/g;
    const coms = /(#[^\n]*)/g;
    const escaped = line.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return escaped
      .replace(coms, '<span class="com">$1</span>')
      .replace(strs, m => `<span class="str">${m}</span>`)
      .replace(kws, '<span class="kw">$&</span>')
      .replace(fns, '<span class="fn">$&</span>')
      .replace(nums, '<span class="num">$&</span>');
  };

  return (
    <div className="code" style={{ padding: 0, overflow: "auto", maxHeight: "100%" }}>
      {lines.map((l, i) => {
        const ln = i + 1;
        const isAdded = addedLines.includes(ln);
        const isDeleted = deletedLines.includes(ln);
        const isHl = highlightLines.includes(ln);
        return (
          <div key={i} style={{
            padding: "1px 14px",
            background: isAdded ? "color-mix(in srgb, var(--success) 10%, transparent)"
                        : isDeleted ? "color-mix(in srgb, var(--danger) 10%, transparent)"
                        : isHl ? "color-mix(in srgb, var(--accent) 10%, transparent)" : "transparent",
            borderLeft: isAdded ? "2px solid var(--success)"
                       : isDeleted ? "2px solid var(--danger)"
                       : isHl ? "2px solid var(--accent)" : "2px solid transparent",
            display: "flex", gap: 12, alignItems: "baseline",
            fontFamily: "var(--font-mono)", fontSize: 12.5, lineHeight: 1.65,
          }}>
            <span className="lineno mono" style={{ width: 28, textAlign: "right", flexShrink: 0, color: "var(--fg-subtle)" }}>{ln}</span>
            <span style={{ flex: 1, whiteSpace: "pre" }} dangerouslySetInnerHTML={{ __html: highlight(l, lang) || "&nbsp;" }}/>
          </div>
        );
      })}
    </div>
  );
}

/* ============================================================
   Heatmap (calendar)
   ============================================================ */
function CalendarHeatmap({ data, cols = 30, rows = 7, color = "var(--accent)" }) {
  const max = Math.max(1, ...data.map(d => d.value));
  // pad start to fill 30*7 = 210
  const totalCells = cols * rows;
  const filled = data.slice(-totalCells);
  const start = totalCells - filled.length;
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 3 }}>
      {Array.from({ length: totalCells }, (_, i) => {
        const idx = i - start;
        const d = filled[idx];
        const v = d ? d.value : 0;
        const op = d ? 0.15 + (v / max) * 0.85 : 0.05;
        return (
          <div key={i} title={d ? `${d.label}: ${v}` : ""} style={{
            aspectRatio: "1", borderRadius: 2,
            background: d ? color : "var(--surface-2)",
            opacity: op,
            animation: "fadeIn 0.4s ease-out both",
            animationDelay: `${i * 4}ms`,
          }}/>
        );
      })}
    </div>
  );
}

/* ============================================================
   Toggle (theme switch)
   ============================================================ */
const ThemeToggle = ({ value, onChange }) => (
  <button className="btn btn-icon btn-ghost" onClick={() => onChange(value === "dark" ? "light" : "dark")}
          title="Toggle theme" aria-label="Toggle theme">
    <Icon name={value === "dark" ? "sun" : "moon"} size={14}/>
  </button>
);

/* ============================================================
   Expose to window
   ============================================================ */
export {
  Icon, ICONS, StatCard, StatusBadge, Avatar,
  AreaChart, BarChart, DonutChart, Sparkline,
  ProgressBar, Sheet, CommandPalette, CodeBlock,
  CalendarHeatmap, AnimatedNumber, ThemeToggle,
};
