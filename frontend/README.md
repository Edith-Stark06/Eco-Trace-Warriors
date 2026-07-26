# EcoTrace India — Frontend

React web dashboard for the **EcoTrace India** e-waste lifecycle management platform (IEEE YESIST 2026).

> **Status:** Sprint 9.2 — Authentication & Session Management. The frontend
> foundation (Sprint 9.1) is complete, and a full login / logout / session
> lifecycle is now integrated with the backend auth API. Business dashboards
> remain placeholders.

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
│   │   ├── axios.ts        #   instance, request/response interceptors, refresh flow
│   │   ├── client.ts       #   envelope unwrap + error normalization helpers
│   │   ├── auth.api.ts     #   auth endpoint wrappers (login/refresh/logout/me)
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
- **Authentication** — A complete login / logout / session lifecycle wired to
  the backend auth API (`AuthProvider`, token storage abstraction, Axios
  interceptors, `ProtectedRoute`, `RoleGuard`). The server is the source of
  truth: the current user is always resolved via `GET /auth/me` and JWTs are
  **never** decoded on the client. Client-side role checks are **UX only**; real
  authorization is enforced server-side. See [Authentication](#authentication).
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
| `/login`      | Public               | `LoginPage` (login form)         |
| `/dashboard`  | Authenticated        | Redirect → role home             |
| `/consumer`   | `CONSUMER`           | Consumer dashboard placeholder   |
| `/collector`  | `COLLECTOR`          | Collector dashboard placeholder  |
| `/recycler`   | `RECYCLER`           | Recycler dashboard placeholder   |
| `/government` | `GOVERNMENT`,`ADMIN` | Government dashboard placeholder |
| `/admin`      | `ADMIN`              | Admin dashboard placeholder      |
| `*`           | —                    | `NotFoundPage`                   |

All authenticated routes are wrapped by `ProtectedRoute` and the `MainLayout`
shell; role-specific routes are additionally fenced by `RoleGuard`. After login,
`/dashboard` forwards each user to their role home (e.g. `ADMIN → /admin`).

---

## Authentication

The complete auth flow is integrated with the backend contract in
[`docs/engineering/05_API.md`](../docs/engineering/05_API.md).

### API methods (`src/api/auth.api.ts`)

| Method                   | Endpoint             | Returns                               |
| ------------------------ | -------------------- | ------------------------------------- |
| `authApi.login`          | `POST /auth/login`   | `{ user, accessToken, refreshToken }` |
| `authApi.refresh`        | `POST /auth/refresh` | `{ accessToken, refreshToken }`       |
| `authApi.logout`         | `POST /auth/logout`  | `{ loggedOut }`                       |
| `authApi.getCurrentUser` | `GET /auth/me`       | `PublicUser`                          |

All methods use the single shared Axios instance and unwrap the success
envelope (`response.data.data`).

### Login flow

```
Submit credentials → POST /auth/login → store access + refresh tokens
  → GET /auth/me (server confirms identity) → populate AuthContext
  → redirect to role home (or the originally requested page)
```

The login form uses React Hook Form + Zod for UX validation; the server
re-validates and remains the authority.

### Session bootstrap

On app start, `AuthProvider.bootstrapSession()` runs once:

```
Stored token? ── no ──▶ unauthenticated
     │ yes
     ▼
GET /auth/me ──ok──▶ populate user (authenticated)
     │ fail
     ▼
clear tokens + cache ──▶ unauthenticated (guards redirect to /login)
```

If only the refresh token survived a reload, the Axios interceptor transparently
refreshes the access token before `/auth/me` resolves.

### Token refresh (`401 → refresh → retry`)

The Axios response interceptor handles expired access tokens:

1. On `401`, call `POST /auth/refresh` with the stored refresh token.
2. Refresh tokens **rotate** — both tokens are replaced on success.
3. Retry the original request once with the new access token.
4. Concurrent `401`s share a **single in-flight** refresh (no stampede).
5. The retry flag and the refresh-endpoint skip prevent infinite loops.
6. If refresh fails, the session is cleared and an `unauthorized` event fires,
   so route guards redirect to `/login`.

### Logout

```
POST /auth/logout (best-effort; failures ignored)
  → clear tokens → clear React Query cache → redirect to /login
```

### Token storage strategy

`src/services/token.service.ts` is the single seam for token persistence:

| Token         | Location       | Rationale                                        |
| ------------- | -------------- | ------------------------------------------------ |
| Access token  | In-memory      | Minimizes XSS exposure; short-lived              |
| Refresh token | `localStorage` | Survives reloads; enables silent session restore |

The access token is intentionally **not** persisted; a full page reload relies
on the refresh token + `/auth/me` to restore the session. Swapping the strategy
(e.g. to secure cookies) touches only this one module.

---

## Quality Gates

Before committing, ensure all of the following pass:

```bash
npm run lint        # 0 errors, 0 warnings
npm run typecheck   # no type errors
npm run build       # production build succeeds
npm run format:check
```
