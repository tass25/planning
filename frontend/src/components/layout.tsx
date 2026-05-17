import React, { useState, useEffect, useRef, useMemo, useCallback, createContext, useContext } from "react";
import type { ReactNode, CSSProperties } from "react";
import { Icon, Avatar, ThemeToggle } from "./ui";
import { Popover } from "./ambient";

/* ──────────────────────────────────────────────────────────
   App shell: Sidebar + TopBar
   ────────────────────────────────────────────────────────── */

function CodaraLogo({ collapsed = false, size = 22 }) {
  const s = size + 6;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <span style={{
        width: s, height: s, borderRadius: 8,
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        position: "relative", overflow: "hidden", flexShrink: 0,
      }}>
        <svg width={s} height={s} viewBox="0 0 32 32" aria-label="Codara logo">
          <defs>
            <linearGradient id="codara-mark-grad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%"  stopColor="var(--accent)"/>
              <stop offset="100%" stopColor="var(--secondary)"/>
            </linearGradient>
            <linearGradient id="codara-mark-shine" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"  stopColor="white" stopOpacity="0.35"/>
              <stop offset="100%" stopColor="white" stopOpacity="0"/>
            </linearGradient>
          </defs>
          {/* Hex container with rounded corners */}
          <path d="M16 1 L28.5 8 L28.5 24 L16 31 L3.5 24 L3.5 8 Z"
                fill="url(#codara-mark-grad)"
                stroke="color-mix(in srgb, var(--accent) 40%, transparent)" strokeWidth="0.5"/>
          {/* Top highlight */}
          <path d="M16 1 L28.5 8 L28.5 16 L16 9 L3.5 16 L3.5 8 Z"
                fill="url(#codara-mark-shine)"/>
          {/* C / chevron mark (translates SAS arrow into Python paren) */}
          <g style={{
            transformOrigin: "16px 16px",
            animation: "codaraSpin 14s linear infinite",
          }}>
            <path d="M21 11 L12 16 L21 21"
                  fill="none" stroke="white"
                  strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"
                  strokeOpacity="0.96"/>
          </g>
          {/* Orbiting dot */}
          <circle cx="22" cy="22" r="1.4" fill="white" fillOpacity="0.9">
            <animateTransform attributeName="transform" type="rotate"
                              from="0 16 16" to="360 16 16" dur="9s" repeatCount="indefinite"/>
          </circle>
        </svg>
      </span>
      {!collapsed && (
        <span style={{
          fontFamily: "var(--font-display)", fontWeight: 600,
          fontSize: size * 0.78, letterSpacing: "-0.025em",
          lineHeight: 1, color: "var(--fg)",
        }}>Codara</span>
      )}
      <style>{`
        @keyframes codaraSpin {
          0%, 88%, 100% { transform: rotate(0deg); }
          92% { transform: rotate(-6deg); }
          96% { transform: rotate(6deg); }
        }
      `}</style>
    </div>
  );
}

/* ─── Sidebar ─── */
function AppSidebar({ collapsed, setCollapsed, path, navigate, role, onCommand }) {
  const userNav = [
    { label: "Dashboard", path: "/dashboard", icon: "dashboard" },
    { label: "New Conversion", path: "/conversions", icon: "upload" },
    { label: "Workspace", path: "/workspace", icon: "folder" },
    { label: "Projects", path: "/projects", icon: "layers", isNew: true },
    { label: "History", path: "/history", icon: "history" },
    { label: "Knowledge Base", path: "/knowledge-base", icon: "book" },
    { label: "Analytics", path: "/analytics", icon: "bar" },
  ];
  const adminNav = [
    { label: "Admin Overview", path: "/admin", icon: "shield" },
    { label: "Cost Dashboard", path: "/admin/cost", icon: "dollar", isNew: true },
    { label: "Error Triage", path: "/admin/error-queue", icon: "alert", isNew: true, count: 4 },
    { label: "Prompt Templates", path: "/admin/prompts", icon: "terminal", isNew: true },
    { label: "Users", path: "/admin/users", icon: "users" },
    { label: "Audit Logs", path: "/admin/audit-logs", icon: "history" },
    { label: "System Health", path: "/admin/system-health", icon: "activity" },
    { label: "Pipeline Config", path: "/admin/pipeline-config", icon: "git" },
    { label: "File Registry", path: "/admin/file-registry", icon: "database" },
    { label: "KB Management", path: "/admin/kb-management", icon: "book" },
    { label: "KB Changelog", path: "/admin/kb-changelog", icon: "branch" },
  ];

  const renderItem = (item) => {
    const active = path === item.path || (item.path !== "/dashboard" && path.startsWith(item.path + "/"));
    return (
      <button key={item.path} onClick={() => navigate(item.path)}
              className="nav-item" data-active={active}>
        <Icon name={item.icon} size={15}/>
        {!collapsed && (
          <>
            <span style={{ flex: 1, textAlign: "left" }}>{item.label}</span>
            {item.isNew && <span className="badge badge-accent" style={{ fontSize: 9, padding: "1px 5px" }}>NEW</span>}
            {item.count != null && (
              <span className="mono" style={{
                fontSize: 10, padding: "1px 5px", borderRadius: 4,
                background: "var(--danger-soft)", color: "var(--danger)",
              }}>{item.count}</span>
            )}
          </>
        )}
        {active && <span style={{
          position: "absolute", left: 0, top: "20%", bottom: "20%", width: 2,
          background: "var(--accent)", borderRadius: "0 2px 2px 0",
        }}/>}
      </button>
    );
  };

  return (
    <aside style={{
      gridColumn: 1, height: "100vh", display: "flex", flexDirection: "column",
      background: "var(--sidebar-bg)", borderRight: "1px solid var(--border)",
      overflow: "hidden",
    }}>
      <div style={{
        height: 60, display: "flex", alignItems: "center", padding: collapsed ? "0" : "0 18px",
        justifyContent: collapsed ? "center" : "flex-start",
        borderBottom: "1px solid var(--border)",
      }}>
        <CodaraLogo collapsed={collapsed}/>
      </div>

      <nav style={{ flex: 1, overflowY: "auto", overflowX: "hidden", padding: "10px 8px" }}>
        {/* Command palette trigger */}
        <button onClick={onCommand} className="nav-item" style={{
          width: "100%", marginBottom: 8, justifyContent: collapsed ? "center" : "space-between",
          background: "var(--surface)", border: "1px solid var(--border)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Icon name="search" size={14} className="text-muted"/>
            {!collapsed && <span className="text-muted" style={{ fontSize: 12.5 }}>Search…</span>}
          </div>
          {!collapsed && <kbd>⌘K</kbd>}
        </button>

        {!collapsed && <div className="eyebrow" style={{ padding: "8px 10px 4px" }}>Platform</div>}
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {userNav.map(renderItem)}
        </div>

        {role === "admin" && (
          <>
            {!collapsed && <div className="eyebrow" style={{ padding: "16px 10px 4px" }}>Admin</div>}
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {adminNav.map(renderItem)}
            </div>
          </>
        )}

        {!collapsed && <div className="eyebrow" style={{ padding: "16px 10px 4px" }}>System</div>}
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {renderItem({ label: "Settings", path: "/settings", icon: "settings" })}
        </div>
      </nav>

      <div style={{ borderTop: "1px solid var(--border)", padding: 8 }}>
        <button onClick={() => setCollapsed(!collapsed)} className="nav-item" style={{
          width: "100%", color: "var(--fg-muted)", justifyContent: collapsed ? "center" : "flex-start",
        }}>
          <Icon name={collapsed ? "chevronRight" : "chevronLeft"} size={14}/>
          {!collapsed && <span style={{ fontSize: 12 }}>Collapse</span>}
        </button>
      </div>

      <style>{`
        .nav-item {
          display: flex; align-items: center; gap: 10px;
          padding: ${collapsed ? "8px" : "7px 10px"};
          border-radius: var(--radius);
          font-size: 13px; color: var(--fg-muted);
          width: 100%; position: relative;
          transition: background 0.16s var(--ease-out), color 0.16s var(--ease-out);
          justify-content: ${collapsed ? "center" : "flex-start"};
        }
        .nav-item:hover { background: var(--surface-2); color: var(--fg); }
        .nav-item[data-active="true"] {
          background: var(--surface); color: var(--fg);
          font-weight: 500;
          box-shadow: var(--shadow-1);
        }
        .nav-item[data-active="true"] svg { color: var(--accent); }
      `}</style>
    </aside>
  );
}

/* ─── Top Bar ─── */
function TopBar({ user, theme, setTheme, role, setRole, onCommand, onNotifications, onTour,
                  onShortcuts, onWhatsNew, onInvite, onNavigate, unread, breadcrumb,
                  showTourCallout, dismissTourCallout }) {
  const helpAnchor = React.useRef(null);
  const userAnchor = React.useRef(null);
  const [helpOpen, setHelpOpen] = React.useState(false);
  const [userOpen, setUserOpen] = React.useState(false);

  return (
    <header style={{
      height: 60, flexShrink: 0,
      borderBottom: "1px solid var(--border)",
      background: "var(--topbar-bg)",
      backdropFilter: "blur(20px) saturate(160%)",
      WebkitBackdropFilter: "blur(20px) saturate(160%)",
      display: "flex", alignItems: "center", padding: "0 24px", gap: 16,
      position: "sticky", top: 0, zIndex: 10,
    }}>
      {/* Breadcrumb */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, minWidth: 0 }}>
        {breadcrumb.map((b, i) => (
          <React.Fragment key={i}>
            {i > 0 && <Icon name="chevronRight" size={12} className="text-subtle"/>}
            <span style={{
              fontSize: 13, color: i === breadcrumb.length - 1 ? "var(--fg)" : "var(--fg-muted)",
              fontWeight: i === breadcrumb.length - 1 ? 500 : 400,
              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            }}>{b}</span>
          </React.Fragment>
        ))}
      </div>

      {/* Right controls */}
      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <button className="btn btn-sm btn-ghost" onClick={onCommand}>
          <Icon name="search" size={13}/>
          <span>Search</span>
          <kbd>⌘K</kbd>
        </button>

        {/* Help dropdown — tour entry point */}
        <div style={{ position: "relative" }}>
          <button
            ref={helpAnchor}
            className="btn btn-icon btn-ghost"
            onClick={() => { setHelpOpen(o => !o); dismissTourCallout && dismissTourCallout(); }}
            title="Help & tour"
            style={{
              position: "relative",
              animation: showTourCallout ? "haloPulse 2s ease-out infinite" : "none",
              borderRadius: "var(--radius)",
            }}
          >
            <span style={{
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              width: 18, height: 18, borderRadius: 999,
              border: "1.5px solid currentColor", fontSize: 11, fontWeight: 700, lineHeight: 1,
            }}>?</span>
          </button>
          {showTourCallout && !helpOpen && (
            <div className="tour-callout">
              <Icon name="sparkles" size={12}/>
              <span>Take the 30-second tour</span>
              <button className="x" onClick={(e) => { e.stopPropagation(); dismissTourCallout(); }}
                      style={{ marginLeft: 6 }}>
                <Icon name="x" size={11}/>
              </button>
            </div>
          )}
          <Popover open={helpOpen} anchorRef={helpAnchor} onClose={() => setHelpOpen(false)} width={264}>
            <div className="eyebrow" style={{ padding: "6px 10px 4px" }}>Get help</div>
            <button className="menu-item" onClick={() => { setHelpOpen(false); onTour && onTour(); }}>
              <Icon name="sparkles" size={14} className="text-accent"/>
              <span style={{ flex: 1 }}>Take the product tour</span>
              <span className="badge badge-accent" style={{ fontSize: 9 }}>30s</span>
            </button>
            <button className="menu-item" onClick={() => { setHelpOpen(false); onShortcuts && onShortcuts(); }}>
              <Icon name="command" size={14} className="text-muted"/>
              <span style={{ flex: 1 }}>Keyboard shortcuts</span>
              <kbd>?</kbd>
            </button>
            <button className="menu-item" onClick={() => { setHelpOpen(false); onWhatsNew && onWhatsNew(); }}>
              <Icon name="zap" size={14} className="text-muted"/>
              <span style={{ flex: 1 }}>What's new</span>
              <span className="badge badge-accent" style={{ fontSize: 9 }}>3</span>
            </button>
            <div style={{ height: 1, background: "var(--border)", margin: "4px 6px" }}/>
            <button className="menu-item" onClick={() => setHelpOpen(false)}>
              <Icon name="book" size={14} className="text-muted"/>
              <span>Documentation</span>
              <Icon name="externalLink" size={11} className="text-subtle"/>
            </button>
            <button className="menu-item" onClick={() => setHelpOpen(false)}>
              <Icon name="message" size={14} className="text-muted"/>
              <span>Contact support</span>
            </button>
            <button className="menu-item" onClick={() => setHelpOpen(false)}>
              <Icon name="branch" size={14} className="text-muted"/>
              <span>Changelog</span>
              <Icon name="externalLink" size={11} className="text-subtle"/>
            </button>
          </Popover>
        </div>

        <button className="btn btn-icon btn-ghost" onClick={onNotifications} title="Notifications" style={{ position: "relative" }}>
          <Icon name="bell" size={14}/>
          {unread > 0 && (
            <span style={{
              position: "absolute", top: 4, right: 4,
              width: 7, height: 7, borderRadius: 999,
              background: "var(--accent)",
              boxShadow: "0 0 0 2px var(--bg-elev)",
              animation: "pulseSoft 1.6s ease-in-out infinite",
            }}/>
          )}
        </button>

        <ThemeToggle value={theme} onChange={setTheme}/>

        {/* Role switcher (so user can see admin pages too) */}
        <div className="toggle-pill" style={{ marginLeft: 6 }}>
          <button onClick={() => setRole("user")} aria-selected={role === "user"}>User</button>
          <button onClick={() => setRole("admin")} aria-selected={role === "admin"}>Admin</button>
        </div>

        <div style={{ width: 1, height: 24, background: "var(--border)", margin: "0 8px" }}/>

        {/* User avatar with dropdown */}
        <div style={{ position: "relative" }}>
          <button
            ref={userAnchor}
            onClick={() => setUserOpen(o => !o)}
            style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "4px 8px 4px 4px", borderRadius: 999,
              border: "1px solid transparent",
              transition: "background 0.16s, border-color 0.16s",
            }}
            onMouseEnter={e => { e.currentTarget.style.background = "var(--surface-2)"; e.currentTarget.style.borderColor = "var(--border)"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.borderColor = "transparent"; }}
          >
            <Avatar name={user.name} size={28}/>
            <Icon name="chevronDown" size={12} className="text-subtle"/>
          </button>
          <Popover open={userOpen} anchorRef={userAnchor} onClose={() => setUserOpen(false)} width={260}>
            <div style={{ padding: "10px 12px 8px", display: "flex", alignItems: "center", gap: 10 }}>
              <Avatar name={user.name} size={36}/>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{user.name}</div>
                <div className="text-subtle mono" style={{ fontSize: 10.5, overflow: "hidden", textOverflow: "ellipsis" }}>
                  {user.email || "you@codara.dev"}
                </div>
              </div>
            </div>
            <div style={{ height: 1, background: "var(--border)", margin: "4px 6px" }}/>
            <button className="menu-item" onClick={() => { setUserOpen(false); onNavigate && onNavigate("/settings"); }}>
              <Icon name="user" size={14} className="text-muted"/>
              <span>Profile & API keys</span>
            </button>
            <button className="menu-item" onClick={() => { setUserOpen(false); onNavigate && onNavigate("/settings"); }}>
              <Icon name="settings" size={14} className="text-muted"/>
              <span>Settings</span>
              <kbd>,</kbd>
            </button>
            <button className="menu-item" onClick={() => { setUserOpen(false); onInvite && onInvite(); }}>
              <Icon name="users" size={14} className="text-muted"/>
              <span>Invite teammates</span>
            </button>
            <button className="menu-item" onClick={() => { setUserOpen(false); onTour && onTour(); }}>
              <Icon name="sparkles" size={14} className="text-accent"/>
              <span>Take the tour</span>
            </button>
            <div style={{ height: 1, background: "var(--border)", margin: "4px 6px" }}/>
            <button className="menu-item" onClick={() => setUserOpen(false)}>
              <Icon name="logout" size={14} className="text-muted"/>
              <span style={{ color: "var(--danger)" }}>Sign out</span>
            </button>
          </Popover>
        </div>
      </div>
    </header>
  );
}
export { CodaraLogo, AppSidebar, TopBar };
