# EcoTrace India — Frontend

React web dashboard for the **EcoTrace India** e-waste lifecycle management platform (IEEE YESIST 2026).

> **Status:** Sprint 9.1 — Frontend Foundation. This is **infrastructure only**:
> architecture, routing, state management, API layer, theming, and reusable
> layouts. No business dashboards or features are implemented yet.

---

## Tech Stack

| Concern          | Choice                          |
| ---------------- | ------------------------------- |
| Framework        | React 19                        |
| Build tool       | Vite 6                          |
| Language         | TypeScript (strict)             |
| Styling          | Tailwind CSS v4                 |
| UI primitives    | shadcn/ui (new-york) + Radix    |
| Icons            | lucide-react                    |
| Routing          | React Router v7                 |
| Server state     | TanStack Query v5               |
| HTTP client      | Axios (single shared instance)  |
| Forms            | React Hook Form + Zod           |
| Notifications    | Sonner                          |
| Linting / Format | ESLint (flat config) + Prettier |

The app consumes **only** the backend REST API (`/api/v1`) documented in
[`docs/engineering/05_API.md`](../docs/engineering/05_API.md).

---

## Prerequisites

- Node.js `>= 20`
- npm `>= 10`

---

## Setup

```bash
cd frontend

# 1. Install dependencies
npm install

# 2. Create your local environment file from the template
cp .env.example .env
#   (Windows PowerShell: Copy-Item .env.example .env)

# 3. Adjust VITE_API_BASE_URL in .env if your backend is not on localhost:3000
```

### Environment Variables

| Variable            | Description                     | Default                        |
| ------------------- | ------------------------------- | ------------------------------ |
| `VITE_API_BASE_URL` | Base URL of the backend API     | `http://localhost:3000/api/v1` |
| `VITE_API_TIMEOUT`  | Request timeout in milliseconds | `15000`                        |
| `VITE_APP_NAME`     | Display name of the application | `EcoTrace India`               |

Never commit `.env`; only `.env.example` is tracked.

---

## Scripts

| Command                | Description                                       |
| ---------------------- | ------------------------------------------------- |
| `npm run dev`          | Start the Vite dev server (http://localhost:5173) |
| `npm run build`        | Type-check and build for production (`dist/`)     |
| `npm run preview`      | Preview the production build locally              |
| `npm run lint`         | Run ESLint                                        |
| `npm run lint:fix`     | Run ESLint with autofix                           |
| `npm run typecheck`    | Type-check without emitting                       |
| `npm run format`       | Format the codebase with Prettier                 |
| `npm run format:check` | Verify formatting without writing                 |

---

## Folder Architecture

```
frontend/
├── public/                 # Static assets served as-is (favicon, etc.)
├── src/
│   ├── api/                # Single Axios instance + typed API modules
│   │   ├── axios.ts        #   instance, request/response interceptors, refresh hook
│   │   ├── client.ts       #   envelope unwrap + error normalization helpers
│   │   ├── auth.api.ts     #   auth endpoint wrappers (placeholders)
│   │   ├── submission.api.ts
│   │   ├── reward.api.ts
│   │   └── user.api.ts
│   ├── assets/             # Imported images/fonts
│   ├── components/
│   │   ├── common/         # ErrorBoundary, LoadingSpinner, Placeholder, ThemeToggle
│   │   ├── forms/          # Reusable form controls (later sprints)
│   │   ├── layout/         # Navbar, Sidebar, Footer
│   │   └── ui/             # shadcn/ui primitives (Button, ...)
│   ├── features/           # Feature/role modules (auth, consumer, collector, ...)
│   ├── hooks/              # Shared hooks (useAuth, useTheme)
│   ├── layouts/            # MainLayout (app shell), AuthLayout (centered)
│   ├── lib/                # utils, env, routes, query-keys (framework-agnostic)
│   ├── pages/              # Top-level routed pages (Login, Dashboard, NotFound)
│   ├── providers/          # QueryProvider, ThemeProvider, AuthProvider + contexts
│   ├── routes/             # AppRouter, ProtectedRoute, RoleGuard
│   ├── services/           # Non-React services (token storage abstraction)
│   ├── store/              # Global client state (only if needed later)
│   ├── styles/             # globals.css (Tailwind v4 + design tokens)
│   ├── types/              # Shared TypeScript types (API envelope, auth)
│   ├── utils/              # Pure utility functions (later sprints)
│   ├── App.tsx             # Provider composition + router
│   └── main.tsx            # Entry point
├── .env.example
├── components.json         # shadcn/ui configuration
├── eslint.config.js
├── index.html
├── tsconfig*.json
├── vite.config.ts
└── package.json
```

### Path Aliases

`@/` resolves to `src/` (configured in `vite.config.ts` and `tsconfig.app.json`).

```ts
import { Button } from '@/components/ui/button';
```

---

## Architecture Notes

- **API layer** — Exactly one Axios instance (`src/api/axios.ts`). UI code never
  calls `axios`/`fetch` directly. A request interceptor attaches the bearer
  token; a response interceptor centralizes error handling and the
  `401 → refresh → retry` flow. The success envelope (`{ success, data, meta }`)
  and error contract mirror `docs/engineering/05_API.md`.
- **Authentication** — Infrastructure is in place (auth context/provider, token
  storage abstraction, interceptors, `ProtectedRoute`, `RoleGuard`). The access
  token is held in memory and the refresh token in `localStorage`. The concrete
  login/register/refresh calls are intentionally **not** implemented in this
  sprint. Client-side role checks are **UX only**; real authorization is
  enforced server-side.
- **State management** — Server state via TanStack Query; a query-key factory
  lives in `src/lib/query-keys.ts`. Global client state is intentionally minimal
  (session + theme) — `store/` exists for future needs only.
- **Theming** — Light / Dark / System with a persisted preference
  (`ThemeProvider`), driven by CSS variables in `src/styles/globals.css`.
- **Error handling** — A top-level `ErrorBoundary`, a reusable `LoadingSpinner`,
  and a dedicated `NotFoundPage`.

---

## Routing

| Path          | Access               | Renders                          |
| ------------- | -------------------- | -------------------------------- |
| `/`           | —                    | Redirect → `/dashboard`          |
| `/login`      | Public               | `LoginPage` (placeholder)        |
| `/dashboard`  | Authenticated        | `DashboardPage` (placeholder)    |
| `/consumer`   | `CONSUMER`           | Consumer dashboard placeholder   |
| `/collector`  | `COLLECTOR`          | Collector dashboard placeholder  |
| `/recycler`   | `RECYCLER`           | Recycler dashboard placeholder   |
| `/government` | `GOVERNMENT`,`ADMIN` | Government dashboard placeholder |
| `/admin`      | `ADMIN`              | Admin dashboard placeholder      |
| `*`           | —                    | `NotFoundPage`                   |

All authenticated routes are wrapped by `ProtectedRoute` and the `MainLayout`
shell; role-specific routes are additionally fenced by `RoleGuard`.

---

## Quality Gates

Before committing, ensure all of the following pass:

```bash
npm run lint        # 0 errors, 0 warnings
npm run typecheck   # no type errors
npm run build       # production build succeeds
npm run format:check
```
