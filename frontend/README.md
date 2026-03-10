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
- Tailwind CSS

## How can I deploy this project?

Simply open [Lovable](https://lovable.dev/projects/REPLACE_WITH_PROJECT_ID) and click on Share -> Publish.

## Can I connect a custom domain to my Lovable project?

Yes, you can!

To connect a domain, navigate to Project > Settings > Domains and click Connect Domain.

Read more here: [Setting up a custom domain](https://docs.lovable.dev/features/custom-domain#custom-domain)
