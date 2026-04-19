# `frontend/src/` — React Application Source

## Structure

```
src/
├── components/   — shared UI components (buttons, modals, pipeline visualizer, etc.)
├── hooks/        — custom React hooks
├── lib/
│   └── api.ts    — thin fetch wrapper; injects JWT from localStorage, proxies to /api
├── pages/        — one file per route
│   ├── Login.tsx / Register.tsx
│   ├── Dashboard.tsx      — conversion history + stats
│   ├── Workspace.tsx      — main conversion UI (side-by-side SAS↔Python diff)
│   └── admin/             — admin-only pages (users, KB, audit logs, system health)
├── store/        — Zustand state management
│   ├── conversion-store.ts — upload, start, poll, stopPolling
│   ├── user-store.ts       — auth state (login, logout, JWT)
│   └── theme-store.ts      — dark/light mode preference
├── test/         — Vitest unit tests
└── types/
    └── index.ts  — TypeScript types mirroring the backend Pydantic schemas
```

## Key design decisions

**`lib/api.ts`** — All HTTP calls go through this one wrapper. It reads the JWT
from `localStorage("codara_token")` and adds the `Authorization: Bearer` header
automatically. Never call `fetch()` directly from a component.

**Zustand stores** — One store per domain. `conversion-store.ts` owns the full
conversion lifecycle (upload → start → poll → results). Components read from
the store and call store actions — they don't hold their own async state.

**Polling vs SSE** — The `pollConversion` action uses `setTimeout` (not `setInterval`)
so each tick waits for the previous one to finish. This prevents request pile-up
when the server is slow. Polling stops automatically on terminal states.
An SSE endpoint (`/api/conversions/{id}/stream`) also exists as an alternative.

**Type safety** — `src/types/index.ts` is the TypeScript equivalent of
`backend/api/core/schemas.py`. When you add a field to the backend schema,
add it here too so the compiler catches any missing UI handling.

## Running

```bash
cd frontend
bun run dev      # http://localhost:5173 — proxies /api → backend :8000
bun run build    # production build → dist/
bun run test     # Vitest unit tests
```
