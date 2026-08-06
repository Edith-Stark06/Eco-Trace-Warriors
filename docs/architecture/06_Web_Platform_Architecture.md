# Web Platform Architecture

**Version:** 1.0.0  
**Status:** Active  
**Last Updated:** 2026-08-06

**Scope:** Web Platform only (React single-page application under `frontend/`)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Web Platform Overview](#2-web-platform-overview)
3. [Frontend Architecture](#3-frontend-architecture)
4. [Folder Structure](#4-folder-structure)
5. [Component Hierarchy](#5-component-hierarchy)
6. [Routing Architecture](#6-routing-architecture)
7. [Authentication Flow](#7-authentication-flow)
8. [Authorization Strategy](#8-authorization-strategy)
9. [Dashboard Architecture](#9-dashboard-architecture)
10. [State Management](#10-state-management)
11. [Custom Hooks](#11-custom-hooks)
12. [API Client Layer](#12-api-client-layer)
13. [UI Component Library](#13-ui-component-library)
14. [Form Architecture](#14-form-architecture)
15. [Validation Strategy](#15-validation-strategy)
16. [Error Handling](#16-error-handling)
17. [Notification System](#17-notification-system)
18. [Search & Pagination](#18-search--pagination)
19. [Layout System](#19-layout-system)
20. [Build Configuration](#20-build-configuration)
21. [Performance Strategy](#21-performance-strategy)
22. [Testing Strategy](#22-testing-strategy)
23. [Extension Points](#23-extension-points)
24. [Current Limitations](#24-current-limitations)
25. [Future Frontend Evolution](#25-future-frontend-evolution)
26. [Design Rationale](#26-design-rationale)

---

## 1. Executive Summary

The EcoTrace India **Web Platform** is a role-based single-page application (SPA) that serves as the human-facing control surface for the e-waste lifecycle platform. It is built with **React 19**, **TypeScript**, and **Vite 6**, and consumes the backend REST API documented in `docs/engineering/05_API.md`. Where the AI Platform ([02 — AI Platform Architecture]), Device Intelligence ([03 — Device Intelligence Architecture]), Decision Intelligence ([04 — Decision Intelligence Architecture]), and Blockchain ([05 — Blockchain Architecture]) layers are backend/service concerns, this document describes **only** the browser client.

The application delivers **five distinct role experiences** — Consumer, Collector, Recycler, Government, and Admin — from a single codebase, sharing one authentication system, one application shell, and one design system while code-splitting each role's screens into its own bundle.

**Key architectural properties:**

- **Feature-first organization** — role workflows live in self-contained slices under `src/features/`, each owning its pages, components, hooks, schemas, and display helpers.
- **Server as source of truth** — the client never decodes JWTs or recomputes authoritative values (rewards, trust scores); it renders what the backend returns and re-validates only for UX.
- **One API client** — every network call flows through a single Axios instance with a transparent `401 → refresh → retry` interceptor. UI code never calls `fetch`/`axios` directly.
- **Server-state vs UI-state separation** — TanStack Query owns all remote data (caching, invalidation, retry); React state/context owns only ephemeral UI concerns.
- **Layered guards** — `ProtectedRoute` gates authentication, `RoleGuard` gates role access, and role-filtered navigation ensures users never see links they cannot use. All client-side gating is UX-only; the server remains the authority.
- **Accessible, themable UI** — a shadcn/ui-style component library over Radix primitives, with light/dark/system theming driven by CSS custom properties.

The platform is **defensive by construction**: every remote call has explicit loading, empty, and error states; a top-level error boundary prevents blank-screen failures; and a "feature unavailable" path distinguishes an un-deployed backend module (HTTP 404) from a genuine server error.

---

## 2. Web Platform Overview

The Web Platform is one client of the EcoTrace backend. It has no direct knowledge of the AI, decision, or blockchain engines — it observes their *effects* through the REST contract (submission statuses, reward summaries, analytics figures) and never re-implements their logic.

**Technology baseline (from `frontend/package.json`):**

| Concern | Choice |
| --- | --- |
| UI runtime | React 19 (`react`, `react-dom`) |
| Language | TypeScript ~5.7 (strict, project-references build) |
| Build tool | Vite 6 (`@vitejs/plugin-react`) |
| Routing | React Router 7 (`react-router-dom`) |
| Server state | TanStack Query 5 (`@tanstack/react-query`) |
| HTTP | Axios 1.7 |
| Forms | React Hook Form 7 + `@hookform/resolvers` |
| Validation | Zod 3 |
| UI primitives | Radix UI (dialog, select, dropdown, tabs, tooltip, avatar, …) |
| Styling | Tailwind CSS v4 (`@tailwindcss/vite`) |
| Variants | class-variance-authority, `clsx`, `tailwind-merge` |
| Icons | lucide-react |
| Notifications | sonner |

**Node baseline:** `engines.node >= 20`; the package is ESM (`"type": "module"`).

**Role experiences delivered:**

- **Consumer** — register e-waste submissions, track their lifecycle, view GreenCoins rewards and history.
- **Collector** — work an assignment queue through the pickup transitions (accept → start → complete).
- **Recycler** — work an assignment queue through the recycling transitions (start → complete), recording material recovery.
- **Government** — a read-only oversight dashboard of national/regional analytics and AI demand forecasts.
- **Admin** — cross-cutting oversight: all submissions, collector/recycler assignment, and manual reward issuance.

Consistency with prior documents is maintained: role names and the submission lifecycle mirror the backend contract (`docs/engineering/04_DATABASE.md`, `05_API.md`), and reward/sustainability figures are treated as authoritative backend values exactly as described in [04 — Decision Intelligence Architecture].

---

## 3. Frontend Architecture

The application is a **feature-first SPA** organized by role workflow rather than by technical layer. The folder tree reflects user journeys, not framework concepts.

```
                 ┌──────────────────────────┐
                 │   Browser  (React 19)    │
                 └────────────┬─────────────┘
                              │
              ┌───────────────┴───────────────┐
              │   Application Root (App.tsx)  │
              │   - ErrorBoundary             │
              │   - ThemeProvider             │
              │   - QueryProvider (TanStack)  │
              │   - AuthProvider              │
              │   - AppRouter (React Router)  │
              └───────────────┬───────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ┌────▼────┐         ┌─────▼─────┐        ┌─────▼──────┐
   │  Public │         │ Protected │        │   Catch-   │
   │  Routes │         │  Routes   │        │   all 404  │
   │ (Login) │         │ (MainLayout)│       └────────────┘
   └─────────┘         └─────┬─────┘
                             │
                  ┌──────────┼──────────┐
                  │          │          │
            ┌─────▼────┐  ┌──▼────┐  ┌─▼────────┐
            │ Dashboard │  │ Role  │  │ Settings │
            │ Redirect  │  │ Guards│  │ (shared) │
            └───────────┘  └───┬───┘  └──────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
     ┌────▼────┐         ┌────▼────┐         ┌────▼────┐
     │Consumer │         │Collector│         │Recycler │
     │ Feature │         │ Feature │         │ Feature │
     └─────────┘         └─────────┘         └─────────┘
          │                    │                    │
     ┌────▼────┐         ┌────▼────┐         ┌────▼────┐
     │Government│        │  Admin  │         │         │
     │ Feature │         │ Feature │         │         │
     └──────────┘        └─────────┘         └─────────┘
```

**Overall Frontend Architecture Diagram**

**Key architectural patterns:**

1. **Provider composition** — The root `App.tsx` layers global providers in strict order: ErrorBoundary (outermost) → ThemeProvider → QueryProvider → AuthProvider → AppRouter, so each inner layer can depend on the outer ones.

2. **Lazy route code-splitting** — Every role's pages are `React.lazy(() => import('...'))` wrapped, so the consumer never downloads the admin bundle. The `MainLayout`'s `<Suspense>` boundary shows a shared `PageLoader` while chunks download.

3. **Layout isolation** — Public routes (login) render inside `AuthLayout` (centered card, no nav). Authenticated routes render inside `MainLayout` (navbar, sidebar, content well, footer). The layout dictates chrome; routes supply content via `<Outlet />`.

4. **Guard layering** — `ProtectedRoute` gates authentication (redirects to login if no session). Nested `RoleGuard` gates specific role access (shows `AccessDenied` if the user's role is not in the `allow` list). All client-side guards are UX-only; the server enforces real authorization.

5. **Central registries** — Routes (`src/lib/routes.ts`), navigation items (`src/lib/navigation.ts`), icons (`src/lib/icons.ts`), and query keys (`src/lib/query-keys.ts`) are centralized so scattered string literals never drift.

6. **Server-state externalized** — TanStack Query owns caching, invalidation, retry, and refetching; React `useState`/`useContext` own only local UI ephemera (dialog open state, pagination offset, search filter text). No remote data lives in React state.

**Technology choices grounded in the backend contract:**

- The five roles (CONSUMER, COLLECTOR, RECYCLER, GOVERNMENT, ADMIN) mirror the `UserRole` enum in `docs/engineering/04_DATABASE.md`.
- The nine-state submission lifecycle (PENDING, ASSIGNED, ACCEPTED, IN_PROGRESS, COLLECTED, RECYCLING, RECYCLED, COMPLETED, REJECTED) mirrors the `SubmissionStatus` enum in the backend Prisma schema.
- Reward figures (`greenCoins`, `totalRewards`, `co2Saved`, `energySaved`, `landfillDiverted`) mirror the `RewardBalance` and `RewardSustainability` DTOs from the backend rewards service, treated as authoritative and never recomputed client-side.

---

## 4. Folder Structure

The `frontend/src/` tree is organized so that shared infrastructure lives at the top level and role-specific workflows are isolated in feature slices.

```
frontend/
├── package.json              # deps, scripts (dev/build/lint/typecheck)
├── vite.config.ts            # Vite + React + Tailwind, '@' → ./src alias
└── src/
    ├── main.tsx              # React root; mounts <App/> in StrictMode
    ├── App.tsx               # Provider composition + router
    │
    ├── routes/               # Route table and guards
    │   ├── AppRouter.tsx     # <BrowserRouter> + <Routes> (lazy pages)
    │   ├── ProtectedRoute.tsx# auth gate
    │   └── RoleGuard.tsx     # role gate
    │
    ├── providers/            # React context providers
    │   ├── AuthProvider.tsx  # session state + actions
    │   ├── auth-context.ts   # AuthContext + AuthContextValue
    │   ├── QueryProvider.tsx # TanStack QueryClient
    │   ├── ThemeProvider.tsx # light/dark/system theming
    │   └── theme-context.ts  # ThemeContext + storage key
    │
    ├── hooks/                # cross-cutting hooks
    │   ├── use-auth.ts       # useAuth() context accessor
    │   └── use-theme.ts      # useTheme() context accessor
    │
    ├── layouts/              # route-level chrome
    │   ├── AuthLayout.tsx    # centered card (login)
    │   └── MainLayout.tsx    # navbar + sidebar + content + footer
    │
    ├── pages/                # top-level routed pages (non-feature)
    │   ├── DashboardPage.tsx # redirects to role home
    │   ├── LoginPage.tsx     # session-aware login route
    │   ├── SettingsPage.tsx  # shared settings
    │   └── NotFoundPage.tsx  # catch-all 404
    │
    ├── api/                  # typed API modules over one Axios instance
    │   ├── axios.ts          # the shared instance + interceptors
    │   ├── client.ts         # unwrap() + toApiError()
    │   ├── auth.api.ts        submission.api.ts  reward.api.ts
    │   ├── collector.api.ts   recycler.api.ts    government.api.ts
    │   ├── admin.api.ts       user.api.ts
    │   ├── not-implemented.ts# placeholder marker
    │   └── index.ts          # barrel re-exports
    │
    ├── services/             # framework-agnostic infrastructure
    │   ├── token.service.ts  # token storage abstraction
    │   └── session-events.ts # unauthorized event bus
    │
    ├── lib/                  # pure helpers & central registries
    │   ├── routes.ts         # ROUTES, ROLE_HOME, path builders
    │   ├── navigation.ts     # NAV_ITEMS + navItemsForRole()
    │   ├── icons.ts          # central Lucide icon registry
    │   ├── query-keys.ts     # TanStack query-key factory
    │   ├── breadcrumbs.ts    # pathname → breadcrumb trail
    │   ├── env.ts            # typed import.meta.env access
    │   └── utils.ts          # cn() class merger
    │
    ├── types/                # shared domain & contract types
    │   ├── api.ts            # ApiSuccess/ApiError envelope, pagination
    │   ├── auth.ts           # PublicUser, UserRole, AuthState
    │   ├── submission.ts     # Submission, lifecycle statuses, payloads
    │   ├── reward.ts         # RewardBalance, RewardSummary, history
    │   ├── analytics.ts      # government analytics DTOs
    │   └── index.ts          # barrel re-exports
    │
    ├── components/           # shared presentation
    │   ├── ui/               # shadcn/ui-style primitives over Radix
    │   ├── common/           # status screens, spinner, theme toggle
    │   ├── dashboard/        # StatCard, ContentCard, skeletons, empties
    │   └── layout/           # Navbar, Sidebar, breadcrumbs, user menu
    │
    ├── features/             # role-specific workflow slices
    │   ├── auth/             # login form + schema
    │   ├── consumer/         # submissions + rewards
    │   ├── collector/        # pickup assignment queue
    │   ├── recycler/         # recycling assignment queue
    │   ├── government/       # read-only analytics
    │   ├── admin/            # oversight + assignment + rewards
    │   └── shared/           # cross-role placeholder(s)
    │
    └── styles/
        └── globals.css       # Tailwind v4 import + design tokens
```

**Feature-slice anatomy.** Each feature under `src/features/<role>/` follows the same internal shape, so a developer who learns one learns all:

```
features/consumer/
├── ConsumerDashboardPage.tsx           # routed page (default export → lazy)
├── ConsumerSubmissionsPage.tsx
├── ConsumerSubmissionDetailsPage.tsx
├── ConsumerRewardsPage.tsx
├── components/                         # feature-local presentational parts
│   ├── SubmissionsTable.tsx
│   ├── SubmissionForm.tsx
│   ├── CreateSubmissionDialog.tsx  EditSubmissionDialog.tsx  ...
│   └── SubmissionStatusBadge.tsx  SubmissionTimeline.tsx  ...
├── hooks/                              # TanStack Query wrappers
│   ├── use-submissions.ts
│   └── use-rewards.ts
└── lib/                                # schemas + display helpers
    ├── submission-form.schema.ts       # Zod schema
    ├── submission-display.ts           # formatters/derivations
    └── reward-display.ts
```

**Rationale.** Feature-first colocation keeps a workflow's UI, data access, validation, and formatting in one place, so a change to (say) the consumer submission flow touches one directory. Shared infrastructure (API client, guards, UI primitives, registries) is deliberately hoisted to top-level directories so no feature owns it and all features reuse it — directly satisfying the CLAUDE.md principles of *reusable services* and *no duplicate logic*.

---

## 5. Component Hierarchy

The component tree mirrors the provider layering and route nesting established in §3.

```
<App>
  └─ ErrorBoundary
      └─ ThemeProvider (light/dark/system + CSS var application)
          └─ QueryProvider (TanStack QueryClient)
              └─ AuthProvider (session state + login/logout/refresh/bootstrap)
                  └─ AppRouter (BrowserRouter + Routes)
                      │
                      ├─ <Navigate to="/dashboard" />  (root → dashboard redirect)
                      │
                      ├─ AuthLayout (public)
                      │   └─ LoginPage
                      │       └─ LoginForm (react-hook-form + Zod)
                      │
                      ├─ ProtectedRoute (auth gate)
                      │   └─ MainLayout (Navbar + Sidebar + <Outlet /> + Footer)
                      │       ├─ DashboardPage (redirects to role home)
                      │       ├─ SettingsPage (shared, lazy)
                      │       │
                      │       └─ RoleGuard (role gate, per route group)
                      │           ├─ CONSUMER routes
                      │           │   ├─ ConsumerDashboardPage
                      │           │   ├─ ConsumerSubmissionsPage
                      │           │   │   ├─ SubmissionsTable
                      │           │   │   ├─ CreateSubmissionDialog
                      │           │   │   │   └─ SubmissionForm
                      │           │   │   └─ EditSubmissionDialog
                      │           │   │       └─ SubmissionForm (reused)
                      │           │   ├─ ConsumerSubmissionDetailsPage
                      │           │   └─ ConsumerRewardsPage
                      │           │
                      │           ├─ COLLECTOR routes
                      │           │   ├─ CollectorDashboardPage
                      │           │   │   └─ AssignmentsTable
                      │           │   └─ CollectorAssignmentDetailsPage
                      │           │
                      │           ├─ RECYCLER routes
                      │           │   ├─ RecyclerDashboardPage
                      │           │   │   └─ RecyclerAssignmentsTable
                      │           │   └─ RecyclerAssignmentDetailsPage
                      │           │       └─ CompleteRecyclingDialog
                      │           │
                      │           ├─ GOVERNMENT + ADMIN routes
                      │           │   └─ GovernmentDashboardPage
                      │           │       ├─ OverviewStats (StatCard grid)
                      │           │       ├─ EnvironmentalImpactStats
                      │           │       ├─ RegionalBreakdownTable
                      │           │       └─ ForecastTable
                      │           │
                      │           └─ ADMIN routes
                      │               └─ AdminDashboardPage
                      │                   ├─ AdminSubmissionsTable
                      │                   ├─ AssignCollectorDialog
                      │                   ├─ AssignRecyclerDialog
                      │                   └─ IssueRewardDialog
                      │
                      └─ NotFoundPage (catch-all 404)
```

**Component Hierarchy Diagram**

**Shared UI building blocks.** Every feature reuses the same primitives:

- **Status screens** — `StatusScreen` (base), `AccessDenied`, `NotFound`, `ServerError` (specialized with icon + code + action).
- **Dashboard chrome** — `DashboardHeader` (title + description + actions), `Section` (titled group), `ContentCard` (white box), `StatCard` (metric tile).
- **Loading states** — `LoadingSpinner`, `PageLoader`, `SectionLoader`, `SkeletonCards`, `SkeletonTable`.
- **Empty states** — `EmptyState` (icon + title + description + optional action).
- **Layout chrome** — `Navbar` (brand + breadcrumbs + notifications + theme + user menu), `Sidebar` (desktop nav rail), `MobileSidebar` (drawer toggle + `<Sheet>` overlay), `SidebarNav` (role-filtered link list, shared by desktop and mobile), `Breadcrumbs` (auto-generated from pathname), `UserMenu` (dropdown + logout), `Footer`.
- **UI primitives** — shadcn/ui-style wrappers over Radix: `Button`, `Input`, `Label`, `Textarea`, `Select`, `Dialog`, `Sheet`, `Table`, `Tabs`, `Tooltip`, `Avatar`, `Badge`, `Card`, `Separator`, `ScrollArea`, `Skeleton`, `Alert`, and their `*-variants.ts` cva companions. All use the `cn()` helper (`clsx` + `tailwind-merge`) for conditional class merging.

**Icon registry.** All Lucide icons are centralized in `src/lib/icons.ts` so `<Plus />` imports are replaced with `icons.plus`. Swapping an icon is a one-line edit.

**Lazy boundaries.** Every role's pages are `React.lazy(() => import('...'))` wrapped. The `MainLayout`'s `<Suspense fallback={<PageLoader />}>` shows a shared spinner while chunks download, so the shell never collapses.

---

## 6. Routing Architecture

Routing is centralized in `src/routes/AppRouter.tsx` with a single declarative route table. Every path literal is drawn from the `ROUTES` registry in `src/lib/routes.ts`, so no route string is duplicated across the app.

```
                        REQUEST: any URL
                              │
                     ┌────────▼────────┐
                     │  <BrowserRouter>│
                     │    <Routes>     │
                     └────────┬────────┘
                              │
          ┌───────────────────┼───────────────────────┐
          │                   │                       │
      path "/"           element AuthLayout        catch-all "*"
          │                   │                       │
   <Navigate to             LoginPage             NotFoundPage
    "/dashboard"                                  (StatusScreen 404)
    replace />
                              │
                   ┌──────────▼───────────┐
                   │   <ProtectedRoute>   │  ← auth gate
                   │  isLoading? spinner  │
                   │  !auth?    → /login  │  (preserves `from`)
                   │  auth?     <Outlet/> │
                   └──────────┬───────────┘
                              │
                   ┌──────────▼───────────┐
                   │     <MainLayout>     │  ← app shell + Suspense
                   └──────────┬───────────┘
                              │
        ┌─────────────┬───────┼────────┬──────────────┐
        │             │       │        │              │
   /dashboard     /settings   │   RoleGuard groups    │
   (redirect)     (shared)    │   (per-role fences)   │
                              │
   ┌──────────────────────────┼───────────────────────────┐
   │ allow=[CONSUMER]         │ allow=[COLLECTOR]          │
   │  /consumer               │  /collector                │
   │  /consumer/submissions   │  /collector/submissions/:id│
   │  /consumer/submissions/:id                            │
   │  /consumer/rewards       │ allow=[RECYCLER]           │
   │                          │  /recycler                 │
   │ allow=[GOVERNMENT,ADMIN] │  /recycler/submissions/:id │
   │  /government             │                            │
   │                          │ allow=[ADMIN]              │
   │                          │  /admin                    │
   └──────────────────────────┴────────────────────────────┘
```

**Routing Flow Diagram**

**Route table structure (from `AppRouter.tsx`):**

1. **Root redirect** — `/` → `<Navigate to="/dashboard" replace />`.
2. **Public group** — wrapped in `AuthLayout`; currently only `/login`.
3. **Authenticated group** — wrapped in `ProtectedRoute` then `MainLayout`:
   - Shared: `/dashboard` (role-home redirect) and `/settings`.
   - Role-fenced groups via nested `<RoleGuard allow={[...]} />`:
     - Consumer: dashboard, submissions list, submission detail (`:id`), rewards.
     - Collector: dashboard, assignment detail (`:id`).
     - Recycler: dashboard, assignment detail (`:id`).
     - Government: dashboard (shared with ADMIN via `allow={['GOVERNMENT','ADMIN']}`).
     - Admin: dashboard.
4. **Catch-all** — `path="*"` → `NotFoundPage`.

**The `ROUTES` registry** (`src/lib/routes.ts`) is a frozen `as const` object plus:

- `ROLE_HOME: Record<UserRole, string>` — maps each role to its landing route.
- `roleHome(role)` — resolves post-login destination, falling back to `/dashboard`.
- Path builders — `consumerSubmissionPath(id)`, `collectorAssignmentPath(id)`, `recyclerAssignmentPath(id)` — construct parameterized detail URLs from a single source of truth.

**Navigation model.** The sidebar/drawer are driven by a separate declarative list, `NAV_ITEMS` in `src/lib/navigation.ts`. Each item names an icon (from the central registry) and optionally the `roles` allowed to see it; `navItemsForRole(role)` filters the list. Items with no `roles` (Dashboard, Settings) are visible to everyone. This role filtering is **UX-only** — it hides links a user cannot use; the actual authorization is enforced server-side, and defensively re-checked by `RoleGuard`.

---

## 7. Authentication Flow

Authentication is owned by `AuthProvider` (`src/providers/AuthProvider.tsx`), which wraps the entire app and exposes session state plus four async actions: `login`, `logout`, `refreshSession`, and `bootstrapSession`. The provider is mounted **above** the router, so it never navigates directly — it exposes reactive state; route guards handle redirects.

```
                    ┌────────────────────────┐
                    │  User visits any URL   │
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │   AuthProvider mounts  │
                    │   calls bootstrapSession()│
                    │   on first render      │
                    └───────────┬────────────┘
                                │
                ┌───────────────┴───────────────┐
                │                               │
       No tokens stored?                  Tokens exist?
                │                               │
       status='unauthenticated'        Call GET /auth/me
       skip network                    (interceptor refreshes if needed)
                │                               │
                │                       ┌───────┴────────┐
                │                       │                │
                │                    Success?         Fail?
                │                       │                │
                │              store user,       clear tokens,
                │              status='authenticated'  status='unauthenticated'
                │                       │                │
                └───────────────────────┴────────────────┘
                                │
                    ┌───────────▼────────────┐
                    │  ProtectedRoute reads  │
                    │  isAuthenticated       │
                    └───────────┬────────────┘
                                │
                ┌───────────────┴───────────────┐
                │                               │
         isLoading=true?                 isAuthenticated?
                │                               │
         <LoadingSpinner />              <Outlet /> (render route)
                                                │
                                         !isAuthenticated?
                                                │
                                    <Navigate to="/login" state={{ from }} />


                    ┌────────────────────────┐
                    │  User submits login    │
                    │  form (email+password) │
                    └───────────┬────────────┘
                                │
                    POST /auth/login (via authApi.login)
                                │
                        ┌───────┴────────┐
                        │                │
                    Success?          Fail?
                        │                │
                 store tokens      show error (toast + inline)
                        │
                    GET /auth/me (confirm session)
                        │
                 setUser(currentUser)
                 status='authenticated'
                        │
                 navigate(from ?? ROUTES.dashboard)
                        │
                 POST /auth/logout (revoke refresh token, best-effort)
                        │
                 clear tokens + state
                 status='unauthenticated'
                        │
                 ProtectedRoute redirects → /login
```

**Authentication Flow Diagram**

**Token storage.** Access token lives in memory (`tokenStorage.ts`); refresh token is persisted in `localStorage` under `ecotrace.refreshToken`. The access token is **not** persisted, so a full page reload clears it — but `bootstrapSession` uses the surviving refresh token to silently restore the session via the interceptor's transparent refresh.

**Transparent refresh-and-retry.** The Axios response interceptor (`src/api/axios.ts`) implements a single-flight `401 → POST /auth/refresh → retry original request` flow:

1. On any HTTP 401, if the request is **not** flagged `skipAuthRefresh` and has **not** already been retried (`_retry`), the interceptor calls `requestRefresh()`.
2. `requestRefresh()` is a single-flight promise: if multiple requests concurrently hit 401, they all await the same shared `POST /auth/refresh` call.
3. On success, both tokens are rotated (refresh tokens rotate per the backend contract), the new access token is injected into the original request's `Authorization` header, and the request is retried **once**.
4. On failure (no refresh token, or the refresh endpoint itself returned 401), `tokenStorage.clear()` is called and `sessionEvents.emit('unauthorized')` fires.
5. The `AuthProvider` subscribes to the `'unauthorized'` event and reacts by clearing `user` + `status`, which causes `ProtectedRoute` to redirect to login on the next render.

**Why a custom event bus?** The Axios interceptor is low-level infrastructure; it cannot import React, the router, or the auth provider without creating a circular dependency. The `sessionEvents` module (`src/services/session-events.ts`) is a tiny framework-agnostic emitter that lets infrastructure signal lifecycle events upward without coupling.

**Server is source of truth.** The current user is **always** resolved via `GET /auth/me` after login and on bootstrap. The client **never** decodes the JWT; the token is opaque. Role gating and authorization remain server-side; the client's role checks are UX-only (hiding links, showing `AccessDenied`).

---

## 8. Authorization Strategy

Authorization on the client is a **defense-in-depth UX layer**, never a security boundary. The backend is the sole authority (as established in [02 — AI Platform Architecture] and the API contract). The frontend applies three cooperating, non-authoritative gates:

**1. Navigation filtering (visibility).** `navItemsForRole(role)` filters `NAV_ITEMS` so a user only sees links they are permitted to use. A CONSUMER never sees the Admin link; a COLLECTOR never sees the Government link. This is purely to avoid presenting dead ends.

**2. Route guarding (access).** `RoleGuard` wraps each role-specific route group with an `allow: UserRole[]` list:

```
RoleGuard states:
  isLoading   → <LoadingSpinner fullScreen />         (session resolving)
  authorized  → <Outlet />                            (user.role ∈ allow)
  unauthorized→ <AccessDenied homePath={roleHome()} />(rendered inside shell)
```

Crucially, `AccessDenied` is rendered **inside** the `MainLayout` shell (navbar + sidebar remain), so a user who lands on a forbidden route keeps working navigation and a link back to their role home — never a dead end.

**3. Action gating (capability).** Individual actions are hidden when the backend would reject them, mirroring server rules so the user is never offered an impossible action:

- Consumer Edit/Delete buttons appear **only** for `PENDING` submissions (`isSubmissionMutable(status)`), mirroring the backend rule that submissions are mutable only while pending.
- Collector transition buttons expose only the legal next step for the current status (accept → start → complete).
- Recycler transition buttons expose only start → complete.
- Reward issuance and assignment actions appear only within the Admin feature.

**Role → home mapping** (`ROLE_HOME` in `routes.ts`) ensures every role has a sensible landing page, and `roleHome(role)` is the single resolver used by `DashboardPage`, `LoginPage`, and `AccessDenied`.

**Consistency note.** This mirrors the layered raise-vs-report and least-privilege posture described in the backend layers: the UI *reports* what is permitted (hides/disables), while the server *enforces* it (rejects). A malicious user who manually navigates to `/admin` gets `AccessDenied` client-side and, even if that were bypassed, a 403 server-side.

---

## 9. Dashboard Architecture

Each role has a dedicated, code-split dashboard. All dashboards share the same compositional primitives (`DashboardHeader`, `Section`, `ContentCard`, `StatCard`, `EmptyState`, skeleton loaders) so they look and behave consistently while presenting role-specific data.

```
                    ┌───────────────────────────┐
                    │      Role dashboards      │
                    │  (shared primitives, per- │
                    │   role data + actions)    │
                    └─────────────┬─────────────┘
          ┌──────────┬────────────┼────────────┬──────────┐
          │          │            │            │          │
    ┌─────▼───┐ ┌───▼────┐  ┌────▼─────┐ ┌───▼─────┐ ┌──▼────┐
    │Consumer │ │Collector│  │Recycler  │ │Governmnt│ │ Admin │
    ├─────────┤ ├─────────┤  ├──────────┤ ├─────────┤ ├───────┤
    │ Submissions│ Assignment│ Assignment│ Overview  │ All subs│
    │  create   │  queue    │  queue    │  stats    │ (read)  │
    │  edit     │  accept→  │  start→   │ Impact    │ Assign  │
    │  delete   │  start→   │  complete │  stats    │ collector│
    │  timeline │  complete │ (+material│ Regional  │ Assign  │
    │ Rewards   │           │  recovery)│  table    │ recycler│
    │  balance  │           │ +reward   │ Forecast  │ Issue   │
    │  history  │           │  dialog   │  table    │ reward  │
    └───────────┘ └─────────┘ └──────────┘ └─────────┘ └───────┘
        │             │            │            │          │
    WRITE (own)   WRITE (own    WRITE (own   READ-ONLY  WRITE (all,
                  assignments)  assignments) (observer) admin scope)
```

**Dashboard Relationships Diagram**

**Consumer dashboard** — The most feature-rich role. `ConsumerSubmissionsPage` lists the user's own submissions with client-side search, status filter, and pagination (see §18). `CreateSubmissionDialog`/`EditSubmissionDialog` host the shared `SubmissionForm`; `DeleteSubmissionDialog` confirms removal. `ConsumerSubmissionDetailsPage` shows a read-only `SubmissionTimeline` of lifecycle stages. `ConsumerRewardsPage` renders GreenCoins balance and transaction history — display-only, since rewards are issued server-side.

**Collector dashboard** — `CollectorDashboardPage` renders the assignment queue (`AssignmentsTable`) with a `StatusSummary`. Each row's `AssignmentActionButton` exposes only the legal next transition. `CollectorAssignmentDetailsPage` shows one assignment's detail.

**Recycler dashboard** — Symmetric to the collector: `RecyclerDashboardPage` + `RecyclerAssignmentsTable` + `RecyclerStatusSummary`. Completion opens `CompleteRecyclingDialog` (records recovered weight + optional per-material recovery), and on success shows `RewardSuccessDialog` with the **backend-issued** reward values (never recomputed).

**Government dashboard** — Read-only observer view. `GovernmentDashboardPage` fetches four analytics endpoints (overview, environmental impact, regions, forecast). It has **no write actions**. It distinguishes an un-deployed Analytics module (HTTP 404 → `AnalyticsUnavailable` informational state) from a genuine error (retryable `ServerError`), and shows per-section states via `AnalyticsSection`. Because the backend Analytics module is documented but not yet deployed, the DTOs in `types/analytics.ts` are explicitly typed-but-provisional — no data is fabricated.

**Admin dashboard** — `AdminDashboardPage` renders all submissions across every user (admin-scoped `GET /submissions`), with dialogs to assign collectors (`AssignCollectorDialog`), assign recyclers (`AssignRecyclerDialog`), and issue rewards manually (`IssueRewardDialog`). `AdminUnavailable` covers absent backend surfaces gracefully.

**Common contract.** Every dashboard section follows the same lifecycle discipline: **loading** (skeleton) → **error** (retryable) → **empty** (informational `EmptyState`) → **data** (table/cards). No section ever renders a blank region while data resolves.

---

## 10. State Management

The application draws a hard line between **server state** and **UI state**, assigning each to a purpose-built owner.

**Server state → TanStack Query.** All remote data — submissions, rewards, assignments, analytics, the current user — is owned by TanStack Query. It handles caching, background refetching, deduplication, retry, and invalidation. Components never store fetched data in `useState`; they subscribe to a query and re-render when the cache changes.

The `QueryClient` is created once per provider instance (via `useState(createQueryClient)`) so it is stable across re-renders. Default options (`src/providers/QueryProvider.tsx`):

```
queries:   staleTime 60_000ms, gcTime 5min, retry 1, refetchOnWindowFocus false
mutations: retry 0
```

**UI state → React state/context.** Only ephemeral, view-local concerns use `useState`/`useReducer`: dialog open/closed, current pagination page, search text, status filter selection, form field state (via React Hook Form). None of this is remote data.

**Global cross-cutting state → Context.** Two long-lived concerns are contexts:

- **Auth** — `AuthContext` (`providers/auth-context.ts`) exposes `AuthState` + actions, consumed via `useAuth()`. The provider owns all session network work.
- **Theme** — `ThemeContext` (`providers/theme-context.ts`) exposes `theme`, `resolvedTheme`, `setTheme`, consumed via `useTheme()`.

Both contexts throw a descriptive error if consumed outside their provider — a fail-fast guard against mis-wiring.

**Query-key factory.** All cache keys come from a single factory in `src/lib/query-keys.ts`, structured hierarchically so mutations can invalidate precisely:

```
queryKeys.auth.me
queryKeys.submissions.all | .list(params) | .detail(id)
queryKeys.rewards.all | .balance | .history(params)
queryKeys.collector.all | .assignments(params)
queryKeys.recycler.all | .assignments(params)
queryKeys.government.overview | .regions | .environmentalImpact | .forecast
queryKeys.admin.all | .submissions(params) | .collectors | .recyclers
queryKeys.user.profile
```

**Invalidation discipline.** Mutations never manually refetch — they invalidate the relevant top-level key (e.g. `queryKeys.submissions.all`, `queryKeys.collector.all`) and let Query refetch whatever is currently observed. This keeps the "what changed" logic in one place and avoids stale reads. Collector/recycler transitions invalidate the whole queue key because a status change can add or remove a row from the active queue.

---

## 11. Custom Hooks

Two categories of hooks exist: **context accessors** (top-level `src/hooks/`) and **feature data hooks** (per-feature `hooks/`).

**Context accessors:**

| Hook | Purpose |
| --- | --- |
| `useAuth()` | Access session state + `login`/`logout`/`refreshSession`/`bootstrapSession`. Throws outside `AuthProvider`. |
| `useTheme()` | Access `theme`/`resolvedTheme`/`setTheme`. Throws outside `ThemeProvider`. |

**Feature data hooks** — thin TanStack Query wrappers that colocate cache keys, query functions, and invalidation with the feature:

| Feature | Hooks | Kind |
| --- | --- | --- |
| Consumer submissions | `useSubmissions`, `useSubmission`, `useCreateSubmission`, `useUpdateSubmission`, `useDeleteSubmission` | query + mutations |
| Consumer rewards | `useRewardBalance`, `useRewardHistory` | queries (read-only) |
| Collector | `useCollectorAssignments`, `useAcceptAssignment`, `useStartPickup`, `useCompletePickup` | query + mutations |
| Recycler | `useRecyclerAssignments`, `useStartRecycling`, `useCompleteRecycling` | query + mutations |
| Government | `useGovernmentOverview`, `useGovernmentRegions`, `useGovernmentEnvironmentalImpact`, `useGovernmentForecast` | queries (read-only) |
| Admin | `useAdminSubmissions`, `useCollectors`, `useRecyclers`, `useIssueReward`, `useAssignCollector`, `useAssignRecycler` | query + mutations |

**Consistent conventions across data hooks:**

- Query hooks read their key from `queryKeys.*` and call the matching typed API module.
- Detail queries use `enabled: Boolean(id)` so they don't fire until an id is available (`useSubmission`).
- Mutation hooks capture `useQueryClient()` and invalidate the relevant top-level key in `onSuccess`.
- Government hooks share a custom `analyticsRetry` policy: a 404 (module not deployed) is **not** retried (it's an expected "unavailable" state); other transient failures retry up to twice. This keeps the informational empty state instant while still being resilient to blips.
- Collector/recycler features factor their shared invalidation into a small internal hook (`useInvalidate*Assignments`) reused by every transition mutation — no duplicated invalidation logic.

**Rationale.** Colocating data access with the feature (rather than a monolithic `hooks/` folder) means a workflow's cache strategy lives next to its UI, satisfying the feature-first principle while keeping the query-key factory the single source of cache identity.

---

## 12. API Client Layer

All network calls flow through a single Axios instance (`src/api/axios.ts`) with typed domain-specific modules built atop it. UI code never calls `fetch` or `axios` directly.

```
          ┌───────────────────────────────────────┐
          │  React Components / Feature Hooks     │
          └────────────────┬──────────────────────┘
                           │
          ┌────────────────▼──────────────────────┐
          │   Typed API Modules (domain facades)  │
          │  authApi  submissionApi  rewardApi    │
          │  collectorApi  recyclerApi  adminApi  │
          │  governmentApi  userApi               │
          └────────────────┬──────────────────────┘
                           │
          ┌────────────────▼──────────────────────┐
          │   unwrap() helper (extract data)      │
          │   response.data.data → TData          │
          └────────────────┬──────────────────────┘
                           │
          ┌────────────────▼──────────────────────┐
          │   Single Axios Instance (apiClient)   │
          │   - Base URL from env                 │
          │   - Request interceptor (bearer token)│
          │   - Response interceptor (401→refresh)│
          └────────────────┬──────────────────────┘
                           │
          ┌────────────────▼──────────────────────┐
          │         Backend REST API              │
          │    (documented in 05_API.md)          │
          └───────────────────────────────────────┘
```

**API Communication Diagram**

**Shared Axios instance** (`src/api/axios.ts`) — created once with:

- `baseURL`: `import.meta.env.VITE_API_BASE_URL` (default `http://localhost:3000/api/v1`), read from `src/lib/env.ts`.
- `timeout`: `import.meta.env.VITE_API_TIMEOUT` (default 15000ms).
- `headers`: `Content-Type: application/json`.

**Request interceptor** — injects the bearer token from `tokenStorage.getAccessToken()` into every outgoing request's `Authorization` header when a token exists.

**Response interceptor** — implements the transparent `401 → refresh → retry` flow described in §7. A 401 triggers a single-flight `POST /auth/refresh`, which rotates both tokens; the original request is retried once with the new access token. On refresh failure or when no refresh token exists, `tokenStorage.clear()` is called and `sessionEvents.emit('unauthorized')` fires, which the `AuthProvider` subscribes to.

**Typed API modules** — each exports an object with methods that call the shared instance and unwrap the backend's success envelope. Every method is strongly typed to the backend contract DTOs (`src/types/`):

| Module | Methods | Notes |
| --- | --- | --- |
| `authApi` | `login`, `refresh`, `logout`, `getCurrentUser` | `refresh` flagged `skipAuthRefresh` to prevent infinite recursion. |
| `submissionApi` | `list`, `getById`, `create`, `update`, `remove` | Consumer CRUD only; no transition endpoints. |
| `collectorApi` | `getAssignments`, `acceptAssignment`, `startPickup`, `completePickup` | Collector workflow transitions. |
| `recyclerApi` | `getAssignments`, `startRecycling`, `completeRecycling` | Recycler workflow + material recovery. Returns `{ submission, reward }` on complete. |
| `rewardApi` | `getBalance`, `getHistory` | Consumer reads only; rewards issued server-side. |
| `governmentApi` | `getOverview`, `getRegions`, `getEnvironmentalImpact`, `getForecast` | Read-only analytics. |
| `adminApi` | `listAllSubmissions`, `issueReward`, `listUsersByRole`, `assignCollector`, `assignRecycler` | Admin-scoped write operations. |
| `userApi` | `getProfile`, `updateProfile` | Placeholder (`notImplemented`) in current sprint. |

**Helper utilities** (`src/api/client.ts`):

- `unwrap<TData>(promise)` — extracts `response.data.data` so callers get the resource directly, never the envelope.
- `toApiError(error)` — normalizes any thrown error into the backend's `ApiErrorBody` shape for consistent UI error handling. Recognizes Axios errors, network/timeout errors (`ECONNABORTED` → `TIMEOUT`), and unknown errors.

**The `notImplemented` marker** (`src/api/not-implemented.ts`) — a function that throws a clear, traceable error for methods scaffolded but not yet implemented (Sprint 9.1 is infrastructure-only). It prevents silent failures and makes incompleteness explicit.

**Rationale.** One Axios instance = one interceptor configuration, one base URL, one timeout, and one retry strategy. Typed modules keep the backend contract explicit; UI code gets auto-complete and compile-time errors when the contract drifts. The `unwrap` abstraction means components never manually navigate `.data.data`, and `toApiError` ensures every failure renders a friendly, actionable message — directly satisfying the *defensive* principle from the Executive Summary.

---

## 13. UI Component Library

The design system is a **shadcn/ui-style** local component library: hand-owned wrappers over headless Radix UI primitives, styled with Tailwind and variant-managed by class-variance-authority (cva). The components live in the repo (not `node_modules`), so they are fully customizable.

**Primitive inventory** (`src/components/ui/`):

| Component | Radix primitive | Variants file |
| --- | --- | --- |
| `Button` | `@radix-ui/react-slot` (asChild) | `button-variants.ts` |
| `Badge` | — | `badge-variants.ts` |
| `Alert` | — | `alert-variants.ts` |
| `Sheet` | `@radix-ui/react-dialog` | `sheet-variants.ts` |
| `Dialog` | `@radix-ui/react-dialog` | — |
| `DropdownMenu` | `@radix-ui/react-dropdown-menu` | — |
| `Select` | `@radix-ui/react-select` | — |
| `Tabs` | `@radix-ui/react-tabs` | — |
| `Tooltip` | `@radix-ui/react-tooltip` | — |
| `Avatar` | `@radix-ui/react-avatar` | — |
| `ScrollArea` | `@radix-ui/react-scroll-area` | — |
| `Separator` | `@radix-ui/react-separator` | — |
| `Input`, `Label`, `Textarea`, `Card`, `Table`, `Skeleton` | native + Tailwind | — |

**The cva + separate-variants pattern.** Style variants are defined in a sibling `*-variants.ts` file, not the component file. For example, `button-variants.ts` exports `buttonVariants = cva(base, { variants: { variant: {...}, size: {...} }, defaultVariants })`, and `button.tsx` imports it. This split exists so the component module exports *only* components — satisfying the `react-refresh/only-export-components` ESLint rule (fast-refresh safety). The `Button` uses Radix `Slot` to support `asChild`, letting it render as a `<Link>` while keeping button styling (used throughout tables for "View" links).

**The `cn()` helper** (`src/lib/utils.ts`) — the standard shadcn merger: `twMerge(clsx(inputs))`. `clsx` resolves conditional classes; `tailwind-merge` de-duplicates conflicting Tailwind utilities (so a later `px-8` wins over an earlier `px-4`). Every primitive threads `className` through `cn()`.

**Dashboard primitives** (`src/components/dashboard/`) — presentation-only building blocks with no data fetching:

- `StatCard` — metric tile (label + pre-formatted string value + optional icon + hint). Callers pass already-computed values (e.g. `"—"` or `"12.5 kg"`); the card never formats or fetches.
- `ContentCard` — bordered content well. `Section` — titled group. `DashboardHeader` — title + description + actions slot. `EmptyState` — icon + title + description + optional action.
- `PageLoader`, `SectionLoader`, `SkeletonCards`, `SkeletonTable` — loading placeholders matching the shape of the content they replace.

**Common/status components** (`src/components/common/`):

- `StatusScreen` — the shared base for full-page status screens (business-logic-free): optional code, icon, title, description, action, and `fullScreen` toggle.
- `AccessDenied`, `NotFound`, `ServerError` — specialize `StatusScreen` with the right icon/code/action, so the three never duplicate markup.
- `LoadingSpinner` — inline or `fullScreen` spinner with optional label. `ThemeToggle` — light/dark/system switcher.

**Rationale.** Owning the primitives (vs. importing a component kit) keeps full control over styling and accessibility while avoiding heavy dependencies. The `StatusScreen`/`StatCard`/`EmptyState` trio ensures every screen's loading, empty, and error states are visually consistent and DRY.

---

## 14. Form Architecture

Forms use **React Hook Form** for state/submission and **Zod** for validation, wired together via `@hookform/resolvers/zod`. Two representative forms establish the pattern: `LoginForm` (simple) and `SubmissionForm` (complex, reused for create + edit).

**Standard form anatomy:**

```
useForm<FormValues>({
  resolver: zodResolver(schema),
  defaultValues: {...},
})
   │
   ├─ register('field')          → uncontrolled input binding
   ├─ handleSubmit(onValid)      → validate then run handler
   ├─ formState.errors           → per-field messages (inline)
   └─ formState.isSubmitting     → disable inputs during submit
```

**Accessibility as a first-class concern.** Every field wires:

- `<Label htmlFor="id">` associated with its input.
- `aria-invalid={errors.field ? true : undefined}` on the input.
- `aria-describedby` pointing at the error `<p id="field-error">` when present.
- Inputs `disabled` while `isSubmitting`.
- A submit button showing a spinner + "Signing in…"/busy label while pending.

This directly satisfies the CLAUDE.md rule that generated UI must be accessibility-compliant.

**Reusable `SubmissionForm`** — used by both `CreateSubmissionDialog` and `EditSubmissionDialog`. Notable techniques:

- **Numeric-as-text fields.** `estimatedWeight`, `latitude`, `longitude` are modeled as strings (native inputs yield strings) and coerced to numbers on submit. This makes an empty field show a friendly "required" message instead of a confusing "expected number" error.
- **Dynamic field array.** `imageUrls` uses `useFieldArray` for an add/remove list of URL strings (the backend accepts URLs, not file uploads — an explicit contract fact reflected in the UI copy).
- **Payload coercion on submit.** The handler trims strings, converts numeric text to `Number`, maps the field-array objects to plain strings, and omits an empty optional `description` — producing exactly the backend-ready `CreateSubmissionPayload`.
- **Create/edit reuse.** The same form serves both flows; edit mode passes `defaultValues`, create mode starts blank (`EMPTY_VALUES`). The hosting dialog owns open state and the mutation.

**Dialog + mutation + toast pattern.** `CreateSubmissionDialog` illustrates the canonical write flow: it owns `open` state and the `useCreateSubmission` mutation; on success it toasts, closes, and lets React Query invalidation refresh lists (no manual refetch); on error it toasts `toApiError(error).message`.

---

## 15. Validation Strategy

Validation is **two-tier by design**: the client validates for UX responsiveness, and the server re-validates as the authority. The client schemas are deliberately kept in sync with the backend schemas so the client rejects exactly what the server would — no request is sent that the backend will refuse.

**Client schemas** (Zod, colocated with their forms):

- `auth.schema.ts` — `loginSchema`: trimmed non-empty valid email + non-empty password. Deliberately minimal — password *strength* rules belong to registration, not login.
- `submission-form.schema.ts` — `submissionFormSchema`, mirroring the backend `createSubmissionSchema`: category (2–100 chars), optional description (≤2000), positive numeric weight, address (3–500 chars), latitude (−90…90), longitude (−180…180), and up to 20 valid image URLs. A shared `numericField(label)` helper produces friendly "required"/"must be a number" messages.
- `complete-recycling.schema.ts` — the recycler completion form (recovered weight + optional notes + optional per-material recovery map).

**Design choices grounded in the code:**

1. **Schemas mirror the backend contract**, with comments pointing at the exact backend schema file — so drift is visible and intentional.
2. **`zodResolver` bridges** Zod schemas into React Hook Form, so validation runs on submit and per-field messages render inline.
3. **Client validation is explicitly UX-only.** Every schema file documents that the server re-validates and is the authority. The client never trusts its own validation as a security control.
4. **Type inference.** `type FormValues = z.infer<typeof schema>` derives the TypeScript form type from the schema, so schema and types never diverge.

**Consistency note.** This "validate for UX, enforce server-side" split mirrors the raise-vs-report asymmetry in the backend engines ([03], [04], [05]): the client *reports* likely-invalid input early and cheaply; the server *rejects* authoritatively. Neither the trust score nor the reward is ever recomputed on the client — the frontend validates *inputs*, never *verdicts*.

---

## 16. Error Handling

Error handling is layered so that no failure ever produces a blank screen or an unhandled crash. Four cooperating mechanisms cover the full surface:

**1. Top-level error boundary.** `ErrorBoundary` (`src/components/common/ErrorBoundary.tsx`) is the outermost wrapper in `App.tsx`. A React class component (boundaries require lifecycle), it catches render-time errors anywhere in the tree, logs them (with a TODO to forward to observability), and shows a recoverable `ServerError` fallback with a **retry** that resets its state — never a white screen.

**2. Normalized API errors.** `toApiError(error)` collapses any thrown value into the backend's `ApiErrorBody` shape (`{ code, message, details? }`). It recognizes Axios errors (extracting `response.data.error`), network failures (`NETWORK_ERROR`), timeouts (`ECONNABORTED` → `TIMEOUT`), and unknown errors (`UNKNOWN_ERROR`). Every UI error path can therefore rely on a `code` + friendly `message`.

**3. Per-query error states.** Every data-driven section renders an explicit error branch. The canonical pattern (from `ConsumerSubmissionsPage`) is:

```
isPending  → <SkeletonTable />         (loading)
isError    → <ServerError onRetry={refetch} />  (retryable failure)
empty      → <EmptyState ... />        (no data / no matches)
data       → <Table ... />             (success)
```

**4. "Feature unavailable" vs. "server error".** The Government dashboard distinguishes an *expected* absence from a *genuine* failure. `isAnalyticsUnavailable(error)` classifies an HTTP 404 as "the Analytics module isn't deployed on this backend instance" and renders a calm `AnalyticsUnavailable` informational state; any other error surfaces the retryable `ServerError`. The `analyticsRetry` policy also skips retrying a 404 (it won't spontaneously appear) while retrying transient failures. This prevents an un-shipped backend module from looking like a broken app.

**Form-level error mapping.** `LoginForm.messageForError(code, fallback)` maps backend error codes (`INVALID_CREDENTIALS`, `ACCOUNT_DEACTIVATED`, `NETWORK_ERROR`, `TIMEOUT`) to friendly, display-safe copy — shown both as a toast and an inline `role="alert"` banner.

**Rationale.** Defense-in-depth error handling means a failure is caught at the nearest sensible layer: a bad field at the form, a failed request at the query section, a 404 as an informational state, and a catastrophic render error at the boundary. The app is, by construction, *never a dead end* — the guiding principle from `docs/engineering/07_FRONTEND.md`.

---

## 17. Notification System

Transient user feedback uses **sonner** (`Toaster`), mounted once in `App.tsx` alongside the router:

```
<Toaster richColors closeButton position="top-right" />
```

**Usage pattern.** Feature code imports `toast` from `sonner` and fires:

- `toast.success('Submission created.')` — after a successful mutation.
- `toast.error(toApiError(error).message)` — on a failed mutation, using the normalized error message.

**Where toasts fire.** Write operations (create/edit/delete submission, login, workflow transitions, assignment, reward issuance) toast on both success and failure. Read operations do **not** toast — they render inline loading/empty/error states instead, so passive data fetching never spams notifications.

**Login's dual feedback.** The login form shows *both* a toast and a persistent inline alert on error — the toast for immediate attention, the inline banner so the reason stays visible while the user corrects their input.

**Configuration rationale.** `richColors` gives semantic success/error coloring; `closeButton` lets users dismiss; `top-right` keeps toasts clear of primary actions and the mobile drawer toggle. Mounting the `Toaster` inside `AuthProvider` (but as a sibling of the router) means any authenticated screen can toast without prop-drilling.

**A specialized "reward" surface.** Beyond transient toasts, the recycler completion flow shows a dedicated `RewardSuccessDialog` presenting the backend-issued reward (GreenCoins + sustainability figures). This is a modal — not a toast — because the reward is a meaningful outcome worth dwelling on, and every figure is an authoritative backend value, never recomputed on the client.

---

## 18. Search & Pagination

The submissions list demonstrates the platform's **client-side** search + filter + pagination strategy, chosen deliberately for datasets scoped to a single user.

**`ConsumerSubmissionsPage` implementation:**

- **Data fetched once** via `useSubmissions()` (React Query), then filtered and paged **in memory**. Because the list is one user's own submissions, this is cheap and avoids extra round-trips.
- **Search** — a debounce-free controlled `<Input type="search">` matched case-insensitively against category and address.
- **Status filter** — a Radix `<Select>` over `SUBMISSION_STATUSES` plus an `ALL` sentinel.
- **Sort** — newest-first via `sortByNewest(data)` from the feature's display lib.
- **Pagination** — fixed `PAGE_SIZE = 10`; `useMemo` derives the filtered set, then `slice()` produces the current page. Previous/Next buttons are disabled at the boundaries, and the page auto-resets to 1 whenever a filter changes the result set.
- **Live region** — `aria-live="polite"` on the "Showing X of Y" summary announces result changes to assistive tech.

**Server-side pagination is contract-ready.** The API layer already supports offset-based pagination: `PaginationParams { limit?, offset? }` (`types/api.ts`), an `ApiMeta { page, pageSize, total }` envelope field, and every list API method accepts `params`. The query-key factory threads `params` into list keys (`submissions.list(params)`, `collector.assignments(params)`, …), so switching a large list to server-driven pagination is a localized change — pass `params`, read `meta`, and drop the in-memory slice.

**Rationale.** Client-side paging is the right call for small, user-scoped lists (fewer round-trips, instant filtering). The infrastructure for server-side paging is already in place for lists that will grow unbounded (admin's all-submissions view), so the migration path is clear and non-breaking.

---

## 19. Layout System

Two route-level layouts and a set of shared chrome components compose the application's visual frame.

**`AuthLayout`** — a minimal centered card for unauthenticated pages (login). Brand mark + centered `<Outlet />`, no navigation. Deliberately free of business chrome.

**`MainLayout`** — the shell for every authenticated role:

```
┌────────────────────────────────────────────────────────┐
│ Navbar (sticky, h-14, full width)                       │
│  [☰ mobile] [🌿 brand] [breadcrumbs]  [🔔][theme][user] │
├──────────┬─────────────────────────────────────────────┤
│ Sidebar  │  Main content (scrolls independently)        │
│ (md+ rail│   <Suspense fallback={PageLoader}>           │
│  drawer  │      <Outlet />   ← lazy role pages          │
│  on sm)  │   </Suspense>                                │
│          │                                              │
│ [nav     ├──────────────────────────────────────────────┤
│  links]  │  Footer                                       │
│ [logout] │                                              │
└──────────┴─────────────────────────────────────────────┘
```

**Responsive navigation.** The `Sidebar` is a fixed rail shown from the `md` breakpoint up; below `md` it is hidden and `MobileSidebar` (a `<Sheet>` drawer toggled from the navbar) takes over. Both render the same `SidebarNav`, so desktop and mobile navigation can never drift. `SidebarNav` role-filters links via `navItemsForRole(user?.role)` and highlights the active route with `NavLink`'s `isActive`.

**Auto-generated breadcrumbs.** `Breadcrumbs` derives its trail from the current pathname via `buildBreadcrumbs()` (`src/lib/breadcrumbs.ts`) — always rooted at Dashboard, with each segment labeled from a known-segment map or title-cased as a fallback. New routes need no breadcrumb wiring.

**Theming.** `ThemeProvider` applies light/dark/system by toggling the `.dark` class on `<html>`, which switches the CSS custom properties defined in `globals.css`. Preference persists in `localStorage` (`ecotrace.theme`) and `system` mode reacts live to OS changes via `matchMedia`.

**Design tokens.** `globals.css` is Tailwind v4 (`@import 'tailwindcss'`) with a `@custom-variant dark`. Design tokens are OKLCH CSS variables defined once for `:root` and overridden under `.dark`, then exposed to Tailwind via `@theme inline` (`--color-background`, `--color-primary`, …). Components reference semantic utilities (`bg-background`, `text-muted-foreground`, `border-input`) — never raw hex — so the entire palette (a green primary at `oklch(0.6 0.16 150)`) is swappable in one file.

**Page navigation model.** The diagram below traces how a user moves through the app once authenticated:

```
                    ┌─────────────┐
                    │   /login    │
                    └──────┬──────┘
                           │ successful sign-in
                           ▼
                    ┌─────────────┐
                    │ /dashboard  │  (DashboardPage: redirect only)
                    └──────┬──────┘
                           │ roleHome(user.role)
        ┌──────────┬───────┼────────┬─────────────┐
        ▼          ▼       ▼        ▼             ▼
   /consumer  /collector /recycler /government  /admin
        │          │        │
        │          │        └─► /recycler/submissions/:id ─► CompleteRecyclingDialog
        │          │                                         └─► RewardSuccessDialog
        │          └─► /collector/submissions/:id
        │
        ├─► /consumer/submissions ─► /consumer/submissions/:id (timeline)
        │        │
        │        └─► CreateSubmissionDialog / EditSubmissionDialog
        │
        └─► /consumer/rewards (balance + history)

   Shared from anywhere (via sidebar):  /settings
   Any unknown path:                    NotFoundPage (catch-all "*")
   Any forbidden path:                  AccessDenied (inside shell)
   Session lost (401 unrecoverable):    → /login (guards redirect)
```

**Page Navigation Diagram**

---

## 20. Build Configuration

The build is **Vite 6** with the React and Tailwind plugins.

**`vite.config.ts`:**

- `plugins: [react(), tailwindcss()]` — React Fast Refresh + Tailwind v4's Vite integration.
- `resolve.alias`: `'@' → ./src` — the `@/...` import prefix used throughout (matched by TypeScript path mapping so editor and bundler agree).
- `server: { port: 5173, host: true }` — dev server on 5173, exposed on the network (`host: true`) for device testing.

**NPM scripts (`package.json`):**

| Script | Command | Purpose |
| --- | --- | --- |
| `dev` | `vite` | Dev server with HMR. |
| `build` | `tsc -b && vite build` | Type-check (project references) **then** bundle — a type error fails the build. |
| `preview` | `vite preview` | Serve the production build locally. |
| `lint` / `lint:fix` | `eslint .` | Lint (with autofix variant). |
| `format` / `format:check` | `prettier` | Formatting. |
| `typecheck` | `tsc -b --noEmit` | Standalone type-check. |

**Toolchain baseline:** TypeScript ~5.7 (project-reference build, `tsc -b`), ESLint 9 flat config with `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, and `eslint-config-prettier`; Prettier 3. Node ≥ 20, ESM package.

**Environment variables** are read exclusively through `src/lib/env.ts`, which centralizes every `import.meta.env.VITE_*` access behind a typed `env` object with sensible fallbacks (`apiBaseUrl`, `apiTimeout`, `appName`, `appVersion`, `isDev`, `isProd`). No component touches raw env strings — satisfying the CLAUDE.md "no hardcoded values" rule and keeping secrets/config out of the component tree. Only `VITE_`-prefixed variables are exposed to the client by Vite, so server secrets never reach the bundle.

**Rationale.** Coupling `tsc -b` into `build` guarantees the deployed artifact is type-clean. The `@` alias keeps imports absolute and refactor-safe. Centralized `env` is the single seam for configuration, mirroring the backend's environment-driven configuration discipline.

---

## 21. Performance Strategy

Performance is addressed at build, network, and render layers:

**Bundle splitting.** Every role's pages are `React.lazy`-loaded, so the initial bundle carries only the shell, auth, and the redirect logic. A consumer never downloads admin/government/recycler code. Each lazy chunk loads on demand behind the `MainLayout` `<Suspense>` boundary with a `PageLoader` fallback. Login and the dashboard redirect stay eager (entry points, negligible weight).

**Server-state caching.** TanStack Query caches query results with a 60s `staleTime` and 5min `gcTime`, so revisiting a screen within the window renders instantly from cache with a background refetch only when stale. `refetchOnWindowFocus` is disabled to avoid refetch storms on tab switching. Retry is 1 for queries, 0 for mutations (mutations should surface failures immediately, not silently retry a write).

**Precise invalidation.** Mutations invalidate only the affected key subtree (e.g. `submissions.all`), so unrelated cached data is untouched and only observed queries refetch. This minimizes network traffic after writes.

**In-memory list operations.** User-scoped lists filter/sort/paginate in memory (`useMemo`), avoiding a round-trip per keystroke or page change.

**Render efficiency.** `useMemo`/`useCallback` stabilize derived data and callbacks in hot components (auth context value, filtered lists). The `QueryClient` and theme/auth context values are memoized so provider re-renders don't cascade.

**CSS-variable theming.** Theme switching toggles a single `.dark` class rather than re-mounting a styled tree, so light/dark transitions are instant and allocation-free.

**Current posture.** No route-level prefetching, image optimization pipeline, or virtualized lists are implemented yet (see §24) — appropriate for the current data volumes, with clear upgrade paths noted in §25.

---

## 22. Testing Strategy

**Current state.** The frontend package does **not** yet include a test runner or test files in its dependency set (`package.json` declares no Vitest/Jest/Testing Library, and there are no `*.test.tsx` files in `src/`). Testing is presently enforced through **static guarantees** rather than runtime suites:

- **Type safety** — `tsc -b` runs as part of `build`, so the deployed artifact is type-clean against the backend contract DTOs.
- **Linting** — ESLint 9 (flat config) with `react-hooks` (exhaustive-deps, rules-of-hooks) and `react-refresh` rules catches a class of runtime bugs statically. The `*-variants.ts` split exists specifically to satisfy `react-refresh/only-export-components`.
- **Formatting** — Prettier enforces consistency (`format:check`).

**Architecture is test-ready.** The codebase is structured for straightforward future testing:

- **Pure helpers** (`lib/breadcrumbs.ts`, `lib/routes.ts` path builders, `lib/navigation.ts` filtering, `features/*/lib/*-display.ts` formatters, Zod schemas) are side-effect-free and unit-testable in isolation.
- **API modules** are thin and mockable (one Axios instance to intercept).
- **Data hooks** wrap TanStack Query and can be tested with a `QueryClientProvider` wrapper.
- **Presentational components** (StatCard, tables, status screens) take plain props with no data fetching, so they render deterministically under a component test.

**Recommended future stack** (see §25): Vitest + React Testing Library for units/components, MSW to mock the API contract, and Playwright for role-based end-to-end journeys — aligning with the CLAUDE.md testing policy (unit, integration, e2e where practical).

---

## 23. Extension Points

The architecture is deliberately open for extension without modification of existing code:

**Add a new role experience.** Create `src/features/<role>/` following the standard slice shape (pages + `components/` + `hooks/` + `lib/`), add its routes to `ROUTES`, add a `<RoleGuard allow={[...]}>` group in `AppRouter`, add `NAV_ITEMS` entries with the role, add a `ROLE_HOME` mapping, and register the role in the `USER_ROLES` tuple. No existing feature changes.

**Add a new API surface.** Create a typed module in `src/api/`, export it from `api/index.ts`, add its DTOs to `src/types/`, add a query-key namespace to `query-keys.ts`, and write feature hooks. The shared Axios instance (auth, refresh, error normalization) is inherited automatically.

**Add a UI primitive.** Drop a shadcn/ui-style wrapper in `components/ui/` (with a `*-variants.ts` companion if it needs variants). It gains `cn()` merging and the theme tokens for free.

**Swap token storage.** `tokenStorage` is an interface (`TokenStorage`); moving the access token from memory to a worker, or the refresh token to an httpOnly cookie flow, is a single-file change with no call-site impact.

**Add session lifecycle events.** The `sessionEvents` bus currently emits only `unauthorized`; new events (e.g. `token-refreshed`, `session-expiring`) extend the `SessionEvent` union without coupling infrastructure to React.

**Enable server-side pagination.** The `PaginationParams`/`ApiMeta` plumbing and params-aware query keys are already in place; a growing list migrates by passing `params` and reading `meta` (§18).

**Wire the notification button.** `NotificationButton` is a placeholder ready to bind to a notifications API + badge count.

**Add observability.** `ErrorBoundary.componentDidCatch` has a marked TODO to forward errors to a monitoring service — a single integration point.

---

## 24. Current Limitations

Stated honestly, grounded in the implementation:

1. **No automated tests.** No test runner, unit, component, or e2e tests exist yet (§22). Correctness rests on TypeScript + ESLint.
2. **Placeholder API methods.** `userApi.getProfile`/`updateProfile` throw `notImplemented` — the profile/settings write path is scaffolded, not functional.
3. **Provisional analytics contract.** The backend Analytics module is not deployed; `types/analytics.ts` DTOs are inferred from one-line endpoint descriptions and will need reconciliation when the module ships. The UI already handles the 404-unavailable case gracefully.
4. **Access token lost on hard reload.** By design (XSS mitigation) the access token is memory-only; a reload silently re-derives it from the persisted refresh token, but if that refresh fails the user must re-login.
5. **Client-side-only pagination in use.** The consumer list pages in memory; large admin lists will need the (already-plumbed) server-side path.
6. **No charts/maps.** The government dashboard renders analytics as tables; latitude/longitude are typed but no map/chart library is bundled.
7. **No route prefetching or list virtualization.** Acceptable at current data volumes.
8. **No i18n.** UI copy is inline English despite the "India" context; no localization layer exists yet.
9. **No optimistic updates.** Mutations invalidate-and-refetch rather than optimistically updating the cache — simpler and correct, but with a brief post-write latency.
10. **Refresh token in `localStorage`.** A documented, deliberate trade-off (survives reload) pending a future httpOnly-cookie flow.

---

## 25. Future Frontend Evolution

A pragmatic roadmap that builds on the existing seams:

**Near term:**
- **Testing suite** — Vitest + React Testing Library + MSW (contract mocks) + Playwright (role-based e2e journeys), targeting the pure helpers, hooks, and forms first.
- **Complete the profile/settings path** — implement `userApi` and wire `SettingsPage` to real reads/writes.
- **Observability** — forward `ErrorBoundary` catches and unhandled rejections to a monitoring service.
- **Notifications** — bind `NotificationButton` to a notifications endpoint with an unread badge.

**Medium term:**
- **Server-driven pagination/filtering** for the admin all-submissions view using the existing `PaginationParams`/`ApiMeta` plumbing.
- **Optimistic updates** for high-frequency transitions (collector/recycler queues) to remove post-write latency.
- **Analytics visualization** — introduce a charting/mapping library once the backend Analytics module ships and DTOs are finalized; render the regional lat/long as a heatmap.
- **Reconcile analytics DTOs** against the real backend module response shapes.

**Longer term:**
- **Harden auth storage** — move the refresh token to an httpOnly cookie + CSRF flow, eliminating `localStorage` exposure.
- **Internationalization** — introduce an i18n layer for multi-language support appropriate to the Indian market.
- **PWA/offline** — service-worker caching for field users (collectors/recyclers) with intermittent connectivity.
- **Route prefetching + list virtualization** as data volumes grow.
- **Blockchain provenance views** — surface the tamper-evident lifecycle chains from [05 — Blockchain Architecture] in a read-only audit UI once those endpoints are exposed.

Every item above extends the current architecture through its existing extension points (§23) without rewriting the foundation.

---

## 26. Design Rationale

This section explains *why* the Web Platform is built the way it is, tying the decisions back to the whole-system principles in Documents 01–05 and CLAUDE.md.

**Why feature-first, not layer-first?** Organizing by role workflow (`features/consumer/`, `features/collector/`, …) keeps a change to one journey inside one directory, and lets each role's screens code-split cleanly. Shared infrastructure is hoisted to top-level directories so no feature owns it — the CLAUDE.md tension between *modularity* and *no duplication* is resolved by colocating what changes together and centralizing what is reused.

**Why "server as source of truth"?** The client never decodes JWTs, never recomputes trust scores or reward figures, and always confirms the user via `GET /auth/me`. This mirrors the backend's authority model: the AI, decision, and blockchain layers ([03], [04], [05]) *produce* verdicts; the frontend only *displays* them. Recomputing any authoritative value on the client would risk divergence from the ledgered truth.

**Why one Axios instance with an interceptor?** Centralizing auth-token injection, the single-flight `401 → refresh → retry`, and error normalization in one place means every one of the 30-plus API methods inherits correct, consistent behavior. The event-bus decoupling (`sessionEvents`) keeps low-level HTTP infrastructure free of React/router imports — the same clean dependency direction the backend enforces (infrastructure never depends on domain).

**Why TanStack Query for all server state?** Remote data has caching, staleness, retry, and invalidation concerns that `useState` handles poorly. Externalizing it removes an entire class of bugs (stale reads, duplicate fetches, manual refetch orchestration) and makes the invalidate-don't-refetch discipline uniform.

**Why UX-only client authorization?** Route guards and nav filtering exist to avoid dead ends and hide impossible actions — improving usability — but are never trusted as security. The server enforces every rule. This is the frontend expression of the least-privilege, never-trust-the-client posture from CLAUDE.md's security section.

**Why the two-tier validation split?** Zod schemas mirror the backend schemas so invalid input is caught early and cheaply, but the client explicitly documents that the server re-validates and is authoritative. The user gets instant feedback; the system stays correct.

**Why owned shadcn/ui primitives over a component kit?** Owning the primitives gives full control over accessibility and theming with minimal dependencies, and the `cn()` + cva + CSS-variable-token stack makes the entire look-and-feel swappable from `globals.css` — no hardcoded colors scattered through components.

**Why defense-in-depth error handling?** Every remote interaction has explicit loading/empty/error states, a 404 is distinguished from a failure, and a top-level boundary catches the rest. The product is, by construction, *never a dead end* — the guiding usability principle for the platform.

Together these choices make the Web Platform a maintainable, scalable, secure client that faithfully renders the authoritative state produced by the rest of the EcoTrace India system — advancing the project's goal of a production-ready IEEE YESIST 2026 prototype.

---

*This document was reverse-engineered from the frontend implementation under `frontend/` and reflects the code as the single source of truth. It describes only the Web Platform; the AI, decision, blockchain, database, deployment, and security-implementation layers are covered by Documents 01–05 and the engineering documentation under `docs/engineering/`.*
