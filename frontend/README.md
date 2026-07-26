# EcoTrace India — Frontend

React web dashboard for the **EcoTrace India** e-waste lifecycle management platform (IEEE YESIST 2026).

> **Status:** Sprint 9.7 — Government Dashboard (analytics & oversight).
> Building on the foundation (9.1), authentication (9.2), the shared dashboard
> framework (9.3), the Consumer module (9.4), the Collector module (9.5), and the
> Recycler module (9.6), the **Government** role now has a production-ready,
> read-only oversight dashboard wired to the documented `/analytics/*` contract.
> Government users are **observers** — they monitor national statistics,
> environmental impact, regional breakdowns, and AI demand forecasts, and perform
> **no** write operations. The backend Analytics module is not yet deployed on
> this instance, so the endpoints currently return 404; the dashboard treats this
> as an expected "feature unavailable" condition and shows a dedicated
> informational state, then populates automatically once the module ships. The
> remaining role dashboard (**Admin**) still renders **placeholder content** — its
> business features arrive in a later sprint.

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

| Variable            | Description                       | Default                        |
| ------------------- | --------------------------------- | ------------------------------ |
| `VITE_API_BASE_URL` | Base URL of the backend API       | `http://localhost:3000/api/v1` |
| `VITE_API_TIMEOUT`  | Request timeout in milliseconds   | `15000`                        |
| `VITE_APP_NAME`     | Display name of the application   | `EcoTrace India`               |
| `VITE_APP_VERSION`  | Version label shown in the footer | `0.1.0`                        |

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
│   │   ├── common/         # ErrorBoundary, LoadingSpinner, ThemeToggle, status/error screens
│   │   ├── dashboard/      # Reusable dashboard containers (headers, cards, loaders)
│   │   ├── forms/          # Reusable form controls (later sprints)
│   │   ├── layout/         # Navbar, Sidebar, MobileSidebar, Breadcrumbs, Footer, UserMenu
│   │   └── ui/             # shadcn/ui primitives (Button, Card, Dialog, Sheet, ...)
│   ├── features/           # Feature/role modules (auth, consumer, …, shared placeholder)
│   ├── hooks/              # Shared hooks (useAuth, useTheme)
│   ├── layouts/            # MainLayout (app shell), AuthLayout (centered)
│   ├── lib/                # utils, env, routes, query-keys, icons, navigation, breadcrumbs
│   ├── pages/              # Top-level routed pages (Login, Dashboard, Settings, NotFound)
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
- **Dashboard shell** — Every authenticated role shares one reusable
  application shell (navbar + responsive sidebar + footer) and a library of
  business-logic-free dashboard components. Content pages are lazy-loaded. See
  [Dashboard Framework](#dashboard-framework).
- **Theming** — Light / Dark / System with a persisted preference
  (`ThemeProvider`), driven by CSS variables in `src/styles/globals.css`.
- **Error handling** — A top-level `ErrorBoundary` (backed by `ServerError`), a
  reusable `LoadingSpinner`, and reusable `AccessDenied` / `NotFound` screens.

---

## Routing

| Path                         | Access               | Renders                          |
| ---------------------------- | -------------------- | -------------------------------- |
| `/`                          | —                    | Redirect → `/dashboard`          |
| `/login`                     | Public               | `LoginPage` (login form)         |
| `/dashboard`                 | Authenticated        | Redirect → role home             |
| `/settings`                  | Authenticated        | Settings placeholder (all roles) |
| `/consumer`                  | `CONSUMER`           | Consumer dashboard (live data)   |
| `/consumer/submissions`      | `CONSUMER`           | Submissions list                 |
| `/consumer/submissions/:id`  | `CONSUMER`           | Submission details + timeline    |
| `/consumer/rewards`          | `CONSUMER`           | Rewards summary + history        |
| `/collector`                 | `COLLECTOR`          | Collector dashboard (live data)  |
| `/collector/submissions/:id` | `COLLECTOR`          | Assignment details + timeline    |
| `/recycler`                  | `RECYCLER`           | Recycler dashboard (live data)   |
| `/recycler/submissions/:id`  | `RECYCLER`           | Recycling details + timeline     |
| `/government`                | `GOVERNMENT`,`ADMIN` | Government dashboard (read-only) |
| `/admin`                     | `ADMIN`              | Admin dashboard placeholder      |
| `*`                          | —                    | `NotFoundPage`                   |

All authenticated routes are wrapped by `ProtectedRoute` and the `MainLayout`
shell; role-specific routes are additionally fenced by `RoleGuard`. After login,
`/dashboard` forwards each user to their role home (e.g. `ADMIN → /admin`). A
user who reaches a route their role may not view sees the reusable
`AccessDenied` screen **inside** the shell (so navigation stays available)
rather than a silent redirect. All content pages are lazy-loaded
(see [Dashboard Framework](#dashboard-framework)).

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

## Dashboard Framework

Every authenticated role shares one reusable application shell and a common set
of dashboard building blocks. This sprint delivers the framework only — role
dashboards render placeholder content.

### Layout hierarchy

```
MainLayout (h-screen, fixed shell)
├── Navbar (sticky)
│     ├── MobileSidebar toggle (drawer, < md only)
│     ├── Brand logo → /dashboard
│     ├── Breadcrumbs (auto-generated from the path)
│     └── NotificationButton · ThemeToggle · UserMenu
├── Sidebar (fixed rail, md+ only — role-filtered nav + logout)
└── scroll container
      ├── <main> → <Suspense fallback={<PageLoader/>}> Outlet </Suspense>
      └── Footer (app name · year · version)
```

The navbar spans the full width; below it a fixed sidebar and an independently
scrolling content column sit side by side, with the footer pinned under the
content. The shell is role-agnostic — the only thing that changes per role is
which navigation links appear.

### Responsive behavior

| Breakpoint               | Navigation                          | Layout notes                               |
| ------------------------ | ----------------------------------- | ------------------------------------------ |
| Mobile (`<md`)           | Hamburger → slide-in drawer (Sheet) | Sidebar hidden; brand text hidden on `<sm` |
| Tablet / Desktop (`md+`) | Fixed sidebar rail                  | Breadcrumbs and full brand shown           |

Layouts use Tailwind responsive utilities and fluid widths (no fixed pixel
page widths). Content grids collapse from multi-column to single-column on
small screens.

### Navigation & breadcrumbs

- **`src/lib/navigation.ts`** is the single source of truth for sidebar links.
  Each item declares an icon and optional `roles`; `navItemsForRole()` filters
  the list so **only permitted destinations are ever rendered** (UX-only —
  the server still enforces authorization). The desktop sidebar and mobile
  drawer both render the shared `SidebarNav`, so they never drift.
- **`src/lib/breadcrumbs.ts`** derives the trail from the current pathname
  (`buildBreadcrumbs`). New routes need no per-page wiring; unknown segments are
  title-cased automatically.

### Shared components

Reusable, business-logic-free building blocks:

| Group      | Components                                                                              |
| ---------- | --------------------------------------------------------------------------------------- |
| Containers | `DashboardHeader`, `PageTitle`, `PageDescription`, `Section`, `ContentCard`, `StatCard` |
| Empty/data | `EmptyState`                                                                            |
| Loading    | `PageLoader`, `SectionLoader`, `SkeletonCards`, `SkeletonTable`                         |
| Errors     | `AccessDenied` (403), `NotFound` (404), `ServerError` (500) via `StatusScreen`          |

These live in `src/components/dashboard/` (containers/loaders) and
`src/components/common/` (error/status screens). `AccessDenied` backs
`RoleGuard`, `NotFound` backs `NotFoundPage`, and `ServerError` is the
top-level `ErrorBoundary` fallback — so the reusable screens are the real
implementations, not copies.

### UI primitives (shadcn/ui)

The shared design system was expanded with new-york-style primitives in
`src/components/ui/`: `card`, `badge`, `avatar`, `dropdown-menu`, `separator`,
`skeleton`, `tabs`, `dialog`, `sheet`, `alert`, `textarea`, `select`, `table`,
`scroll-area`, and `tooltip` (joining the existing `button`, `input`, `label`).
Radix packages back the interactive ones; `cva` variant maps are split into
`*-variants.ts` files so component modules only export components (satisfies
`react-refresh/only-export-components`).

### Icons

All Lucide icons are re-exported from a central registry,
**`src/lib/icons.ts`**. Components import `{ icons }` and reference an icon by
key (`icons.dashboard`) instead of importing from `lucide-react` directly, so
swapping an icon is a one-line change.

### Route lazy loading

All content pages (the five role dashboards and Settings) are loaded with
`React.lazy` and split into their own chunks; the `MainLayout` `<Suspense>`
boundary shows the shared `PageLoader` skeleton while a chunk downloads. The
login page and the `/dashboard` redirect stay eager as entry points.

---

## Consumer Module

The Consumer role is the first module wired to **real backend data** — no mocks,
no fixtures. Everything lives under `src/features/consumer/` and reuses the
shared API layer, dashboard framework, and UI primitives.

### Pages

| Page                            | Route                       | Contents                                                                 |
| ------------------------------- | --------------------------- | ------------------------------------------------------------------------ |
| `ConsumerDashboardPage`         | `/consumer`                 | Welcome header, reward summary, 5 most-recent submissions, quick actions |
| `ConsumerSubmissionsPage`       | `/consumer/submissions`     | Full list with search, status filter, and pagination                     |
| `ConsumerSubmissionDetailsPage` | `/consumer/submissions/:id` | Full record, image URLs, and a read-only lifecycle timeline              |
| `ConsumerRewardsPage`           | `/consumer/rewards`         | Reward summary card + reward-history table                               |

### API integration

The module talks only to the endpoints below (see
[`docs/engineering/05_API.md`](../docs/engineering/05_API.md)). Each wrapper uses
the single shared Axios instance and unwraps the success envelope
(`response.data.data`).

| Method                  | Endpoint                  | Purpose                             |
| ----------------------- | ------------------------- | ----------------------------------- |
| `submissionApi.list`    | `GET /submissions`        | The caller's own submissions        |
| `submissionApi.getById` | `GET /submissions/:id`    | A single submission                 |
| `submissionApi.create`  | `POST /submissions`       | Create a submission                 |
| `submissionApi.update`  | `PATCH /submissions/:id`  | Edit a submission (while PENDING)   |
| `submissionApi.remove`  | `DELETE /submissions/:id` | Delete a submission (while PENDING) |
| `rewardApi.getBalance`  | `GET /rewards/balance`    | GreenCoins + lifetime impact        |
| `rewardApi.getHistory`  | `GET /rewards/history`    | Reward transactions                 |

Server state is managed with TanStack Query hooks
(`useSubmissions`, `useSubmission`, `useRewardBalance`, `useRewardHistory`,
`useCreateSubmission`, `useUpdateSubmission`, `useDeleteSubmission`). Mutations
never refetch manually — they invalidate the shared query keys
(`submissions.*`, `rewards.*`) and let Query refresh what is observed.

### Submission flow

```
Create (dialog) ─▶ POST /submissions ─▶ invalidate submissions ─▶ lists refresh
Edit   (dialog) ─▶ PATCH /submissions/:id ─▶ invalidate detail + lists
Delete (confirm) ─▶ DELETE /submissions/:id ─▶ invalidate lists (navigate away from detail)
```

- The **submission form** (create + edit) uses React Hook Form + Zod, mirroring
  the backend `createSubmissionSchema` so the client rejects exactly what the
  server would.
- **Images are URLs, not uploads.** The form provides a dynamic _Add / Remove
  image URL_ list; each URL is validated. There is no multipart upload.
- **Edit and Delete are offered only while a submission is `PENDING`** — once a
  collector is assigned the backend rejects modification, so the UI hides those
  actions and shows _"This submission can no longer be modified."_ The user is
  never offered an action the server would reject.
- The **lifecycle timeline** renders the recycling path
  `PENDING → ASSIGNED → ACCEPTED → IN_PROGRESS → COLLECTED → RECYCLING → RECYCLED`
  and highlights the current stage. It is read-only; consumers do not drive
  status transitions.

### Reward flow

Rewards are issued **server-side** when a submission is recycled — the client
only reads them. `GET /rewards/balance` powers the summary tiles (Green Coins,
Total Rewards, CO₂ Saved, Energy Saved, Landfill Diverted) and
`GET /rewards/history` powers the history table (points, reason, submission
category/status, date).

### Reuse

The module adds **no** new empty-state, loader, or error screens. It reuses
`EmptyState`, `PageLoader` / `SectionLoader` / `SkeletonCards` / `SkeletonTable`,
and `ServerError` / `NotFound` / `AccessDenied` from the shared framework, plus
the shared `Table`, `Badge`, `Dialog`, `Select`, and dashboard container
components.

---

## Collector Module

The Collector role is the first **operational workflow** — a collector reads the
pickups assigned to them and advances each through the recycling lifecycle
against the real backend. Everything lives under `src/features/collector/` and
reuses the shared API layer, dashboard framework, and UI primitives. Assignment
itself is an Admin/Government concern and is intentionally not built here.

### Pages

| Page                             | Route                        | Contents                                                          |
| -------------------------------- | ---------------------------- | ----------------------------------------------------------------- |
| `CollectorDashboardPage`         | `/collector`                 | Status summary, active assignments, today's work, quick actions   |
| `CollectorAssignmentDetailsPage` | `/collector/submissions/:id` | Full record, images, coordinates, and a read-only pickup timeline |

### API integration

The module talks only to the endpoints below (see
[`docs/engineering/05_API.md`](../docs/engineering/05_API.md)). Each wrapper uses
the single shared Axios instance and unwraps the success envelope
(`response.data.data`).

| Method                          | Endpoint                          | Purpose                                       |
| ------------------------------- | --------------------------------- | --------------------------------------------- |
| `collectorApi.getAssignments`   | `GET /collector/submissions`      | The collector's active assignment queue       |
| `collectorApi.acceptAssignment` | `PATCH /submissions/:id/accept`   | Accept an assignment (ASSIGNED → ACCEPTED)    |
| `collectorApi.startPickup`      | `PATCH /submissions/:id/start`    | Start the pickup (ACCEPTED → IN_PROGRESS)     |
| `collectorApi.completePickup`   | `PATCH /submissions/:id/complete` | Complete the pickup (IN_PROGRESS → COLLECTED) |

Server state is managed with TanStack Query hooks (`useCollectorAssignments`,
`useAcceptAssignment`, `useStartPickup`, `useCompletePickup`). Mutations never
refetch manually — they invalidate the shared `collector.*` query keys and let
Query refresh what is observed.

### Assignment lifecycle

The backend `GET /collector/submissions` returns only the collector's **active**
queue — submissions in `ASSIGNED`, `ACCEPTED`, or `IN_PROGRESS`. Each status
maps to exactly one legal action, and the UI shows **only** that action (an
invalid transition is never offered):

```
ASSIGNED     → Accept Assignment  → ACCEPTED
ACCEPTED     → Start Pickup       → IN_PROGRESS
IN_PROGRESS  → Complete Pickup    → COLLECTED
COLLECTED    → (read-only) Waiting for recycler
```

Once a pickup reaches `COLLECTED` it leaves the active queue and is handed to
the recycler (Sprint 9.6). The **status summary** tiles (Assigned, Accepted, In
Progress, Collected Today) are computed from the assignment list — no extra API
call — using `computeStatusSummary`.

### Workflow flow

```
Accept  (confirm) ─▶ PATCH /submissions/:id/accept   ─▶ invalidate collector.* ─▶ queue refreshes
Start   (confirm) ─▶ PATCH /submissions/:id/start     ─▶ invalidate collector.*
Complete(confirm) ─▶ PATCH /submissions/:id/complete  ─▶ invalidate collector.* (item leaves queue)
```

- Every workflow action requires **confirmation** via the shared `Dialog`
  ("Accept this pickup assignment?", "Start traveling to pickup location?",
  "Mark this pickup as completed?") and reports success with a **Sonner** toast.
- The **pickup timeline** reuses the shared read-only `SubmissionTimeline`,
  highlighting the collector stages (`ASSIGNED → ACCEPTED → IN_PROGRESS →
COLLECTED`); consumer stages before `ASSIGNED` read as complete and recycler
  stages remain upcoming.
- Because `GET /submissions/:id` is owner/admin-only on the backend, the details
  page sources its record from the collector's assignment-queue cache rather
  than a by-id fetch — a pickup that has left the queue (or an unknown id)
  renders the shared `NotFound` screen.

### Navigation

The Collector sidebar shows **Dashboard** and **Settings** (plus **Logout** in
the sidebar footer). Consumer routes are never exposed to a collector —
`navItemsForRole` filters the shared navigation by role.

### Reuse

The module adds **no** new empty-state, loader, or error screens. It reuses
`EmptyState`, `PageLoader` / `SkeletonCards` / `SkeletonTable`, and
`ServerError` / `NotFound` from the shared framework; the shared `StatCard`,
`Table`, `Badge`, `Dialog`, and dashboard containers; and the Consumer module's
pure submission display helpers (`SubmissionStatusBadge`, `SubmissionTimeline`,
`formatWeight` / `formatDate`, …) rather than duplicating them.

---

## Recycler Module

The Recycler role is the second **operational workflow** and the first to close
the reward loop — a recycler reads the submissions handed off by collectors,
processes each through the recycling lifecycle against the real backend, and
receives the GreenCoins reward the backend issues on completion. Everything
lives under `src/features/recycler/` and reuses the shared API layer, dashboard
framework, and UI primitives. Recycler assignment itself is an Admin/Government
concern and is intentionally not built here.

### Pages

| Page                            | Route                       | Contents                                                                       |
| ------------------------------- | --------------------------- | ------------------------------------------------------------------------------ |
| `RecyclerDashboardPage`         | `/recycler`                 | Status summary, active recycling, today's recycling, quick actions             |
| `RecyclerAssignmentDetailsPage` | `/recycler/submissions/:id` | Full record incl. recovered weight, notes, material recovery, and the timeline |

### API integration

The module talks only to the endpoints below (see
[`docs/engineering/05_API.md`](../docs/engineering/05_API.md)). Each wrapper uses
the single shared Axios instance and unwraps the success envelope
(`response.data.data`).

| Method                          | Endpoint                                  | Purpose                                           |
| ------------------------------- | ----------------------------------------- | ------------------------------------------------- |
| `recyclerApi.getAssignments`    | `GET /recycler/submissions`               | The recycler's active assignment queue            |
| `recyclerApi.startRecycling`    | `PATCH /submissions/:id/recycle/start`    | Begin processing (COLLECTED → RECYCLING)          |
| `recyclerApi.completeRecycling` | `PATCH /submissions/:id/recycle/complete` | Record recovery + finalize (RECYCLING → RECYCLED) |

Server state is managed with TanStack Query hooks (`useRecyclerAssignments`,
`useStartRecycling`, `useCompleteRecycling`). Mutations never refetch manually —
they invalidate the shared `recycler.*` query keys and let Query refresh what is
observed.

### Recycling lifecycle

`GET /recycler/submissions` returns only the recycler's **active** queue —
submissions in `COLLECTED` or `RECYCLING`. Each status maps to exactly one legal
action, and the UI shows **only** that action (an invalid transition is never
offered):

```
COLLECTED   → Start Recycling     → RECYCLING
RECYCLING   → Complete Recycling  → RECYCLED
RECYCLED    → (read-only) Completed
```

Once a job reaches `RECYCLED` it leaves the active queue. The **status summary**
tiles (Collected, Recycling, Completed Today, Recovered Weight) are computed from
the assignment list — no extra API call — using `computeRecyclerSummary`.

### Workflow flow

```
Start    (confirm)  ─▶ PATCH /submissions/:id/recycle/start     ─▶ invalidate recycler.* ─▶ queue refreshes
Complete (form)     ─▶ PATCH /submissions/:id/recycle/complete  ─▶ { submission, reward } ─▶ reward dialog + invalidate
```

- **Start Recycling** requires **confirmation** via the shared `Dialog`
  ("Start the recycling process?") and reports success with a **Sonner** toast.
- **Complete Recycling** opens `CompleteRecyclingDialog`, a **React Hook Form +
  Zod** form mirroring the backend `completeRecyclingSchema`:
  - **Recovered weight** — required, positive.
  - **Recycler notes** — optional textarea (≤ 2000 chars).
  - **Material recovery** — a dynamic add/remove list of `{ name, weight }` rows
    (weights non-negative, no duplicate names). On submit the list is folded into
    the `materialRecovery` object the backend expects, e.g.
    `{ Copper: 2.4, Plastic: 3.7, Glass: 1.2 }`.
- The **recycling timeline** reuses the shared read-only `SubmissionTimeline`,
  highlighting the recycler stages (`COLLECTED → RECYCLING → RECYCLED`); earlier
  consumer/collector stages read as complete.
- Because `GET /submissions/:id` is owner/admin-only on the backend, the details
  page sources its record from the recycler's assignment-queue cache rather than
  a by-id fetch — a job that has left the queue (or an unknown id) renders the
  shared `NotFound` screen.

### Reward integration

Rewards are **never calculated on the frontend**. `PATCH .../recycle/complete`
returns `{ submission, reward }`, and the reward is displayed exactly as
returned. On success `RewardSuccessDialog` opens with a "Congratulations!"
message and shared `StatCard`s for the backend values:

- **GreenCoins Awarded** (`reward.greenCoinsAwarded`)
- **Updated Balance** (`reward.updatedBalance`)
- **CO₂ Saved**, **Energy Saved**, **Landfill Diverted**
  (`reward.sustainability.*`, each with the unit the backend supplies)
- **Submission Status** (the updated `submission.status`)

A **Continue** button dismisses the dialog. The GreenCoins credit is automatic:
the recycler triggers it by completing the job, and the consumer's balance is
updated server-side.

### Navigation

The Recycler sidebar shows **Dashboard** and **Settings** (plus **Logout** in
the sidebar footer). Consumer/collector routes are never exposed to a recycler —
`navItemsForRole` filters the shared navigation by role.

### Reuse

The module adds **no** new empty-state, loader, or error screens. It reuses
`EmptyState`, `PageLoader` / `SkeletonCards` / `SkeletonTable`, and
`ServerError` / `NotFound` from the shared framework; the shared `StatCard`,
`Table`, `Badge`, `Dialog`, `Input` / `Textarea` / `Label`, and dashboard
containers; and the Consumer module's pure display helpers
(`SubmissionStatusBadge`, `SubmissionTimeline`, `formatWeight` / `formatDate`,
`formatMetric` / `formatPoints`, …) rather than duplicating them. The
start/confirm and complete/form dialog patterns mirror the Collector module
without altering its code.

---

## Government Module

The Government role is a **read-only oversight dashboard**. Government users are
**observers**: they monitor national e-waste statistics, environmental impact,
regional breakdowns, and AI demand forecasts. They perform **no** write
operations — no submission edits, no collector/recycler assignment, no workflow
transitions, and no reward issuance. Everything lives under
`src/features/government/` and reuses the shared API layer, dashboard framework,
and UI primitives.

### Pages

| Page                      | Route         | Contents                                                            |
| ------------------------- | ------------- | ------------------------------------------------------------------- |
| `GovernmentDashboardPage` | `/government` | National overview, environmental impact, regional & forecast tables |

Guarded by `RoleGuard allow={['GOVERNMENT', 'ADMIN']}`.

### API integration

The module talks **only** to the four analytics endpoints documented in
[`docs/engineering/05_API.md`](../docs/engineering/05_API.md) (Government + Admin
scope). Each wrapper uses the single shared Axios instance and unwraps the
success envelope (`response.data.data`). All calls are **read-only**.

| Method                                 | Endpoint                              | Purpose                                          |
| -------------------------------------- | ------------------------------------- | ------------------------------------------------ |
| `governmentApi.getOverview`            | `GET /analytics/overview`             | National e-waste statistics                      |
| `governmentApi.getEnvironmentalImpact` | `GET /analytics/environmental-impact` | National impact metrics (CO₂, energy, landfill)  |
| `governmentApi.getRegions`             | `GET /analytics/regions`              | Regional breakdown (rendered as a table)         |
| `governmentApi.getForecast`            | `GET /analytics/forecast`             | AI demand forecast (proxied from the AI service) |

Server state is managed with read-only TanStack Query hooks
(`useGovernmentOverview`, `useGovernmentEnvironmentalImpact`,
`useGovernmentRegions`, `useGovernmentForecast`) keyed under `government.*`.
There are no mutations.

### Backend availability & the 404 contract

> **The backend Analytics module is not yet deployed on this instance.** The
> module directory is an empty stub and no `/analytics` router is mounted, so the
> endpoints currently respond **404 Not Found**.

Per product decision, a 404 from these endpoints is treated as an **expected
"feature unavailable" condition**, not a server error:

- `isAnalyticsUnavailable(error)` classifies a 404 specifically.
- The hooks **do not retry** a 404 (they retry other transient failures), so the
  UI resolves immediately.
- When the primary overview endpoint 404s, a single, calm informational state
  (`AnalyticsUnavailable`) is shown for the whole page instead of a red error
  screen. Any other section resolves its own state independently, falling back to
  the shared `ServerError` (with retry) for genuine failures.

The API layer, DTOs, hooks, routing, layout, and components are all
**production-ready** and become functional automatically once the backend
Analytics module ships — no frontend change required.

### Provisional DTOs

The documentation lists the four endpoints with one-line descriptions but does
**not** yet specify field-level response DTOs. The interfaces in
[`src/types/analytics.ts`](src/types/analytics.ts) (`NationalOverview`,
`EnvironmentalImpact`, `RegionalBreakdown`, `DemandForecast`) are therefore
**inferred** from those descriptions and from the existing authoritative backend
contracts they will aggregate (the rewards module's `RewardBalance` /
`SustainabilityResult` and the submission lifecycle). They are type declarations
only — **no fabricated data** — and are clearly flagged in-file for reconciliation
against the real backend contract when the Analytics module is implemented.

### No mock data, no client-side aggregation

Every figure on the dashboard comes **straight from the backend**. There are no
hardcoded numbers, no charts fabricated from unavailable data, and no client-side
metric calculations. Because no chart library is bundled, the regional breakdown
and forecast are rendered as accessible **tables**; stat rows use the shared
`StatCard`. Empty backend lists render a shared `EmptyState`.

### Reuse

The module adds **no** new loader or error primitives. It reuses `StatCard`,
`Section`, `ContentCard`, `Table`, `Badge`, `EmptyState`, `SkeletonCards` /
`SkeletonTable`, `ServerError`, and the shared `formatPoints` / `formatMetric`
display helpers rather than duplicating them.

---

## Quality Gates

Before committing, ensure all of the following pass:

```bash
npm run lint        # 0 errors, 0 warnings
npm run typecheck   # no type errors
npm run build       # production build succeeds
npm run format:check
```
