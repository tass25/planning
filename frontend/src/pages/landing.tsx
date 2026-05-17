import React, { useState, useEffect, useRef, useMemo, useCallback, createContext, useContext } from "react";
import type { ReactNode, CSSProperties } from "react";
import { Icon, AnimatedNumber, Avatar, ThemeToggle } from "../components/ui";
import { AmbientBackdrop, CursorGlow, Constellation, CodaraMascot } from "../components/ambient";
import { CodaraLogo } from "../components/layout";
import { SalesDialog } from "../components/dialogs";

/* ──────────────────────────────────────────────────────────
   Landing / pricing — the public front door
   ────────────────────────────────────────────────────────── */

/* ── Scroll-reveal on intersection ──────────────────────── */
function useReveal() {
  const ref = useRef(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) { setShown(true); io.disconnect(); }
    }, { threshold: 0.15 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return [ref, shown];
}

const Reveal = ({ delay = 0, children, as: As = "div", ...rest }) => {
  const [ref, shown] = useReveal();
  return (
    <As ref={ref} {...rest} style={{
      ...(rest.style || {}),
      opacity: shown ? 1 : 0,
      transform: shown ? "translateY(0)" : "translateY(16px)",
      transition: `opacity 0.7s var(--ease-out) ${delay}ms, transform 0.7s var(--ease-out) ${delay}ms`,
    }}>{children}</As>
  );
};

/* ── Landing page ───────────────────────────────────────── */
function LandingPage({ navigate }) {
  const [annual, setAnnual] = useState(true);
  const [salesOpen, setSalesOpen] = useState(false);
  const [salesPlan, setSalesPlan] = useState(null);

  // Body needs scroll for landing (app forces overflow:hidden)
  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    const root = document.getElementById("root");
    const prev = {
      htmlOverflow: html.style.overflow, bodyOverflow: body.style.overflow,
      htmlHeight: html.style.height, bodyHeight: body.style.height,
      rootHeight: root?.style.height, rootOverflow: root?.style.overflow,
    };
    html.style.overflow = "auto"; body.style.overflow = "auto";
    html.style.height = "auto"; body.style.height = "auto";
    if (root) { root.style.height = "auto"; root.style.overflow = "visible"; }
    return () => {
      html.style.overflow = prev.htmlOverflow; body.style.overflow = prev.bodyOverflow;
      html.style.height = prev.htmlHeight; body.style.height = prev.bodyHeight;
      if (root) { root.style.height = prev.rootHeight; root.style.overflow = prev.rootOverflow; }
    };
  }, []);

  const openSales = (plan) => { setSalesPlan(plan); setSalesOpen(true); };

  return (
    <div style={{
      position: "relative", minHeight: "100vh", overflow: "hidden",
      background: "var(--bg)",
    }}>
      <AmbientBackdrop/>
      <CursorGlow/>

      <LandingNav navigate={navigate} onSales={() => openSales("Enterprise")}/>
      <LandingHero navigate={navigate} onSales={() => openSales("Enterprise")}/>
      <LogosMarquee/>
      <FeatureGrid/>
      <LiveDemoSection/>
      <PricingSection annual={annual} setAnnual={setAnnual} onSales={openSales} navigate={navigate}/>
      <ComparisonTable/>
      <StatsBand/>
      <TestimonialsSection/>
      <FAQSection/>
      <FinalCTA navigate={navigate} onSales={() => openSales("Enterprise")}/>
      <LandingFooter navigate={navigate}/>

      <SalesDialog open={salesOpen} onClose={() => setSalesOpen(false)} planSeed={salesPlan}/>
    </div>
  );
}

/* Module-scoped theme reader (replaces a window.__landingTheme singleton) */
const themeStore = { get: () => document.documentElement.getAttribute("data-theme") || "dark" };

/* ── Nav ────────────────────────────────────────────────── */
function LandingNav({ navigate, onSales }) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  const [theme, setTheme] = useState(themeStore.get());
  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    setTheme(next);
  };

  const linkStyle = { fontSize: 13, color: "var(--fg-muted)", padding: "6px 10px", borderRadius: 6 };
  const scrollTo = (id) => {
    const el = document.getElementById(id);
    if (el) {
      const top = el.getBoundingClientRect().top + window.scrollY - 60;
      window.scrollTo({ top, behavior: "smooth" });
    }
  };

  return (
    <nav style={{
      position: "sticky", top: 0, zIndex: 30,
      borderBottom: scrolled ? "1px solid var(--border)" : "1px solid transparent",
      background: scrolled ? "color-mix(in srgb, var(--bg) 78%, transparent)" : "transparent",
      backdropFilter: "blur(20px) saturate(160%)",
      WebkitBackdropFilter: "blur(20px) saturate(160%)",
      transition: "all 0.3s var(--ease-out)",
    }}>
      <div style={{
        maxWidth: 1240, margin: "0 auto", padding: "14px 28px",
        display: "flex", alignItems: "center", gap: 20,
      }}>
        <a onClick={() => navigate("/")} style={{ cursor: "default" }}>
          <CodaraLogo size={22}/>
        </a>

        <div style={{ display: "flex", gap: 4, marginLeft: 20 }}>
          <button onClick={() => scrollTo("features")} style={linkStyle} className="nav-link">Features</button>
          <button onClick={() => scrollTo("pricing")} style={linkStyle} className="nav-link">Pricing</button>
          <button onClick={() => scrollTo("compare")} style={linkStyle} className="nav-link">Compare</button>
          <button onClick={() => scrollTo("faq")} style={linkStyle} className="nav-link">FAQ</button>
          <button style={linkStyle} className="nav-link">Docs</button>
          <button style={linkStyle} className="nav-link">Changelog</button>
        </div>

        <div style={{ flex: 1 }}/>

        <ThemeToggle value={theme} onChange={toggleTheme}/>
        <button className="btn btn-ghost btn-sm" onClick={onSales}>
          <Icon name="message" size={12}/> Talk to sales
        </button>
        <button className="btn btn-sm" onClick={() => navigate("/login")}>
          Sign in <Icon name="arrowRight" size={11}/>
        </button>
        <button className="btn btn-primary btn-sm" onClick={() => navigate("/signup")}>
          Start free
        </button>
      </div>

      <style>{`
        .nav-link:hover { background: var(--surface-2); color: var(--fg); }
      `}</style>
    </nav>
  );
}

/* ── Hero ───────────────────────────────────────────────── */
function LandingHero({ navigate, onSales }) {
  const [phase, setPhase] = useState(0); // 0 sas, 1 morphing, 2 python
  useEffect(() => {
    const id = setInterval(() => setPhase(p => (p + 1) % 3), 3400);
    return () => clearInterval(id);
  }, []);

  return (
    <section style={{
      position: "relative", padding: "60px 28px 80px",
      maxWidth: 1240, margin: "0 auto",
      display: "grid", gridTemplateColumns: "1.1fr 1fr", gap: 60,
      alignItems: "center",
    }}>
      {/* Decorative aurora */}
      <div className="aurora-sweep" style={{ opacity: 0.7 }}/>
      <Constellation density={0.00009} link={120} speed={0.12}/>

      <div style={{ position: "relative", zIndex: 2 }}>
        <div className="badge" style={{
          background: "var(--accent-soft)", color: "var(--accent)",
          borderColor: "transparent", marginBottom: 18, fontSize: 11.5,
          animation: "pop 0.6s var(--ease-spring) both",
        }}>
          <span className="live-dot"/> v4.2 · Cost dashboard is now live
        </div>
        <h1 style={{
          fontSize: 56, lineHeight: 1.05, letterSpacing: "-0.035em",
          fontWeight: 600, marginBottom: 18,
          fontFamily: "var(--font-display)",
          animation: "pageInLong 0.7s var(--ease-out) both",
        }}>
          Ship modernized
          <br/>
          <span style={{
            background: "linear-gradient(120deg, var(--accent), var(--secondary), var(--accent))",
            backgroundSize: "200% 100%",
            WebkitBackgroundClip: "text", backgroundClip: "text",
            color: "transparent",
            animation: "shimmer 6s linear infinite",
          }}>Python</span> in minutes,
          <br/>not months.
        </h1>
        <p className="text-muted" style={{
          fontSize: 17, lineHeight: 1.55, marginBottom: 28, maxWidth: 520,
          animation: "pageInLong 0.7s var(--ease-out) 0.1s both",
        }}>
          Codara translates SAS into production-grade Python with
          line-by-line provenance, full test coverage, and a knowledge base
          your team owns.
        </p>
        <div style={{
          display: "flex", gap: 10, flexWrap: "wrap",
          animation: "pageInLong 0.7s var(--ease-out) 0.2s both",
        }}>
          <button className="btn btn-primary btn-lg" onClick={() => navigate("/signup")}
                  style={{ fontSize: 14, padding: "12px 22px" }}>
            Start your free trial <Icon name="arrowRight" size={13}/>
          </button>
          <button className="btn btn-lg" onClick={onSales} style={{ fontSize: 14, padding: "12px 22px" }}>
            <Icon name="message" size={13}/> Talk to sales
          </button>
        </div>
        <div style={{
          display: "flex", gap: 18, marginTop: 24,
          fontSize: 12, color: "var(--fg-subtle)",
          animation: "pageInLong 0.7s var(--ease-out) 0.3s both",
        }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Icon name="check" size={12} className="text-success"/> 50 conversions free
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Icon name="check" size={12} className="text-success"/> No credit card
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Icon name="check" size={12} className="text-success"/> SOC 2 Type II
          </span>
        </div>
      </div>

      {/* Right side — animated diff demo */}
      <div style={{ position: "relative", zIndex: 2, animation: "pageInLong 0.8s var(--ease-out) 0.2s both" }}>
        <HeroDiffDemo phase={phase}/>
      </div>
    </section>
  );
}

function HeroDiffDemo({ phase }) {
  return (
    <div className="panel" style={{
      padding: 0, overflow: "hidden", position: "relative",
      transform: "perspective(1400px) rotateY(-6deg) rotateX(3deg)",
      transition: "transform 0.5s var(--ease-out)",
      boxShadow: "var(--shadow-pop)",
    }}>
      {/* Window chrome */}
      <div style={{
        height: 32, background: "var(--bg-elev)", borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", padding: "0 12px", gap: 6,
      }}>
        <span style={{ width: 10, height: 10, borderRadius: 999, background: "#ed6a5e" }}/>
        <span style={{ width: 10, height: 10, borderRadius: 999, background: "#f5bf4f" }}/>
        <span style={{ width: 10, height: 10, borderRadius: 999, background: "#62c554" }}/>
        <span className="mono text-subtle" style={{ fontSize: 10.5, marginLeft: 8 }}>codara · monthly_rollup</span>
        <div style={{ flex: 1 }}/>
        <span className="badge" style={{ fontSize: 9 }}>auto</span>
      </div>

      {/* Body */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", minHeight: 360, background: "var(--bg-elev)" }}>
        {/* SAS */}
        <div style={{ padding: 16, borderRight: "1px solid var(--border)", overflow: "hidden", position: "relative" }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 6, marginBottom: 10,
            fontSize: 11, color: "var(--fg-muted)",
          }}><Icon name="tag" size={10}/> claims.sas</div>
          <pre className="mono" style={{
            margin: 0, fontSize: 11.5, lineHeight: 1.65, whiteSpace: "pre",
            color: "var(--fg)",
          }}>
{`data claims_clean;
  set raw.claims;
  where reported_date >= '01JAN26'd;
  if missing(loss_amount) then delete;
  loss_band = "low";
  if loss_amount > 5000 then loss_band = "med";
  if loss_amount > 25000 then loss_band = "high";
run;

proc means data=flagged noprint;
  class region loss_band;
  var loss_amount;
  output out=rollup
    mean=avg_loss
    sum=total_loss
    n=claim_count;
run;`}
          </pre>
        </div>
        {/* Python */}
        <div style={{ padding: 16, position: "relative", overflow: "hidden" }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 6, marginBottom: 10,
            fontSize: 11, color: "var(--fg-muted)",
          }}><Icon name="package" size={10}/> claims.py
            <span className="badge badge-success" style={{ marginLeft: "auto", fontSize: 9 }}>
              <Icon name="check" size={9}/> generated
            </span>
          </div>
          <pre className="mono" style={{
            margin: 0, fontSize: 11.5, lineHeight: 1.65, whiteSpace: "pre",
            color: "var(--fg)",
          }}>
{`def clean_claims(df: pd.DataFrame):
    df = df[df.reported_date >= "2026-01-01"]
    df = df.dropna(subset=["loss_amount"])
    df["loss_band"] = "low"
    df.loc[df.loss_amount > 5_000, "loss_band"] = "med"
    df.loc[df.loss_amount > 25_000, "loss_band"] = "high"
    return df

def rollup(df):
    return (df
        .groupby(["region", "loss_band"])
        .loss_amount
        .agg(avg_loss="mean",
             total_loss="sum",
             claim_count="count")
        .reset_index())`}
          </pre>
        </div>

        {/* Sweeping arrow that pulses across */}
        <div style={{
          position: "absolute", top: "50%", left: "50%",
          transform: "translate(-50%, -50%)",
          width: 36, height: 36, borderRadius: "50%",
          background: "var(--accent)", color: "var(--accent-fg)",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 0 0 6px color-mix(in srgb, var(--accent) 18%, transparent), var(--shadow-pop)",
          animation: "breathe 2.4s ease-in-out infinite",
        }}>
          <Icon name="arrowRight" size={14}/>
        </div>
      </div>

      {/* Footer strip showing pipeline */}
      <div style={{
        height: 36, background: "var(--bg-elev)", borderTop: "1px solid var(--border)",
        display: "flex", alignItems: "center", padding: "0 12px", gap: 10,
        fontSize: 10.5, color: "var(--fg-muted)",
      }}>
        <span className="live-dot"/>
        <span className="mono">claude-sonnet-4 · 23.4s · 96% coverage</span>
        <div style={{ flex: 1 }}/>
        {["Parse", "Chunk", "Translate", "Validate", "Merge"].map((s, i) => (
          <span key={i} style={{
            fontSize: 9.5, padding: "2px 6px", borderRadius: 3,
            background: i <= phase * 2 ? "var(--success-soft)" : "var(--surface-2)",
            color: i <= phase * 2 ? "var(--success)" : "var(--fg-subtle)",
            transition: "all 0.4s var(--ease-out)",
          }}>{s}</span>
        ))}
      </div>
    </div>
  );
}

/* ── Logos marquee ──────────────────────────────────────── */
function LogosMarquee() {
  const logos = [
    "Acme Insurance", "Westbridge Capital", "Helios Health", "Forge Bank",
    "Solstice Pharma", "Brookline Risk", "Verity Actuarial", "Northwind Bio",
  ];
  return (
    <section style={{ padding: "10px 28px 50px", textAlign: "center", position: "relative", zIndex: 2 }}>
      <Reveal>
        <p className="text-subtle" style={{ fontSize: 11, letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 22 }}>
          Trusted by data teams at
        </p>
      </Reveal>
      <div style={{
        position: "relative",
        maskImage: "linear-gradient(90deg, transparent, black 12%, black 88%, transparent)",
        WebkitMaskImage: "linear-gradient(90deg, transparent, black 12%, black 88%, transparent)",
        overflow: "hidden",
      }}>
        <div style={{
          display: "flex", gap: 48,
          animation: "marquee 38s linear infinite",
          width: "max-content",
        }}>
          {[...logos, ...logos].map((l, i) => (
            <span key={i} style={{
              fontFamily: "var(--font-display)", fontSize: 17,
              color: "var(--fg-muted)", whiteSpace: "nowrap",
              letterSpacing: "-0.01em",
              opacity: 0.7,
            }}>{l}</span>
          ))}
        </div>
      </div>
      <style>{`
        @keyframes marquee {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
      `}</style>
    </section>
  );
}

/* ── Feature grid ───────────────────────────────────────── */
function FeatureGrid() {
  const features = [
    { i: "git",       title: "Line-level provenance", body: "Every line of generated Python is traceable to its SAS source. Audit-ready by default.", c: "var(--accent)" },
    { i: "checkCircle", title: "Tests + types included", body: "Conversions ship with unit tests, type hints, and docstrings. Pass review on the first pass.", c: "var(--success)" },
    { i: "book",      title: "A knowledge base you own", body: "Edit, version, and pin SAS→Python translation patterns. Codara learns your codebase.", c: "var(--secondary)" },
    { i: "shield",    title: "SOC 2 + on-prem option", body: "Run Codara in your own VPC. Your SAS never leaves your network. SSO/SCIM ready.", c: "var(--info)" },
    { i: "zap",       title: "Massively parallel pipeline", body: "8-stage pipeline runs batches concurrently. 500-file repos done overnight.", c: "var(--warning)" },
    { i: "dollar",    title: "Predictable cost", body: "Token budgets per project, model fallbacks, and a live cost dashboard with EOM forecasting.", c: "var(--chart-4)" },
  ];
  return (
    <section id="features" style={{ padding: "60px 28px", maxWidth: 1240, margin: "0 auto", position: "relative", zIndex: 2 }}>
      <Reveal>
        <div className="eyebrow" style={{ color: "var(--accent)" }}>Why Codara</div>
        <h2 style={{ fontSize: 36, fontWeight: 600, letterSpacing: "-0.025em", marginTop: 8, marginBottom: 14, maxWidth: 720, fontFamily: "var(--font-display)" }}>
          A migration team in a box — without the four-month learning curve.
        </h2>
        <p className="text-muted" style={{ fontSize: 15, maxWidth: 620, lineHeight: 1.6, marginBottom: 36 }}>
          Codara isn't a code translator. It's a workflow that produces shippable Python and the institutional knowledge to maintain it.
        </p>
      </Reveal>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
        {features.map((f, i) => (
          <Reveal key={i} delay={i * 60}>
            <div className="panel lift" style={{
              padding: 22, position: "relative", overflow: "hidden", height: "100%",
            }}>
              <div style={{
                position: "absolute", top: -20, right: -20, width: 120, height: 120,
                background: `radial-gradient(circle, color-mix(in srgb, ${f.c} 22%, transparent), transparent 70%)`,
                pointerEvents: "none",
              }}/>
              <div style={{
                width: 42, height: 42, borderRadius: "var(--radius)", marginBottom: 16,
                background: `color-mix(in srgb, ${f.c} 14%, var(--surface-2))`,
                color: f.c, display: "inline-flex", alignItems: "center", justifyContent: "center",
                position: "relative",
              }}><Icon name={f.i} size={18}/></div>
              <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 8, position: "relative" }}>{f.title}</h3>
              <p className="text-muted" style={{ fontSize: 13.5, lineHeight: 1.6, position: "relative" }}>{f.body}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ── Live demo section ──────────────────────────────────── */
function LiveDemoSection() {
  const [stage, setStage] = useState(0);
  const stages = [
    { label: "Parsing AST", time: "0.3s" },
    { label: "Chunking by dependency", time: "0.8s" },
    { label: "Resolving lineage", time: "1.2s" },
    { label: "Translating with claude-sonnet-4", time: "18.4s" },
    { label: "Validating syntax", time: "0.9s" },
    { label: "Running tests", time: "2.4s" },
    { label: "Merging modules", time: "0.4s" },
    { label: "Done", time: "✓" },
  ];

  useEffect(() => {
    const id = setInterval(() => setStage(s => (s + 1) % (stages.length + 2)), 700);
    return () => clearInterval(id);
  }, []);

  return (
    <section style={{ padding: "60px 28px", maxWidth: 1240, margin: "0 auto", position: "relative", zIndex: 2 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 50, alignItems: "center" }}>
        <Reveal>
          <div className="eyebrow" style={{ color: "var(--accent)" }}>The pipeline</div>
          <h2 style={{ fontSize: 32, fontWeight: 600, letterSpacing: "-0.025em", marginTop: 8, marginBottom: 14, fontFamily: "var(--font-display)" }}>
            8 stages, fully observable.
          </h2>
          <p className="text-muted" style={{ fontSize: 15, lineHeight: 1.6, marginBottom: 20 }}>
            Watch every step, retry any stage, swap models per task. Conversions
            aren't a black box — they're a workflow you can tune.
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <span className="badge">Parse</span>
            <span className="badge">Chunk</span>
            <span className="badge">Lineage</span>
            <span className="badge">Translate</span>
            <span className="badge">Validate</span>
            <span className="badge">Repair</span>
            <span className="badge">Merge</span>
            <span className="badge">Finalize</span>
          </div>
        </Reveal>

        <Reveal delay={80}>
          <div className="panel" style={{ padding: 22, position: "relative" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Icon name="fileCode" size={14} className="text-accent"/>
                <span className="mono" style={{ fontSize: 12 }}>monthly_rollup.sas</span>
              </div>
              <span className="mono text-subtle" style={{ fontSize: 11 }}>
                {Math.min(stage, stages.length) * 12.5}% · {(Math.min(stage, stages.length) * 2.9).toFixed(1)}s
              </span>
            </div>
            <div style={{ height: 6, background: "var(--surface-2)", borderRadius: 999, overflow: "hidden", marginBottom: 18, position: "relative" }}>
              <div style={{
                height: "100%", width: `${Math.min(stage, stages.length) * 12.5}%`,
                background: "linear-gradient(90deg, var(--accent), var(--secondary))",
                borderRadius: 999, transition: "width 0.6s var(--ease-out)",
              }}>
                <div style={{
                  position: "absolute", inset: 0,
                  background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.25), transparent)",
                  animation: "shimmer 1.5s linear infinite",
                }}/>
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              {stages.map((s, i) => {
                const done = i < stage;
                const running = i === stage && stage < stages.length;
                return (
                  <div key={i} style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "7px 10px", borderRadius: "var(--radius-sm)",
                    background: running ? "color-mix(in srgb, var(--accent) 6%, transparent)" : "transparent",
                    opacity: i > stage ? 0.4 : 1,
                    transition: "all 0.3s var(--ease-out)",
                  }}>
                    <div style={{ width: 16, height: 16, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                      {done && (
                        <div style={{
                          width: 14, height: 14, borderRadius: 999, background: "var(--success-soft)",
                          color: "var(--success)", display: "inline-flex", alignItems: "center", justifyContent: "center",
                        }}><Icon name="check" size={9} strokeWidth={3}/></div>
                      )}
                      {running && (
                        <div style={{
                          width: 14, height: 14, borderRadius: 999,
                          border: "1.5px solid var(--accent-soft)", borderTopColor: "var(--accent)",
                          animation: "spin 0.8s linear infinite",
                        }}/>
                      )}
                      {!done && !running && (
                        <div style={{ width: 12, height: 12, borderRadius: 999, border: "1.2px dashed var(--border-strong)" }}/>
                      )}
                    </div>
                    <span style={{ flex: 1, fontSize: 12.5, fontWeight: running ? 500 : 400,
                                    color: running ? "var(--accent)" : done ? "var(--fg)" : "var(--fg-muted)" }}>
                      {s.label}
                    </span>
                    {done && <span className="mono text-subtle" style={{ fontSize: 10.5 }}>{s.time}</span>}
                  </div>
                );
              })}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* ── Pricing ────────────────────────────────────────────── */
function PricingSection({ annual, setAnnual, onSales, navigate }) {
  const plans = [
    {
      id: "free", name: "Free", tagline: "For solo experiments",
      monthly: 0, annual: 0, accent: "var(--fg-muted)",
      cta: "Start free", action: () => navigate("/signup"),
      includes: [
        "50 conversions / month",
        "Files up to 200 LOC",
        "Side-by-side diff workspace",
        "Knowledge base browsing",
        "Community support",
      ],
    },
    {
      id: "pro", name: "Pro", tagline: "For individual practitioners",
      monthly: 49, annual: 39, accent: "var(--accent)", featured: true,
      cta: "Start free trial", action: () => navigate("/signup"),
      includes: [
        "Unlimited conversions",
        "Files up to 5,000 LOC",
        "All pipeline stages + retries",
        "Editable knowledge base",
        "Cost dashboard + budgets",
        "Email support, < 24h",
      ],
    },
    {
      id: "team", name: "Team", tagline: "For migration squads",
      monthly: 249, annual: 199, accent: "var(--secondary)",
      cta: "Start free trial", action: () => navigate("/signup"),
      includes: [
        "Everything in Pro",
        "Up to 10 seats",
        "Shared projects + audit log",
        "SSO (Google, SAML)",
        "Prompt template versioning",
        "Slack / Teams alerts",
        "Priority support, < 4h",
      ],
    },
    {
      id: "ent", name: "Enterprise", tagline: "For regulated industries",
      monthly: null, annual: null, accent: "var(--success)",
      cta: "Talk to sales", action: () => onSales("Enterprise"),
      includes: [
        "Everything in Team",
        "Unlimited seats",
        "On-prem / VPC deployment",
        "Custom models + fine-tuning",
        "SCIM, audit export, DLP",
        "SOC 2, ISO 27001, HIPAA",
        "Dedicated solutions engineer",
      ],
    },
  ];

  return (
    <section id="pricing" style={{ padding: "70px 28px 50px", maxWidth: 1240, margin: "0 auto", position: "relative", zIndex: 2 }}>
      <Reveal>
        <div className="eyebrow" style={{ color: "var(--accent)", textAlign: "center" }}>Pricing</div>
        <h2 style={{ fontSize: 38, fontWeight: 600, letterSpacing: "-0.025em",
                      marginTop: 8, marginBottom: 12, textAlign: "center", fontFamily: "var(--font-display)" }}>
          Pay for what you ship.
        </h2>
        <p className="text-muted" style={{ fontSize: 15, textAlign: "center", maxWidth: 580, margin: "0 auto 28px", lineHeight: 1.6 }}>
          Start free, scale as your migration grows. Cancel anytime. Save 20% with annual billing.
        </p>

        {/* Billing toggle */}
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 36 }}>
          <div className="toggle-pill" style={{ padding: 4, fontSize: 13 }}>
            <button aria-selected={!annual} onClick={() => setAnnual(false)} style={{ padding: "8px 18px", fontSize: 12 }}>Monthly</button>
            <button aria-selected={annual} onClick={() => setAnnual(true)} style={{ padding: "8px 18px", fontSize: 12, display: "inline-flex", alignItems: "center", gap: 6 }}>
              Annual <span className="badge badge-success" style={{ fontSize: 9, padding: "1px 5px" }}>SAVE 20%</span>
            </button>
          </div>
        </div>
      </Reveal>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, alignItems: "stretch" }}>
        {plans.map((p, i) => (
          <Reveal key={p.id} delay={i * 70}>
            <PricingCard plan={p} annual={annual}/>
          </Reveal>
        ))}
      </div>

      <Reveal>
        <p className="text-subtle" style={{ textAlign: "center", fontSize: 12, marginTop: 24 }}>
          All plans include unlimited team members on view-only seats. Prices in USD.
        </p>
      </Reveal>
    </section>
  );
}

function PricingCard({ plan, annual }) {
  const price = annual ? plan.annual : plan.monthly;
  const isCustom = price === null;
  const [count, setCount] = useState(price ?? 0);
  useEffect(() => {
    if (price == null) return;
    const start = performance.now(); const dur = 380;
    const from = count; const to = price;
    let raf;
    const step = (now) => {
      const t = Math.min(1, (now - start) / dur);
      const e = 1 - Math.pow(1 - t, 3);
      setCount(Math.round(from + (to - from) * e));
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [price]);

  return (
    <div className="lift" style={{
      position: "relative", borderRadius: "var(--radius-lg)",
      background: plan.featured ? "linear-gradient(180deg, color-mix(in srgb, var(--accent) 8%, var(--surface)) 0%, var(--surface) 60%)" : "var(--surface)",
      border: plan.featured ? "1.5px solid var(--accent)" : "1px solid var(--border)",
      padding: 22, display: "flex", flexDirection: "column",
      boxShadow: plan.featured ? "0 12px 40px color-mix(in srgb, var(--accent) 22%, transparent)" : "var(--shadow-1)",
      overflow: "hidden",
    }}>
      {plan.featured && (
        <div style={{
          position: "absolute", top: 14, right: -28, transform: "rotate(35deg)",
          background: "var(--accent)", color: "var(--accent-fg)",
          padding: "3px 30px", fontSize: 10, fontWeight: 700, letterSpacing: "0.06em",
        }}>POPULAR</div>
      )}
      {plan.featured && (
        <div style={{
          position: "absolute", inset: 0, pointerEvents: "none",
          background: "radial-gradient(circle at top right, color-mix(in srgb, var(--accent) 14%, transparent), transparent 60%)",
        }}/>
      )}

      <div style={{ position: "relative" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <span style={{
            width: 8, height: 8, borderRadius: 999, background: plan.accent,
            boxShadow: `0 0 0 3px color-mix(in srgb, ${plan.accent} 22%, transparent)`,
          }}/>
          <h3 style={{ fontSize: 18, fontWeight: 600 }}>{plan.name}</h3>
        </div>
        <p className="text-muted" style={{ fontSize: 12.5, minHeight: 18, marginBottom: 18 }}>{plan.tagline}</p>

        <div style={{ marginBottom: 18, minHeight: 60 }}>
          {isCustom ? (
            <div style={{ fontSize: 32, fontWeight: 600, fontFamily: "var(--font-display)", letterSpacing: "-0.02em" }}>Custom</div>
          ) : (
            <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
              <span style={{ fontSize: 14, color: "var(--fg-muted)" }}>$</span>
              <span style={{ fontSize: 44, fontWeight: 600, fontFamily: "var(--font-display)", lineHeight: 1, letterSpacing: "-0.03em" }}>
                {count}
              </span>
              <span className="text-muted" style={{ fontSize: 13 }}>/seat/mo</span>
            </div>
          )}
          {!isCustom && annual && plan.monthly > 0 && (
            <div className="text-subtle" style={{ fontSize: 11, marginTop: 4 }}>
              billed annually · save ${(plan.monthly - plan.annual) * 12}/yr
            </div>
          )}
          {isCustom && <div className="text-subtle" style={{ fontSize: 11, marginTop: 4 }}>From $1,200/mo · annual contract</div>}
        </div>

        <button
          onClick={plan.action}
          className={plan.featured ? "btn btn-primary" : "btn"}
          style={{
            width: "100%", padding: "10px 14px", fontSize: 13, fontWeight: 600, marginBottom: 18,
          }}
        >
          {plan.cta} <Icon name="arrowRight" size={12}/>
        </button>

        <div style={{ height: 1, background: "var(--border)", marginBottom: 14 }}/>

        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 9 }}>
          {plan.includes.map((it, i) => (
            <li key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12.5, lineHeight: 1.5 }}>
              <Icon name="check" size={12} className="text-success" style={{ marginTop: 3, flexShrink: 0 }}/>
              <span>{it}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/* ── Comparison table ───────────────────────────────────── */
function ComparisonTable() {
  const rows = [
    { cat: "Volume", label: "Conversions / month",  free: "50",      pro: "Unlimited", team: "Unlimited", ent: "Unlimited" },
    { cat: "Volume", label: "Max file size",         free: "200 LOC", pro: "5,000 LOC", team: "Unlimited", ent: "Unlimited" },
    { cat: "Volume", label: "Seats",                 free: "1",       pro: "1",         team: "10",        ent: "Unlimited" },
    { cat: "Workflow", label: "Side-by-side diff",   free: true,      pro: true,        team: true,        ent: true },
    { cat: "Workflow", label: "Pipeline retries",    free: false,     pro: true,        team: true,        ent: true },
    { cat: "Workflow", label: "Editable knowledge base", free: false, pro: true,        team: true,        ent: true },
    { cat: "Workflow", label: "Prompt templates",    free: false,     pro: false,       team: true,        ent: true },
    { cat: "Admin", label: "Cost dashboard",         free: false,     pro: true,        team: true,        ent: true },
    { cat: "Admin", label: "Audit logs",             free: false,     pro: "30 days",   team: "1 year",    ent: "Unlimited" },
    { cat: "Admin", label: "SSO (SAML / Google)",    free: false,     pro: false,       team: true,        ent: true },
    { cat: "Admin", label: "SCIM provisioning",      free: false,     pro: false,       team: false,       ent: true },
    { cat: "Security", label: "SOC 2 Type II",       free: true,      pro: true,        team: true,        ent: true },
    { cat: "Security", label: "On-prem / VPC",       free: false,     pro: false,       team: false,       ent: true },
    { cat: "Security", label: "Custom DLP",          free: false,     pro: false,       team: false,       ent: true },
    { cat: "Support", label: "Response time",        free: "Community", pro: "< 24h",   team: "< 4h",      ent: "< 1h" },
    { cat: "Support", label: "Solutions engineer",   free: false,     pro: false,       team: false,       ent: true },
  ];
  const cell = (v) => v === true ? <Icon name="check" size={14} className="text-success"/>
                     : v === false ? <span className="text-subtle" style={{ fontSize: 12 }}>—</span>
                     : <span style={{ fontSize: 12 }}>{v}</span>;

  let lastCat = "";
  return (
    <section id="compare" style={{ padding: "60px 28px", maxWidth: 1240, margin: "0 auto", position: "relative", zIndex: 2 }}>
      <Reveal>
        <div className="eyebrow" style={{ color: "var(--accent)" }}>Compare plans</div>
        <h2 style={{ fontSize: 30, fontWeight: 600, letterSpacing: "-0.025em",
                      marginTop: 8, marginBottom: 24, fontFamily: "var(--font-display)" }}>
          Everything, side by side.
        </h2>
      </Reveal>

      <Reveal>
        <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
          {/* Header row */}
          <div style={{
            display: "grid", gridTemplateColumns: "minmax(220px, 2fr) repeat(4, 1fr)",
            padding: "16px 22px", borderBottom: "1px solid var(--border)",
            background: "var(--bg-elev)", fontSize: 13, fontWeight: 600,
          }}>
            <div>Capability</div>
            <div>Free</div>
            <div style={{ color: "var(--accent)" }}>Pro</div>
            <div style={{ color: "var(--secondary)" }}>Team</div>
            <div style={{ color: "var(--success)" }}>Enterprise</div>
          </div>
          {rows.map((r, i) => {
            const newCat = r.cat !== lastCat;
            lastCat = r.cat;
            return (
              <React.Fragment key={i}>
                {newCat && (
                  <div style={{
                    padding: "10px 22px", background: "var(--surface-2)",
                    fontSize: 10, fontWeight: 700, letterSpacing: "0.08em",
                    textTransform: "uppercase", color: "var(--fg-muted)",
                  }}>{r.cat}</div>
                )}
                <div style={{
                  display: "grid", gridTemplateColumns: "minmax(220px, 2fr) repeat(4, 1fr)",
                  padding: "12px 22px", borderBottom: "1px solid var(--border)",
                  alignItems: "center", fontSize: 13,
                }}>
                  <div className="text-muted">{r.label}</div>
                  <div>{cell(r.free)}</div>
                  <div>{cell(r.pro)}</div>
                  <div>{cell(r.team)}</div>
                  <div>{cell(r.ent)}</div>
                </div>
              </React.Fragment>
            );
          })}
        </div>
      </Reveal>
    </section>
  );
}

/* ── Stats band (counter on view) ───────────────────────── */
function StatsBand() {
  const stats = [
    { v: 2.4, suffix: "M", label: "Lines translated last month" },
    { v: 96,  suffix: "%", label: "Average test coverage" },
    { v: 23,  suffix: "s", label: "Median conversion time" },
    { v: 180, suffix: "h", label: "Engineer-hours saved per project" },
  ];
  return (
    <section style={{
      padding: "40px 28px", maxWidth: 1240, margin: "20px auto",
      position: "relative", zIndex: 2,
    }}>
      <Reveal>
        <div style={{
          padding: "36px 32px", borderRadius: "var(--radius-xl)",
          background: "linear-gradient(135deg, color-mix(in srgb, var(--accent) 10%, var(--bg-elev)), color-mix(in srgb, var(--secondary) 6%, var(--bg-elev)))",
          border: "1px solid var(--border)",
          position: "relative", overflow: "hidden",
        }}>
          <div className="dot-grid-fine" style={{ position: "absolute", inset: 0, opacity: 0.3 }}/>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 24, position: "relative" }}>
            {stats.map((s, i) => (
              <Reveal key={i} delay={i * 80}>
                <div>
                  <div style={{
                    fontSize: 44, fontWeight: 600, fontFamily: "var(--font-display)",
                    letterSpacing: "-0.03em", lineHeight: 1,
                    background: "linear-gradient(135deg, var(--accent), var(--secondary))",
                    WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent",
                  }}>
                    <AnimatedNumber value={s.v}/>{s.suffix}
                  </div>
                  <div className="text-muted" style={{ fontSize: 13, marginTop: 6 }}>{s.label}</div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </Reveal>
    </section>
  );
}

/* ── Testimonials ───────────────────────────────────────── */
function TestimonialsSection() {
  const quotes = [
    { q: "We cut our planned 14-month SAS modernization to 11 weeks. The KB became our institutional memory.",
      n: "Priya Iyer", r: "Director of Data Eng · Helios Health" },
    { q: "Codara is the first translator that produces Python my team would actually merge. Tests included, types included.",
      n: "Marcus Reyes", r: "Principal Engineer · Forge Bank" },
    { q: "On-prem deployment was painless. Our SAS never left the network and the audit logs satisfied compliance.",
      n: "Aiyana Whitehorse", r: "VP Risk Engineering · Westbridge Capital" },
  ];
  return (
    <section style={{ padding: "60px 28px", maxWidth: 1240, margin: "0 auto", position: "relative", zIndex: 2 }}>
      <Reveal>
        <div className="eyebrow" style={{ color: "var(--accent)", textAlign: "center" }}>What teams say</div>
        <h2 style={{ fontSize: 30, fontWeight: 600, letterSpacing: "-0.025em",
                      marginTop: 8, marginBottom: 32, textAlign: "center", fontFamily: "var(--font-display)" }}>
          From SAS-first to Python-fluent.
        </h2>
      </Reveal>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14 }}>
        {quotes.map((q, i) => (
          <Reveal key={i} delay={i * 80}>
            <div className="panel lift" style={{ padding: 24, height: "100%", display: "flex", flexDirection: "column" }}>
              <div style={{ fontSize: 26, color: "var(--accent)", lineHeight: 0.8, marginBottom: 12, fontFamily: "var(--font-display)" }}>"</div>
              <p style={{ fontSize: 14, lineHeight: 1.6, marginBottom: 18, flex: 1 }}>{q.q}</p>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <Avatar name={q.n} size={32}/>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 12.5 }}>{q.n}</div>
                  <div className="text-subtle" style={{ fontSize: 11 }}>{q.r}</div>
                </div>
              </div>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ── FAQ ────────────────────────────────────────────────── */
function FAQSection() {
  const faqs = [
    { q: "Does my SAS code leave my network?",
      a: "On Free, Pro, and Team plans, requests go through our SOC 2 Type II compliant cloud. Enterprise customers can deploy Codara entirely inside their own VPC or on-prem — your SAS never leaves your network." },
    { q: "What SAS features are supported?",
      a: "DATA steps, PROC SQL, PROC MEANS/SUMMARY/FREQ/TABULATE, macros (%MACRO/%MEND), FORMAT/INFORMAT, RETAIN, FIRST.x/LAST.x, BY-group processing, HASH tables, and most ARRAY constructs. We're shipping support for IML and DS2 next quarter." },
    { q: "Can I edit translations after generation?",
      a: "Yes — every chunk is editable inline in the Workspace. Edits are saved back to your Knowledge Base as patterns, so the next conversion learns from them." },
    { q: "How does pricing work for seats vs conversions?",
      a: "Pro and Team are billed per seat. Conversions are unlimited on paid plans, with fair-use guardrails enforced via our cost dashboard. Enterprise can negotiate volume-based pricing." },
    { q: "Do you offer a free trial of paid plans?",
      a: "Yes — every paid plan starts with a 14-day trial, no credit card required. You get full Pro features during the trial, including the Cost Dashboard and full pipeline access." },
    { q: "What models do you use under the hood?",
      a: "Primarily Anthropic Claude (Sonnet for translation, Haiku for chunking/validation). Enterprise customers can plug in their own LLM providers (Azure OpenAI, Bedrock, self-hosted) via our model gateway." },
  ];
  return (
    <section id="faq" style={{ padding: "60px 28px 30px", maxWidth: 980, margin: "0 auto", position: "relative", zIndex: 2 }}>
      <Reveal>
        <div className="eyebrow" style={{ color: "var(--accent)", textAlign: "center" }}>FAQ</div>
        <h2 style={{ fontSize: 30, fontWeight: 600, letterSpacing: "-0.025em",
                      marginTop: 8, marginBottom: 28, textAlign: "center", fontFamily: "var(--font-display)" }}>
          Questions, anticipated.
        </h2>
      </Reveal>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {faqs.map((f, i) => (
          <Reveal key={i} delay={i * 30}>
            <FAQItem q={f.q} a={f.a}/>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

function FAQItem({ q, a }) {
  const [open, setOpen] = useState(false);
  const innerRef = useRef(null);
  return (
    <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
      <button onClick={() => setOpen(o => !o)} style={{
        width: "100%", textAlign: "left", padding: "16px 20px",
        display: "flex", alignItems: "center", gap: 14,
      }}>
        <span style={{ fontSize: 14.5, fontWeight: 500, flex: 1 }}>{q}</span>
        <div style={{
          width: 26, height: 26, borderRadius: 999,
          background: open ? "var(--accent)" : "var(--surface-2)",
          color: open ? "var(--accent-fg)" : "var(--fg-muted)",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          transition: "all 0.3s var(--ease-out)",
        }}>
          <Icon name={open ? "x" : "plus"} size={12} strokeWidth={2.5}/>
        </div>
      </button>
      <div style={{
        maxHeight: open ? (innerRef.current?.scrollHeight || 200) : 0,
        overflow: "hidden",
        transition: "max-height 0.4s var(--ease-out)",
      }}>
        <div ref={innerRef} style={{ padding: "0 20px 18px" }}>
          <p className="text-muted" style={{ fontSize: 13.5, lineHeight: 1.65 }}>{a}</p>
        </div>
      </div>
    </div>
  );
}

/* ── Final CTA ──────────────────────────────────────────── */
function FinalCTA({ navigate, onSales }) {
  return (
    <section style={{ padding: "60px 28px", maxWidth: 1240, margin: "0 auto", position: "relative", zIndex: 2 }}>
      <Reveal>
        <div style={{
          position: "relative", overflow: "hidden",
          padding: "60px 40px", borderRadius: "var(--radius-xl)",
          background: "linear-gradient(135deg, color-mix(in srgb, var(--accent) 18%, var(--surface)) 0%, color-mix(in srgb, var(--secondary) 14%, var(--surface)) 100%)",
          border: "1px solid var(--border)",
          textAlign: "center",
        }}>
          <div className="aurora-sweep" style={{ opacity: 0.5 }}/>
          <div style={{ position: "relative" }}>
            <div style={{
              display: "inline-flex", marginBottom: 24,
              animation: "breathe 4s ease-in-out infinite",
            }}>
              <CodaraMascot size={120}/>
            </div>
            <h2 style={{
              fontSize: 42, fontWeight: 600, letterSpacing: "-0.025em",
              marginBottom: 14, fontFamily: "var(--font-display)", lineHeight: 1.1,
            }}>
              Stop maintaining SAS.
              <br/>Start shipping Python.
            </h2>
            <p className="text-muted" style={{ fontSize: 15, maxWidth: 560, margin: "0 auto 28px", lineHeight: 1.6 }}>
              Try Codara free for 14 days. No credit card. Your first conversion in under five minutes.
            </p>
            <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" }}>
              <button className="btn btn-primary btn-lg" onClick={() => navigate("/signup")}
                      style={{ fontSize: 14, padding: "12px 24px" }}>
                Start free trial <Icon name="arrowRight" size={13}/>
              </button>
              <button className="btn btn-lg" onClick={onSales}
                      style={{ fontSize: 14, padding: "12px 24px" }}>
                <Icon name="message" size={13}/> Talk to sales
              </button>
              <button className="btn btn-lg btn-ghost" onClick={() => navigate("/login")}
                      style={{ fontSize: 14, padding: "12px 24px" }}>
                Sign in
              </button>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  );
}

/* ── Footer ─────────────────────────────────────────────── */
function LandingFooter({ navigate }) {
  const cols = [
    { title: "Product", items: ["Features", "Pricing", "Changelog", "Roadmap", "Status"] },
    { title: "Resources", items: ["Documentation", "Knowledge base", "SAS coverage", "Migration guide", "Blog"] },
    { title: "Company", items: ["About", "Customers", "Careers", "Press kit", "Contact"] },
    { title: "Legal", items: ["Terms", "Privacy", "Security", "DPA", "Cookies"] },
  ];
  return (
    <footer style={{
      padding: "60px 28px 36px", borderTop: "1px solid var(--border)",
      position: "relative", zIndex: 2, background: "var(--bg-elev)",
    }}>
      <div style={{ maxWidth: 1240, margin: "0 auto",
                     display: "grid", gridTemplateColumns: "1.4fr repeat(4, 1fr)", gap: 32 }}>
        <div>
          <CodaraLogo/>
          <p className="text-muted" style={{ fontSize: 12.5, marginTop: 14, lineHeight: 1.6, maxWidth: 280 }}>
            The fastest path from SAS to production Python. Built for regulated industries.
          </p>
          <div style={{ display: "flex", gap: 8, marginTop: 18 }}>
            <button className="btn btn-icon btn-ghost" aria-label="GitHub"><Icon name="git" size={14}/></button>
            <button className="btn btn-icon btn-ghost" aria-label="Twitter"><Icon name="message" size={14}/></button>
            <button className="btn btn-icon btn-ghost" aria-label="LinkedIn"><Icon name="link" size={14}/></button>
            <button className="btn btn-icon btn-ghost" aria-label="Mail"><Icon name="mail" size={14}/></button>
          </div>
        </div>
        {cols.map((c, i) => (
          <div key={i}>
            <div className="eyebrow" style={{ marginBottom: 12 }}>{c.title}</div>
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 7 }}>
              {c.items.map((it, j) => (
                <li key={j}><a style={{ fontSize: 12.5, color: "var(--fg-muted)" }}>{it}</a></li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div style={{
        maxWidth: 1240, margin: "40px auto 0", paddingTop: 20,
        borderTop: "1px solid var(--border)",
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap",
      }}>
        <div className="text-subtle" style={{ fontSize: 11.5 }}>
          © 2026 Codara, Inc. · SOC 2 Type II · ISO 27001
        </div>
        <div style={{ display: "flex", gap: 14, fontSize: 11.5 }}>
          <span className="text-subtle">All systems operational</span>
          <span className="live-dot"/>
        </div>
      </div>
    </footer>
  );
}
export { LandingPage };
export default LandingPage;
