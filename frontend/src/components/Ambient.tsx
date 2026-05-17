import { useState, useEffect, useRef } from "react";

function AmbientBackdrop() {
  const orbs = [
    { color: "accent",    w: 520, top: "-12%",  left: "-8%",   delay: 0,  dur: 26 },
    { color: "secondary", w: 460, top: "60%",   left: "70%",   delay: 4,  dur: 32 },
    { color: "accent",    w: 360, top: "70%",   left: "-10%",  delay: 8,  dur: 30 },
    { color: "secondary", w: 320, top: "-10%",  left: "60%",   delay: 12, dur: 28 },
  ];
  return (
    <div className="ambient-bg" aria-hidden="true">
      {orbs.map((o, i) => (
        <div key={i} className="ambient-orb" style={{
          width: o.w, height: o.w,
          top: o.top, left: o.left,
          background: `radial-gradient(circle, hsl(var(--${o.color})), transparent 65%)`,
          animation: `orbDrift ${o.dur}s ease-in-out ${o.delay}s infinite`,
        }}/>
      ))}
    </div>
  );
}

function CursorGlow() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let raf = 0;
    let tx = window.innerWidth / 2, ty = window.innerHeight / 2;
    let x = tx, y = ty;
    document.body.classList.add("has-cursor");
    const onMove = (e: PointerEvent) => { tx = e.clientX; ty = e.clientY; };
    const onLeave = () => { document.body.classList.remove("has-cursor"); };
    const onEnter = () => { document.body.classList.add("has-cursor"); };
    const tick = () => {
      x += (tx - x) * 0.16;
      y += (ty - y) * 0.16;
      if (ref.current) ref.current.style.transform = `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%)`;
      raf = requestAnimationFrame(tick);
    };
    window.addEventListener("pointermove", onMove);
    document.addEventListener("mouseleave", onLeave);
    document.addEventListener("mouseenter", onEnter);
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("mouseleave", onLeave);
      document.removeEventListener("mouseenter", onEnter);
      document.body.classList.remove("has-cursor");
    };
  }, []);
  return <div ref={ref} className="cursor-glow" aria-hidden="true"/>;
}

function Constellation({ density = 0.00018, color, link = 110, speed = 0.18 }: {
  density?: number; color?: string; link?: number; speed?: number;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current; if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    let raf = 0; let w = 0; let h = 0;
    let dots: { x: number; y: number; vx: number; vy: number; r: number }[] = [];

    const getStrokeColor = () => {
      if (color) return color;
      const raw = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
      return raw ? `hsl(${raw})` : "#d49530";
    };
    const stroke = getStrokeColor();

    const resize = () => {
      const rect = c.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = rect.width; h = rect.height;
      c.width = w * dpr; c.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.max(18, Math.round(w * h * density));
      dots = Array.from({ length: count }, () => ({
        x: Math.random() * w, y: Math.random() * h,
        vx: (Math.random() - 0.5) * speed, vy: (Math.random() - 0.5) * speed,
        r: 0.8 + Math.random() * 1.4,
      }));
    };

    const tick = () => {
      ctx.clearRect(0, 0, w, h);
      for (const d of dots) {
        d.x += d.vx; d.y += d.vy;
        if (d.x < 0 || d.x > w) d.vx *= -1;
        if (d.y < 0 || d.y > h) d.vy *= -1;
      }
      ctx.lineWidth = 1;
      for (let i = 0; i < dots.length; i++) {
        for (let j = i + 1; j < dots.length; j++) {
          const a = dots[i], b = dots[j];
          const dx = a.x - b.x, dy = a.y - b.y;
          const dist = Math.hypot(dx, dy);
          if (dist < link) {
            const op = (1 - dist / link) * 0.35;
            ctx.strokeStyle = stroke;
            ctx.globalAlpha = op;
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          }
        }
      }
      ctx.globalAlpha = 1;
      for (const d of dots) {
        ctx.fillStyle = stroke;
        ctx.globalAlpha = 0.6;
        ctx.beginPath(); ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2); ctx.fill();
      }
      raf = requestAnimationFrame(tick);
    };

    const ro = new ResizeObserver(resize);
    ro.observe(c);
    resize();
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, [density, color, link, speed]);
  return <canvas ref={ref} className="constellation" aria-hidden="true"/>;
}

function FloatParticles({ count = 14 }: { count?: number }) {
  return (
    <div className="float-particles" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <span key={i} style={{
          left: `${(i / count) * 100 + Math.random() * 8}%`,
          animationDuration: `${8 + Math.random() * 8}s`,
          animationDelay: `${Math.random() * 8}s`,
          width: `${2 + Math.random() * 3}px`,
          height: `${2 + Math.random() * 3}px`,
        }}/>
      ))}
    </div>
  );
}

function CodaraMascot({ size = 180 }: { size?: number }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [eye, setEye] = useState({ x: 0, y: 0 });
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const el = wrapRef.current; if (!el) return;
      const r = el.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const dx = e.clientX - cx;
      const dy = e.clientY - cy;
      const d = Math.hypot(dx, dy);
      const max = 3.4;
      const nx = (dx / (d || 1)) * Math.min(max, d / 80);
      const ny = (dy / (d || 1)) * Math.min(max, d / 80);
      setEye({ x: nx, y: ny });
    };
    window.addEventListener("pointermove", onMove);
    return () => window.removeEventListener("pointermove", onMove);
  }, []);

  const s = size;
  return (
    <div ref={wrapRef} style={{ width: s, height: s, position: "relative" }}>
      <div className="mascot-halo" style={{
        position: "absolute", inset: -s * 0.18, borderRadius: "50%",
      }}/>
      <svg width={s} height={s} viewBox="0 0 200 200" className="mascot-body">
        <g className="mascot-ring-outer">
          <circle cx="100" cy="100" r="92" fill="none"
                  stroke="hsl(var(--accent) / 0.35)"
                  strokeWidth="1.2" strokeDasharray="3 7"/>
        </g>
        <g className="mascot-ring-inner">
          <circle cx="100" cy="100" r="78" fill="none"
                  stroke="hsl(var(--secondary) / 0.30)"
                  strokeWidth="1" strokeDasharray="2 6"/>
        </g>

        <defs>
          <radialGradient id="mascot-grad" cx="40%" cy="35%" r="70%">
            <stop offset="0%"  stopColor="hsl(var(--accent))" stopOpacity="0.92"/>
            <stop offset="60%" stopColor="hsl(var(--accent))" stopOpacity="0.55"/>
            <stop offset="100%" stopColor="hsl(var(--secondary))" stopOpacity="0.5"/>
          </radialGradient>
          <radialGradient id="mascot-shine" cx="35%" cy="30%" r="40%">
            <stop offset="0%" stopColor="white" stopOpacity="0.5"/>
            <stop offset="100%" stopColor="white" stopOpacity="0"/>
          </radialGradient>
        </defs>
        <circle cx="100" cy="100" r="60" fill="url(#mascot-grad)"/>
        <circle cx="100" cy="100" r="60" fill="url(#mascot-shine)"/>

        <g className="mascot-brand-mark">
          <path d="M118 84 L82 100 L118 116" fill="none"
                stroke="white" strokeOpacity="0.92" strokeWidth="3.4"
                strokeLinecap="round" strokeLinejoin="round"/>
        </g>

        <g transform={`translate(${eye.x} ${eye.y})`}>
          <ellipse className="mascot-eye" cx="84" cy="96" rx="4.2" ry="5.4" fill="white"/>
          <ellipse className="mascot-eye mascot-eye-r" cx="116" cy="96" rx="4.2" ry="5.4" fill="white"/>
        </g>
        <path d="M88 116 Q100 124 112 116" fill="none" stroke="white" strokeOpacity="0.7"
              strokeWidth="2" strokeLinecap="round"/>
      </svg>
    </div>
  );
}

export { AmbientBackdrop, CursorGlow, Constellation, FloatParticles, CodaraMascot };
