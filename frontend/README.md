# Codara Frontend

React + TypeScript frontend for the Codara SAS-to-Python conversion platform.

## Tech Stack

- **React 18** + TypeScript
- **Vite** (dev server + build)
- **Tailwind CSS** + **shadcn/ui** components
- **Zustand** state management
- **Framer Motion** animations

## Structure

```
frontend/
├── src/
│   ├── components/         # Reusable UI components
│   │   ├── layout/         # TopBar, AdminLayout, Sidebar
│   │   └── ui/             # shadcn/ui primitives
│   ├── pages/              # Route pages
│   │   ├── Index.tsx        # Landing page
│   │   ├── Login.tsx        # Login + GitHub OAuth
│   │   ├── Signup.tsx       # Register + email verification
│   │   ├── Workspace.tsx    # Code conversion workspace
│   │   ├── Conversions.tsx  # Conversion history
│   │   └── admin/           # Admin pages (KB, users, dashboard)
│   ├── store/              # Zustand stores
│   ├── hooks/              # Custom React hooks
│   ├── lib/                # API client, utilities
│   └── types/              # TypeScript interfaces
├── public/                 # Static assets
├── index.html              # HTML entry point
├── vite.config.ts          # Vite config (proxy /api → backend:8000)
├── tailwind.config.ts      # Tailwind configuration
└── package.json            # Dependencies
```

## Quick Start

```bash
# Install dependencies
npm install

# Start dev server (port 8080, proxies /api to localhost:8000)
npm run dev

# Production build
npm run build

# Run tests
npm run test
```

## API Proxy

In development, Vite proxies `/api/*` requests to `http://localhost:8000`.
Make sure the backend is running on port 8000 before starting the frontend.

## Exception Handling

The frontend is crash-proofed so that **no error ever results in a white screen**.

### React Error Boundary (`components/ErrorBoundary.tsx`)

A class-based `ErrorBoundary` component wraps the entire application tree in `App.tsx`. It uses React's `getDerivedStateFromError` and `componentDidCatch` lifecycle methods to:

1. **Catch** any unhandled error thrown during rendering of any child component
2. **Log** the full error + component stack to `console.error`
3. **Display** a styled "Something went wrong" recovery page with:
   - The error message in a code block
   - A **"Try Again"** button that resets the error state and re-renders the tree
   - Dark theme styling consistent with the app's design

Without this, a single failing component (e.g., a bad API response parsed into JSX) would crash the entire React tree and show a blank white page.

### Guarded Initial Fetch (`App.tsx`)

```tsx
useEffect(() => {
  useUserStore.getState().restoreSession();
  if (getToken()) {
    useConversionStore.getState().fetchConversions();
  }
}, []);
```

`fetchConversions()` only fires if a JWT token exists in `localStorage`. Previously it fired unconditionally on every page load, causing a `401 Unauthorized` error in the console for unauthenticated users visiting the landing page, login, or signup pages.

### Store-Level Protections (pre-existing)

Both Zustand stores already wrap all API calls in `try/catch`:

- **`user-store.ts`** — `login()`, `signup()`, `loginWithGitHub()`, `verifyEmail()`, `restoreSession()`, `fetchNotifications()`, `markNotificationRead()`, `markAllNotificationsRead()` all catch errors and return graceful defaults (`false`, `{ success: false }`).
- **`conversion-store.ts`** — `pollConversion()` catches errors and calls `stopPolling()` instead of crashing. `uploadFiles()`, `startConversion()`, `fetchConversions()` propagate errors to the calling component where toast notifications display them.
- **`api.ts`** — The base `request()` function catches `res.json()` parse failures and falls back to `{ detail: res.statusText }`.

