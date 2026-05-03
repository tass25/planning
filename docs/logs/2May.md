# 2 May 2026 — Session Log

## Session 1: Deployment Fixes & Persistent Storage

### .env Recovery
- Recovered `.env` from Azure Key Vault + Container App env vars
- Removed dead Cerebras API key (code was already removed)

### Dead Code Removal
- Removed `get_cerebras_client()` and `get_cerebras_model()` from `backend/partition/utils/llm_clients.py`
- Removed `cerebras_api_key` and `cerebras_model` from `backend/config/settings.py`

### CI/CD Fix
- Fixed `.github/workflows/ci.yml` `paths-ignore: "**.txt"` which was blocking `requirements/base.txt` changes from triggering CI
- This was preventing the bcrypt<4.1.0 pin from deploying

### bcrypt Fix Deployed
- `bcrypt<4.1.0` pinned in `requirements/base.txt` (passlib compatibility)
- Image `sha-40163b6` built and deployed successfully
- Signup now works (verified via curl)

### Cold Start Fix
- Set `minReplicas=1` on both frontend and backend Container Apps
- Eliminates ~30s cold start on first request

### Azure Redis
- Registered `Microsoft.Cache` provider
- Created Azure Cache for Redis `codara-redis` (Basic C0, France Central)
- Connected backend to Redis via `rediss://` URL (SSL, port 6380)
- Health check confirms: `"redis":"ok"`

### Persistent Storage (SQLite)
- Created Azure Files share `codara-data` on storage account `pfestorage123`
- Linked to Container Apps environment as `codaradata`
- Mounted volume at `/app/backend/data` on backend container
- **SQLite database now persists across deploys** — fixes empty conversions page
- Seed users (admin@codara.dev, user@codara.dev) created and persist

### Verification Results
- Backend health: `{"status":"ok","version":"3.1.0","env":"production","dependencies":{"sqlite":"ok","redis":"ok","lancedb":"ok","ollama":"unavailable"}}`
- Admin login: OK
- User signup: OK (bcrypt fixed)
- Frontend proxy to backend: OK
- GitHub OAuth URL endpoint: OK (callback URL must be set correctly in GitHub app)

### Files Changed
- `.env` — recovered
- `.github/workflows/ci.yml` — paths-ignore fix
- `backend/partition/utils/llm_clients.py` — removed Cerebras code
- `backend/config/settings.py` — removed Cerebras fields
- `infra/backend-volume-mount.yaml` — new (Azure Files volume mount config)

---

## Session 2: Frontend UI/UX Transformation — "Noir Amber" Design System

### Design Direction
- **Codename**: "Noir Amber" — deep obsidian backgrounds, burning amber accents, kinetic glass surfaces
- **Typography**: Added Space Grotesk as `font-display` for all headlines (geometric, technical, precise)
- **Color System**: Deepened dark mode backgrounds (hsl(225,30%,4%)), refined light mode with cooler undertones
- **Animation Philosophy**: Every interactive element has personality — spring physics, cursor-tracking, staggered reveals

### New Animation Components Created (5 files)
- `frontend/src/components/ui/particle-field.tsx` — Canvas-based ambient particle background with floating dots, mouse-reactive connections, and smooth drift. Used on landing page hero.
- `frontend/src/components/ui/aurora-background.tsx` — CSS animated mesh gradient aurora effect with 3 layered orbs on independent animation cycles (12s/15s/18s). Variants: subtle/default/intense.
- `frontend/src/components/ui/animated-text.tsx` — Two components: `AnimatedText` (word-by-word reveal with spring physics) and `AnimatedChars` (character-by-character with blur-in). Uses Framer Motion stagger.
- `frontend/src/components/ui/glow-card.tsx` — Mouse-tracking radial gradient glow that follows cursor position. Built with Framer Motion entrance animations + spring physics.
- `frontend/src/components/ui/animated-counter.tsx` — IntersectionObserver-triggered number counting animation with easeOutQuart easing. Supports mixed prefix/suffix formats (e.g., "<3min", "97.3%").

### Foundation Updates
- `frontend/src/index.css` — New Google Font import (Space Grotesk), deepened dark mode palette, added `noise-bg` utility (SVG fractalNoise pseudo-element), 6 new CSS keyframes (aurora-1/2/3, float, shimmer, line-draw)
- `frontend/tailwind.config.ts` — Added `font-display` family, 7 new animation utilities (aurora-1/2/3, float, shimmer), registered all keyframes for Tailwind classes

### Pages Rewritten (5 files)
- `frontend/src/pages/Index.tsx` — Complete landing page rebuild:
  - Particle field background in hero section
  - Word-by-word animated headline with spring physics
  - Magnetic hover buttons (custom `useMagnetic` hook with spring-damped cursor tracking)
  - Scroll-driven parallax on code preview (scale + translateY)
  - Animated stat counters with IntersectionObserver
  - GlowCards with cursor-tracking glow borders on feature cards
  - Animated connecting lines on workflow steps (scaleX from 0)
  - Staggered entrance animations on all sections
  - Living status indicator (ping animation on badge)
  - Noise texture overlay on background

- `frontend/src/pages/Login.tsx` — Immersive auth experience:
  - Aurora background on branding panel
  - Spring-animated form elements (whileHover/whileTap on all buttons)
  - Refined input focus states (ring-2 + accent glow)
  - Consistent font-display on headings

- `frontend/src/pages/Signup.tsx` — Matching signup redesign:
  - Aurora background with animated step indicators
  - Icon-enhanced workflow steps in branding panel
  - Animated password validation checkmarks
  - Email verification screen with spring-scale entrance

- `frontend/src/components/layout/UserLayout.tsx` — Navigation overhaul:
  - Sliding active indicator (Framer Motion animated div tracks active nav item position)
  - Icon micro-rotations on hover (5-8 degree spring rotation)
  - Ping animation on notification bell
  - Spring physics on profile dropdown open/close
  - Staggered mobile menu items
  - Compact 14px header height (was 16px)
  - noise-bg on shell

- `frontend/src/components/layout/AdminLayout.tsx` — Sidebar polish:
  - Spring-animated sidebar collapse (motion.aside with spring transition)
  - AnimatePresence on nav labels for smooth text appear/disappear
  - Animated chevron rotation on collapse toggle
  - Status indicator with ping animation
  - Nav item hover slide (2px x-shift)

### Component Updates
- `frontend/src/components/CodaraLogo.tsx` — Changed to `font-display` (Space Grotesk) for brand consistency
- `frontend/src/components/dashboard/UserDashboard.tsx` — Full glow-up:
  - GlowCards on stat cards and step cards
  - AnimatedCounter on stat values
  - Floating upload icon animation (bounce)
  - Staggered file list entrance
  - Spring micro-interactions on all interactive elements

### Cleanup
- Removed unused imports: `Star`, `Zap`, `MotionValue` from Index.tsx
- Removed unused import: `Circle` from AdminLayout.tsx
- Removed unused import: `cn` from Login.tsx

### Build Status
- Could not verify build — bun is not installed on this machine and node_modules is incomplete (120 packages, missing react/typescript)
- All TypeScript code manually reviewed for correctness
- No new dependencies added — everything uses existing framer-motion + tailwind stack
