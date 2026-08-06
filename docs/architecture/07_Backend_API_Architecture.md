# Backend API Architecture

**Version:** 1.0.0  
**Status:** Active  
**Last Updated:** 2026-08-06

**Scope:** Backend REST API application only (Node.js / Express / TypeScript service under `backend/`)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Backend Overview](#2-backend-overview)
3. [Layered Backend Architecture](#3-layered-backend-architecture)
4. [Bootstrap Sequence](#4-bootstrap-sequence)
5. [Module Organization](#5-module-organization)
6. [Routing Architecture](#6-routing-architecture)
7. [Controller Layer](#7-controller-layer)
8. [Service Layer](#8-service-layer)
9. [Repository Layer](#9-repository-layer)
10. [Authentication Architecture](#10-authentication-architecture)
11. [Authorization Strategy](#11-authorization-strategy)
12. [JWT & Refresh Token Flow](#12-jwt--refresh-token-flow)
13. [Middleware Pipeline](#13-middleware-pipeline)
14. [Validation Strategy](#14-validation-strategy)
15. [Error Handling](#15-error-handling)
16. [Logging Architecture](#16-logging-architecture)
17. [Configuration Management](#17-configuration-management)
18. [Health & Diagnostics](#18-health--diagnostics)
19. [Request Lifecycle](#19-request-lifecycle)
20. [Dependency Injection Strategy](#20-dependency-injection-strategy)
21. [Performance Considerations](#21-performance-considerations)
22. [Testing Strategy](#22-testing-strategy)
23. [Extension Points](#23-extension-points)
24. [Current Limitations](#24-current-limitations)
25. [Future Backend Evolution](#25-future-backend-evolution)
26. [Design Rationale](#26-design-rationale)

---

## 1. Executive Summary

The EcoTrace India backend is a **stateless REST API** built on Node.js, Express 4, and TypeScript. It is the transactional core of the platform: it authenticates users, records e-waste submissions, drives the collection and recycling lifecycle state machine, and issues sustainability rewards. It is the system-of-record service that the Web Platform ([06 — Web Platform Architecture]) consumes and that the AI and Blockchain subsystems ([02 — AI Platform Architecture], [05 — Blockchain Architecture]) integrate with through dedicated infrastructure clients.

The application is organized around three deliberate architectural commitments, each verifiable directly in the source:

- **Strict layering.** Every request flows through the same vertical stack — **Router → Middleware → Controller → Service → Repository → Prisma**. Each layer has one responsibility and depends only on the layer beneath it through an interface. HTTP concerns never leak into services; Prisma never leaks out of repositories.
- **Explicit dependency injection with no framework.** There is no DI container. `createApp()` in `src/app.ts` is a single, readable composition root that constructs every service and repository by hand and wires them together. Each component is a factory function (`createAuthService`, `createSubmissionRepository`, …) that receives its dependencies as a typed `deps` object.
- **Pure, testable assembly.** App construction is separated from process startup. `src/app.ts` builds an `Express` instance and binds nothing; `src/server.ts` owns the port, signals, and shutdown. Because assembly is pure and repositories are injected behind interfaces, the entire HTTP surface is exercised in integration tests with in-memory repositories and no database.

The result is a small, security-conscious, production-shaped service. Secrets are validated and fail-fast at boot, refresh tokens rotate and are stored only as hashes, all input is validated by Zod before a controller runs, and every error becomes one of a fixed set of machine-readable envelopes. This document reverse-engineers that implementation and explains why it is shaped the way it is.

---

## 2. Backend Overview

### 2.1 Technology Stack

The stack is defined by `backend/package.json` and is intentionally conventional — mature libraries, no bespoke frameworks:

| Concern | Technology | Notes |
|---|---|---|
| Runtime | Node.js ≥ 20 | `engines.node: ">=20"` |
| Language | TypeScript 5.7 (strict) | `strict`, `noUncheckedIndexedAccess`, `noImplicitOverride` |
| HTTP framework | Express 4.21 | Classic middleware/router model |
| ORM | Prisma 6 (`@prisma/client`) | Sole database access technology |
| Validation | Zod 3 | Environment, request, and pagination schemas |
| AuthN | `jsonwebtoken` 9 + `bcryptjs` 3 | JWT access/refresh + password hashing |
| Rate limiting | `express-rate-limit` 8 | Scoped to auth endpoints |
| Security headers | `helmet` 8 | Applied first in the pipeline |
| CORS | `cors` 2.8 | Driven by a configured allowlist |
| Logging | `pino` 9 + `pino-http` 10 | Structured JSON, redaction |
| Testing | Jest 29 + `ts-jest` + `supertest` | Unit + integration |

### 2.2 Responsibilities

The backend **owns** the following capabilities:

- User registration, login, session lifecycle, and profile retrieval.
- Role-based access control across five roles: `CONSUMER`, `COLLECTOR`, `RECYCLER`, `GOVERNMENT`, `ADMIN`.
- E-waste submission CRUD and the full lifecycle state machine (`PENDING → ASSIGNED → ACCEPTED → IN_PROGRESS → COLLECTED → RECYCLING → RECYCLED`).
- Collector and recycler assignment and dashboards.
- Automatic reward issuance, GreenCoins balances, and sustainability-impact accounting.
- Liveness/readiness diagnostics and API metadata.

The backend **explicitly excludes** (documented elsewhere and referenced only through boundaries here): the AI/Device Intelligence engines ([03 — Device Intelligence Architecture], [04 — Decision Intelligence Architecture]), the Digital Passport and Ledger engines, the blockchain/Fabric integration ([05 — Blockchain Architecture]), the Web Platform ([06 — Web Platform Architecture]), deployment, and database internals (Document 08). The AI and Fabric infrastructure clients exist under `src/infrastructure/` as integration seams but are not wired into any route in the current implementation.

### 2.3 API Surface at a Glance

All routes mount under a single configured prefix (`API_PREFIX`, default `/api/v1`). Every response uses a uniform envelope defined in `src/types/api.ts`:

```
Success:  { "success": true,  "data": <T>, "meta"?: { page, pageSize, total } }
Error:    { "success": false, "error": { "code", "message", "details"? } }
```

This is the same contract the Web Platform's API client layer depends on ([06 — Web Platform Architecture], §12 API Client Layer).

---

## 3. Layered Backend Architecture

The backend is a **classic layered (onion) architecture** with a single, enforced direction of dependency. Nothing in an inner layer knows about an outer one; HTTP types stop at the controller, and Prisma stops at the repository.

**Overall Backend Architecture Diagram**

```
┌─────────────────────────────────────────────────────────────────────┐
│                          HTTP Clients                                 │
│         Web Platform · Mobile · Server-to-server callers              │
└───────────────────────────────┬─────────────────────────────────────┘
                                 │  JSON over HTTP (/api/v1)
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     EXPRESS APPLICATION (src/app.ts)                  │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  GLOBAL MIDDLEWARE (order-sensitive)                         │    │
│  │  securityHeaders → cors → json → requestId → requestLogger   │    │
│  └───────────────────────────────┬─────────────────────────────┘    │
│                                   ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  MODULE ROUTERS (mounted at API_PREFIX)                     │    │
│  │  health · api-info · auth · users · submission · rewards    │    │
│  │  per-route: authenticate → authorize → validate             │    │
│  └───────────────────────────────┬─────────────────────────────┘    │
│                                   ▼                                   │
│  ┌───────────┐    ┌───────────┐    ┌────────────┐                    │
│  │ CONTROLLER │──▶│  SERVICE  │──▶│ REPOSITORY │                     │
│  │ HTTP shape │    │ business  │    │  Prisma    │                    │
│  │ (thin)     │◀──│  rules    │◀──│  boundary  │                     │
│  └───────────┘    └───────────┘    └─────┬──────┘                    │
│                                   ▲       │                          │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  TERMINAL MIDDLEWARE:  notFoundHandler → errorHandler        │    │
│  └─────────────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────┬─────────────────────────┘
                                             │
                     ┌───────────────────────┴───────────────────────┐
                     ▼                                                ▼
        ┌────────────────────────┐                      ┌────────────────────────┐
        │  INFRASTRUCTURE         │                      │  SHARED KERNEL          │
        │  prisma (singleton)     │                      │  config · errors        │
        │  ai.client   (seam)     │                      │  logging · middleware   │
        │  fabric.client (seam)   │                      │  pagination · utils     │
        └───────────┬────────────┘                      └────────────────────────┘
                    ▼
             ┌─────────────┐
             │  DATABASE   │  (Document 08)
             │ (PostgreSQL) │
             └─────────────┘
```

### 3.1 The Layers

| Layer | Location | Responsibility | May depend on |
|---|---|---|---|
| **Router** | `modules/*/**.routes.ts` | Map HTTP verb + path to a controller method; attach per-route middleware | Middleware, controller |
| **Controller** | `modules/*/**.controller.ts` | Read validated input, call the service, shape the HTTP response | Service, shared types |
| **Service** | `modules/*/**.service.ts` | Business rules, workflow/state-machine logic, authorization decisions | Repository interfaces, other services, errors, logger |
| **Repository** | `modules/*/**.repository.ts` | The only place Prisma is used per module; map rows to records | Prisma client (injected) |
| **Shared kernel** | `shared/*` | Cross-cutting concerns reused by every module | — |
| **Infrastructure** | `infrastructure/*` | External-system clients (Prisma, AI, Fabric) | — |

### 3.2 Dependency Rule

The invariant is stated in the repository files themselves: *"Repositories are the only place Prisma is used … Services depend on these interfaces, never on Prisma directly."* Services import repository **interfaces** (`UserRepository`, `SubmissionRepository`, `RewardRepository`), never the Prisma-backed implementations. This makes the whole business layer database-agnostic and is exactly what lets integration tests substitute in-memory fakes (§20, §22).

---

## 4. Bootstrap Sequence

Startup is split into two files by design so that **assembly is pure** and **only the process entry point touches the outside world**.

- `src/app.ts` — `createApp(deps)`: builds and returns an `Express` app. No `listen`, no `process.env` access, no port. Pure assembly.
- `src/server.ts` — `main()`: loads config, creates the logger, calls `createApp`, binds the port, and installs signal/shutdown handlers.

**Route Registration Flow Diagram**

```
main() [server.ts]
  │
  ├─ import 'dotenv/config'          load .env into process.env
  ├─ getConfig()                     parse + validate env (Zod) → frozen AppConfig
  ├─ createLogger(config)            pino logger (pretty in dev, JSON otherwise)
  ├─ createApp({ config, logger })   ── ENTER src/app.ts ──────────────┐
  │                                                                     │
  │     const app = express()                                          │
  │     app.disable('x-powered-by')                                    │
  │     GLOBAL MIDDLEWARE                                              │
  │       securityHeaders() → cors(origins) → json({limit:'1mb'})     │
  │       → requestId() → requestLogger(logger)                       │
  │                                                                    │
  │     MODULE WIRING + MOUNT (each at config.apiPrefix)             │
  │       1. health     createHealthService → controller → router    │
  │       2. api-info   createApiInfoService → controller → router    │
  │       3. auth       repos → tokenService → authService           │
  │                     → controller → router(authenticate,limiter)   │
  │       4. users      createUsersService(users) → router           │
  │       5. submission repo → submissionService(+rewardService)     │
  │                     → controller → router                        │
  │       6. rewards    repo → rewardService → controller → router    │
  │                                                                    │
  │     TERMINAL MIDDLEWARE                                           │
  │       notFoundHandler() → errorHandler(logger)                   │
  │     return app  ──────────────────────────────────────────────── ┘
  │
  ├─ app.listen(config.port, …)      structured "backend started" log line
  ├─ process.on('SIGTERM'|'SIGINT')  graceful shutdown → disconnectPrisma()
  └─ process.on('unhandledRejection') fatal log → exit(1)
```

### 4.1 Fail-Fast Configuration

`getConfig()` (via `loadConfig`) runs the Zod `envSchema` **once** at startup. If validation fails, the process throws before a port is ever opened — a missing production `DATABASE_URL`, a placeholder JWT secret in production, or identical access/refresh secrets all abort boot with a readable message (§17). This is the earliest possible failure point and is intentional.

### 4.2 Ordering Guarantees

Two orderings are load-bearing and are enforced purely by call order in `createApp`:

1. **Global middleware precedes routers.** `securityHeaders` runs first so *every* response — including 404s and errors — carries security headers. `requestId` precedes `requestLogger` so each completion log carries a correlation id.
2. **Terminal handlers run last.** `notFoundHandler` and `errorHandler` are registered after all routers, so unmatched routes become a `NotFoundError` and every thrown/rejected error converges on the single error handler.

### 4.3 Graceful Shutdown

On `SIGTERM`/`SIGINT`, `server.close()` stops accepting connections, then `disconnectPrisma()` releases the connection pool; a 10-second `unref()`'d timer force-exits if connections refuse to drain. `unhandledRejection` is treated as fatal.

---

## 5. Module Organization

The backend is organized by **feature module**, not by technical layer. Each module is a self-contained vertical slice under `src/modules/<name>/` that owns its controller, routes, service, schemas, types, and (where it touches the database) a repository. Cross-cutting code lives in `src/shared/`; external clients live in `src/infrastructure/`.

```
backend/src/
├── app.ts                     composition root (pure assembly)
├── server.ts                  process entry point (port, signals)
├── modules/
│   ├── api-info/              service · controller · routes · types · index
│   ├── auth/                  + repository · password.service · token.service · schemas
│   ├── health/                service · controller · routes · types · index
│   ├── rewards/               + repository · schemas
│   ├── submission/            + repository · schemas · types
│   └── users/                 service · controller · routes · schemas · types
├── shared/
│   ├── config/                config.ts · env.schema.ts
│   ├── errors/                app-error.ts · error-codes.ts
│   ├── logging/               logger.ts
│   ├── middleware/            11 middleware factories
│   ├── pagination/            pagination.schema.ts
│   └── utils/                 version.ts
├── infrastructure/
│   ├── prisma/                prisma.client.ts (singleton, ping, disconnect)
│   ├── ai/                    ai.client.ts (integration seam)
│   └── fabric/                fabric.client.ts (integration seam)
└── types/
    ├── api.ts                 SuccessResponse / ErrorResponse envelopes
    └── express.d.ts           Request.user augmentation
```

**Module Relationships Diagram**

```
                         ┌──────────────┐
                         │  src/app.ts  │  composition root
                         └──────┬───────┘
        wires & mounts ────────┼──────────────────────────────
      ┌──────────┬─────────────┼──────────────┬───────────────┐
      ▼          ▼             ▼               ▼               ▼
 ┌─────────┐ ┌────────┐  ┌──────────┐   ┌────────────┐   ┌─────────┐
 │ health  │ │api-info│  │   auth   │   │ submission │   │ rewards │
 └─────────┘ └────────┘  └────┬─────┘   └─────┬──────┘   └────┬────┘
                              │ owns          │ depends on     │
                              │ UserRepository│ RewardService  │
                              ▼               │  (auto-issue)  │
                         ┌─────────┐          ├────────────────┘
                         │  users  │◀─────────┘ reuses
                         │ (reuses │  auth.UserRepository
                         │  auth   │
                         │  repo)  │  submission.repo ──▶ used by rewards.service
                         └─────────┘  (findById for reward eligibility)

 Shared kernel (config · errors · logging · middleware · pagination · utils)
   is imported by every module. Infrastructure (prisma) is injected, never imported by services.
```

### 5.1 Inter-Module Dependencies (as implemented)

The wiring in `app.ts` reveals three deliberate cross-module relationships:

- **`users` reuses `auth`'s `UserRepository`.** The user table has a single owner (auth). Rather than introduce a second Prisma access point, `createUsersService({ users })` receives the same repository instance already built for auth. Modules stay decoupled because `users` depends on the **interface**, not on auth internals.
- **`submission` depends on `rewards`.** When a recycler completes processing (`RECYCLING → RECYCLED`), the submission service calls `rewardService.issueReward(id)` to auto-issue the reward in the same operation. `rewardService` is constructed first and injected into `submissionService`.
- **`rewards` reads `submission`'s repository.** `createRewardService` receives the shared `SubmissionRepository` so it can load a submission and verify it is `RECYCLED` before issuing a reward, without importing submission's service.

### 5.2 Barrel Exports

Every module exposes a single `index.ts` barrel (e.g. `modules/auth/index.ts`) re-exporting its factories and public types. `app.ts` imports only from these barrels using the path aliases `@modules/*`, `@shared/*`, `@infrastructure/*` (configured in `tsconfig.json` and rewritten at build time by `tsc-alias`). Internal files are never imported across module boundaries.

## 6. Routing Architecture

### 6.1 Prefix and Mounting

Every module router is mounted at the same configured prefix: `app.use(config.apiPrefix, <router>)`. There is no per-module base path; instead, each router declares full resource paths internally (e.g. `router.post('/auth/login', …)`, `router.get('/submissions', …)`). This keeps the composition root uniform — the prefix is decided once, in config — and lets the API version be changed (`/api/v1` → `/api/v2`) without touching any module.

The API version label surfaced by `api-info` is *derived from the prefix* rather than duplicated: `config.apiPrefix.split('/').filter(Boolean).at(-1) ?? 'v1'`. There is a single source of truth for the version.

### 6.2 Router Factories and Injected Middleware

Routers are **factories**, not module-level singletons. Each `createXRouter(controller, deps)` receives its controller plus the middleware it needs — the auth/authorize guards and, for auth, the rate limiter — as injected dependencies:

```ts
createAuthRouter(controller, { authenticate, rateLimiter })
createSubmissionRouter(controller, { authenticate, authorize })
```

This means a router never imports `authenticate` directly; it receives an already-bound instance (e.g. `authenticate(tokenService)`). The same pattern lets tests build a router with stub guards.

### 6.3 Per-Route Middleware Chains

Within a router, each route composes its own ordered chain. The canonical protected route is:

```
authenticate → authorize(<roles>) → validate({ params, body, query }) → handler
```

Handlers wrap the async controller call and forward rejections to the global error middleware with a uniform idiom:

```ts
router.get('/submissions/:id', authenticate, validate({ params: submissionIdSchema }),
  (req, res, next) => { controller.getById(req, res).catch(next); });
```

The `.catch(next)` is what connects async controllers to the single error handler — an unhandled promise rejection in a controller becomes an ordinary `next(err)`.

### 6.4 Route Inventory (reverse-engineered)

| Method & Path (under `/api/v1`) | Module | Guard | Validates |
|---|---|---|---|
| `GET /health` | health | public | — |
| `GET /ready` | health | public | — |
| `GET /` | api-info | public | — |
| `POST /auth/register` | auth | rate-limited | body |
| `POST /auth/login` | auth | rate-limited | body |
| `POST /auth/refresh` | auth | rate-limited | body |
| `POST /auth/logout` | auth | rate-limited | body |
| `GET /auth/me` | auth | authenticate | — |
| `GET /users?role=` | users | ADMIN, GOVERNMENT | query |
| `POST /submissions` | submission | CONSUMER | body |
| `GET /submissions` | submission | authenticate | query |
| `GET /submissions/:id` | submission | authenticate | params |
| `PATCH /submissions/:id` | submission | authenticate | params, body |
| `DELETE /submissions/:id` | submission | authenticate | params |
| `PATCH /submissions/:id/assign` | submission | ADMIN, GOVERNMENT | params, body |
| `PATCH /submissions/:id/accept` | submission | COLLECTOR | params |
| `PATCH /submissions/:id/start` | submission | COLLECTOR | params |
| `PATCH /submissions/:id/complete` | submission | COLLECTOR | params |
| `GET /collector/submissions` | submission | COLLECTOR | query |
| `PATCH /submissions/:id/assign-recycler` | submission | ADMIN, GOVERNMENT | params, body |
| `PATCH /submissions/:id/recycle/start` | submission | RECYCLER | params |
| `PATCH /submissions/:id/recycle/complete` | submission | RECYCLER | params, body |
| `GET /recycler/submissions` | submission | RECYCLER | query |
| `POST /rewards/issue/:submissionId` | rewards | ADMIN | params |
| `GET /rewards/history` | rewards | authenticate | query |
| `GET /rewards/balance` | rewards | authenticate | — |

This is the exact surface the Web Platform's role-scoped API clients call ([06 — Web Platform Architecture], §12).

### 6.5 Route Registration Order

`health` and `api-info` are registered before the authenticated modules, and both mount at the root/`/health`/`/ready` paths so infrastructure probes remain reachable and cheap. The rate limiter for auth is scoped with `router.use('/auth', rateLimiter)` **inside** the auth router — never registered globally — so brute-force protection applies only to authentication traffic and never throttles submissions or dashboards.

---

## 7. Controller Layer

Controllers are deliberately **thin**. Their entire job is: read already-validated input off the request, call one service method, and shape the HTTP response (status code + envelope). They contain no business rules, no database access, and no authorization logic.

A representative controller method (`submission.controller.ts`):

```ts
async create(req, res): Promise<void> {
  const result = await service.create(actorOf(req), req.body as CreateSubmissionInput);
  const body: SubmissionResponse = { success: true, data: result };
  res.status(201).json(body);
}
```

Three conventions are consistent across every controller:

- **Input is trusted because middleware already validated it.** The `req.body as CreateSubmissionInput` cast is safe precisely because the `validate` middleware ran first and replaced the raw segment with the parsed, coerced value (§14). Controllers never re-check shape.
- **The principal is read through a guard helper.** `actorOf(req)` and the auth module's `getAuthContext(req)` narrow `req.user`, throwing `UnauthorizedError` if the authenticate middleware did not run. This keeps controllers free of non-null assertions and defends against a route being misconfigured without a guard.
- **Status codes are explicit and semantic.** `201` for creates (`register`, submission `create`, reward `issue`), `200` for reads/updates, `204` for `delete` (`res.status(204).send()`), and error statuses are never set here — they are owned by the error handler.

Controllers expose a typed interface (`SubmissionController`, `AuthController`, …) and are produced by a `createXController(service)` factory, mirroring the factory pattern used everywhere else.

---

## 8. Service Layer

Services hold **all business logic**: workflow state machines, authorization decisions beyond coarse role checks, cross-entity orchestration, and mapping between database records and public DTOs. They are framework-agnostic — no `Request`, no `Response`, no Express import anywhere — which is what makes them unit-testable in isolation.

**Controller → Service → Repository Diagram**

```
   HTTP request (validated)
          │
          ▼
 ┌───────────────────┐   actorOf(req) / getAuthContext(req)
 │    CONTROLLER     │   • read typed input
 │   (thin, HTTP)    │   • pick status + envelope
 └─────────┬─────────┘
           │ service.method(actor, input)
           ▼
 ┌───────────────────┐   • enforce ownership / role rules
 │     SERVICE       │   • validateTransition(from,to)  ← state machine
 │ (business logic)  │   • orchestrate (e.g. auto-issue reward)
 │ framework-agnostic│   • map Record → PublicDTO
 └─────────┬─────────┘
           │ repository.method(...)      (interface, not Prisma)
           ▼
 ┌───────────────────┐   • the ONLY Prisma caller
 │    REPOSITORY     │   • select projections
 │  (data boundary)  │   • Record shape out
 └─────────┬─────────┘
           │ prisma.<model>.<op>()
           ▼
      Prisma Client (injected singleton)  ──▶  Database (Doc 08)
```

### 8.1 The Submission State Machine

The submission service is the clearest example of business logic centralization. The legal lifecycle transitions are declared **once** as data:

```ts
export const allowedTransitions: Record<SubmissionStatus, readonly SubmissionStatus[]> = {
  PENDING: ['ASSIGNED'], ASSIGNED: ['ACCEPTED'], ACCEPTED: ['IN_PROGRESS'],
  IN_PROGRESS: ['COLLECTED'], COLLECTED: ['RECYCLING'], RECYCLING: ['RECYCLED'],
  RECYCLED: [], COMPLETED: [], REJECTED: [],
};
```

Every status change flows through a single guard, `validateTransition(from, to)`, which throws `ConflictError` if `to` is not a legal successor of `from`. No route, controller, or repository ever compares statuses itself — the rule lives in exactly one place. This directly implements the lifecycle model that the Web Platform renders ([06 — Web Platform Architecture]) and that later phases extend.

### 8.2 Authorization Inside Services (Defense in Depth)

Route guards enforce the **coarse** role (e.g. only `COLLECTOR` may hit `/accept`). The service enforces the **fine-grained** rule that the actor owns the specific resource:

- `ensureCollectorOwnsSubmission` / `ensureRecyclerOwnsSubmission` load the row and assert `assignedCollectorId`/`assignedRecyclerId` equals the actor — returning `NotFoundError` (never `Forbidden`) so a collector cannot even probe for submissions that are not theirs.
- `loadAccessible` returns `NotFound` for both missing rows and rows owned by another non-admin user — preventing existence disclosure.
- Assignment is gated by `canAssign` (ADMIN or GOVERNMENT), and `ADMIN` may override the strict state machine while `GOVERNMENT` must follow it.

This layered check (route guard + service ownership check) is the "defence in depth" the code comments call out explicitly.

### 8.3 Cross-Service Orchestration

`completeRecycling` demonstrates orchestration: it validates the `RECYCLING → RECYCLED` transition, persists the recovery outcome, then **automatically issues the reward** via the injected `RewardService`, returning a composite `{ submission, reward }` payload. The reward service independently re-verifies the submission is `RECYCLED` and guards against duplicate issuance — the two services cooperate but neither trusts the other blindly.

### 8.4 DTO Mapping

Services never return raw database records. `toPublicUser`, `toPublicSubmission`, and `toListItem` map internal records to public shapes: dates become ISO strings, and — critically — `toPublicUser` never carries `passwordHash`. The `PublicUser` type is described in-code as *"the only user shape that ever leaves the auth module."*

### 8.5 Injectable Clock

Services that stamp time (`auth`, `submission`) accept an optional `now?: () => Date` dependency, defaulting to wall-clock. This makes token-expiry and pickup-timestamp logic deterministic under test without mocking global time.

---

## 9. Repository Layer

Repositories are the **sole boundary to Prisma**. Each is a factory (`createUserRepository({ prisma })`) that closes over an injected `PrismaClient` and returns an object implementing a plain TypeScript interface. Services depend only on that interface.

### 9.1 Responsibilities

- **Encapsulate every query.** All `prisma.<model>.<op>()` calls live here and nowhere else. The comment atop each repository states the rule verbatim.
- **Constrain output with `select` projections.** Each repository defines a `const … Select` projection (e.g. `userSelect`, `submissionSelect`) so queries return exactly the fields the record type declares — no accidental over-fetching, and the `passwordHash` never escapes except where authentication genuinely needs it.
- **Map pagination to Prisma.** A shared idiom `toPage(pagination) → { take, skip }` translates validated pagination into `take`/`skip`, returning `{}` when no window is supplied so unpaginated callers are unaffected.
- **Own partial-update semantics.** `toUpdateData` strips `undefined` keys so Prisma writes only fields the caller supplied, preserving unset columns.

### 9.2 Records vs. Models

Repositories return module-local **record** types (`UserRecord`, `SubmissionRecord`, `RewardTransactionRecord`), not Prisma model types. This decouples the service layer from the ORM's generated types — the database schema (Document 08) can evolve as long as the record contract holds.

### 9.3 Transactions

Atomic multi-row operations use Prisma's interactive transaction. `executeRewardTransaction` performs three writes — create the reward transaction, increment the user's GreenCoins, mark the submission as rewarded with its sustainability metrics — inside a single `prisma.$transaction(async (tx) => …)`, so a reward is all-or-nothing. This is the only place in the backend that spans multiple tables atomically, and it is deliberately owned by the repository, not the service.

### 9.4 Assignment Validation Without Coupling

The submission repository exposes `findCollectorById` / `findRecyclerById`, returning a minimal `{ id, role, isActive }` projection. This lets the submission service confirm an assignee is an active collector/recycler **without importing the auth module's repository** — modules stay decoupled even though they read the same physical table.

---

## 10. Authentication Architecture

Authentication is split into three cooperating pieces, each a framework-agnostic service or a single middleware:

- **`password.service.ts`** — `bcryptjs` hashing with a configured cost factor (`BCRYPT_ROUNDS`). `hash` uses a per-password salt; `verify` is a constant-time compare. Plaintext passwords never leave this service.
- **`token.service.ts`** — JWT signing/verification for both access and refresh tokens, plus SHA-256 token hashing. Detailed in §12.
- **`authenticate.middleware.ts`** — extracts the `Bearer` access token, verifies it via the token service, and attaches `req.user = { userId, role }`.

**Authentication Flow Diagram**

```
 CLIENT                    authenticate MW           authService            repositories
   │  POST /auth/login         │                        │                      │
   │  {email,password}         │                        │                      │
   │──────────────────────────▶│ (public route)         │                      │
   │                           │  authService.login()   │                      │
   │                           │───────────────────────▶│ findByEmail()        │
   │                           │                        │─────────────────────▶│
   │                           │                        │  passwords.verify()  │
   │                           │                        │  isActive? updateLastLogin()
   │                           │                        │  issueTokens():      │
   │                           │                        │   signAccessToken    │
   │                           │                        │   mintRefreshToken → store(hash)
   │  200 {accessToken,        │                        │                      │
   │       refreshToken,user}  │◀───────────────────────│                      │
   │◀──────────────────────────│                        │                      │
   │                           │                        │                      │
   │  GET /auth/me             │  verifyAccessToken()   │                      │
   │  Authorization: Bearer …  │  req.user={userId,role}│                      │
   │──────────────────────────▶│───────────────────────▶│ getMe → findById     │
   │  200 {PublicUser}         │◀───────────────────────│◀─────────────────────│
   │◀──────────────────────────│                        │                      │
```

### 10.1 Login

`login` looks the user up by email, verifies the password, and — importantly — returns a **single generic message** (`"Invalid email or password."`) for both an unknown email and a wrong password, preventing user enumeration. A deactivated account (`isActive === false`) is rejected separately only after credentials check out. On success it stamps `lastLogin` and issues a token pair.

### 10.2 Registration

`register` self-service creates a `CONSUMER` account only (privileged roles are seeded/administered, never self-assigned). It rejects duplicate emails with `ConflictError`, resolves the seeded `CONSUMER` role id (treating a missing role as an internal deployment fault), hashes the password, creates the user, and issues an initial token pair.

### 10.3 The Authenticated Principal

`req.user` is ambiently typed in `src/types/express.d.ts` as `{ userId: string; role: UserRole }` and is populated **only** by the authenticate middleware. Controllers read it through `getAuthContext`, which throws if it is absent — so a protected controller can never silently run unauthenticated.

---

## 11. Authorization Strategy

Authorization is **role-based (RBAC)** over the five `UserRole` values, enforced at two levels.

### 11.1 Coarse: The `authorize` Guard

`authorize(...roles)` is a tiny middleware factory that runs after `authenticate`. It returns `401` if no principal is attached (guarding against misordering) and `403` if `req.user.role` is not in the allowed set. It is the same shared function reused by every module — the submission, users, and rewards routers all receive it via injection and call `authorize(UserRole.ADMIN, UserRole.GOVERNMENT)` etc.

```ts
export function authorize(...roles: readonly UserRole[]): RequestHandler {
  return (req, _res, next) => {
    if (!req.user) throw new UnauthorizedError();
    if (!roles.includes(req.user.role)) throw new ForbiddenError();
    next();
  };
}
```

### 11.2 Fine: Ownership in Services

Role membership alone is insufficient for resource-scoped actions. A `COLLECTOR` passes the route guard for `/accept`, but the service still verifies they are the *assigned* collector for that specific submission (§8.2). The pairing — coarse role at the edge, ownership in the core — is the backend's complete authorization model.

### 11.3 Role Matrix (as implemented)

| Capability | CONSUMER | COLLECTOR | RECYCLER | GOVERNMENT | ADMIN |
|---|:---:|:---:|:---:|:---:|:---:|
| Create submission | ✓ | | | | |
| View own submissions | ✓ | ✓ | ✓ | ✓ | ✓ |
| View **all** submissions | | | | | ✓ |
| Assign collector / recycler | | | | ✓ | ✓ |
| Accept / start / complete pickup | | ✓ (assigned) | | | |
| Start / complete recycling | | | ✓ (assigned) | | |
| List users by role | | | | ✓ | ✓ |
| Manual reward issue | | | | | ✓ |
| View own rewards / balance | ✓ | ✓ | ✓ | ✓ | ✓ |

`ADMIN` additionally bypasses the strict state machine on assignment (override), whereas `GOVERNMENT` must follow legal transitions.

---

## 12. JWT & Refresh Token Flow

The token service implements a **rotating refresh-token** scheme with hash-only storage and reuse detection — a production-grade session design.

### 12.1 Access Tokens

- Signed with `JWT_SECRET`, short-lived (`JWT_ACCESS_EXPIRY`, default `15m`).
- Carry `sub` (user id), `email`, and `role` claims.
- `verifyAccessToken` strictly validates claim shapes (string `sub`/`email`, valid `UserRole`) and throws `UnauthorizedError` on any failure — a malformed or expired token is indistinguishable to the client.

### 12.2 Refresh Tokens

- Signed with a **separate** `JWT_REFRESH_SECRET`, long-lived (`JWT_REFRESH_EXPIRY`, default `7d`), each carrying a unique `jti` (`randomUUID`).
- The **raw token is never persisted.** Only its SHA-256 hex digest (`hashToken`) is stored, alongside `userId`, `expiresAt`, and a nullable `revokedAt`. A database leak therefore cannot yield usable refresh tokens.
- Expiry stored on the row is taken authoritatively from the signed `exp` claim, not recomputed.

**Refresh & Rotation Flow**

```
 refresh(refreshToken):
   verifyRefreshToken(sig+exp) ──▶ userId
   hash = hashToken(token)
   stored = refreshTokens.findByHash(hash)
        │
        ├─ not found        ─────────────▶ 401 Invalid/expired
        ├─ stored.revokedAt ──▶ REUSE! ──▶ revokeAllForUser(userId) ; 401
        ├─ expired          ─────────────▶ 401
        ├─ user missing/inactive ────────▶ 401
        └─ OK ─▶ revokeByHash(hash)   (old token single-use)
                 issueTokens(user) ──▶ new {access, refresh} pair
```

### 12.3 Rotation and Reuse Detection

On every successful refresh the presented token is immediately revoked (`revokeByHash`) and a fresh pair is issued — tokens are single-use. If a **revoked** token is presented again, the service treats the entire token family as compromised and calls `revokeAllForUser`, forcing re-authentication across all sessions. This is a textbook refresh-token-reuse defense.

### 12.4 Logout

`logout` is idempotent: it revokes the presented token's hash if parseable, and simply returns success for an unparseable token (there is no session to revoke). `revokeByHash` itself is a no-op on unknown or already-revoked tokens.

### 12.5 Rate Limiting

All `/auth/*` endpoints sit behind `authRateLimiter`, scoped inside the auth router. Exceeding `AUTH_RATE_LIMIT_MAX` requests per `AUTH_RATE_LIMIT_WINDOW_MS` per IP delegates to the global error handler with `TooManyRequestsError`, yielding a standard `429` envelope plus `RateLimit-*` headers.

## 13. Middleware Pipeline

Middleware is the backbone of the request path. Every middleware is a **factory** returning a `RequestHandler`, which keeps them configurable and injectable. There are two tiers: **global** middleware applied to all traffic in `app.ts`, and **per-route** middleware attached inside module routers.

**Middleware Pipeline Diagram**

```
        INCOMING REQUEST
              │
   ┌──────────▼───────────┐   GLOBAL (app.ts, order-sensitive)
   │ securityHeaders()    │   Helmet — HSTS, X-Frame-Options, etc. (CSP off)
   ├──────────────────────┤
   │ cors(corsOrigins)    │   allowlist; no-Origin (curl/S2S) allowed
   ├──────────────────────┤
   │ express.json(1mb)    │   body parse, 1 MB cap
   ├──────────────────────┤
   │ requestId()          │   x-request-id in/echo → req.id
   ├──────────────────────┤
   │ requestLogger(logger)│   pino-http completion log (ignores /health)
   └──────────┬───────────┘
              │
   ┌──────────▼───────────┐   PER-ROUTE (module routers)
   │ [authRateLimiter]    │   auth router only, scoped to /auth
   ├──────────────────────┤
   │ authenticate(tokens) │   Bearer verify → req.user           (protected)
   ├──────────────────────┤
   │ authorize(...roles)  │   RBAC 401/403                        (guarded)
   ├──────────────────────┤
   │ validate({b,p,q})    │   Zod parse; replace segment w/ typed value
   └──────────┬───────────┘
              │
        ┌─────▼─────┐
        │ CONTROLLER│  → SERVICE → REPOSITORY
        └─────┬─────┘
              │  (no match?)                    (thrown / rejected error?)
   ┌──────────▼───────────┐   TERMINAL          ┌───────────────────────┐
   │ notFoundHandler()    │──▶ NotFoundError ──▶│ errorHandler(logger)  │
   └──────────────────────┘                     │  → single JSON envelope│
                                                └───────────────────────┘
```

### 13.1 Global Middleware (in order)

| # | Middleware | Purpose | Notable behavior |
|---|---|---|---|
| 1 | `securityHeaders` | Helmet security headers | CSP disabled (JSON API + future `/docs`); all other defaults on. First so 404s/errors also carry headers. |
| 2 | `cors` | Origin allowlist | Requests with no `Origin` (curl, Postman, S2S) allowed; unlisted origins get no CORS headers (browser blocks) without erroring the request; `credentials: true`. |
| 3 | `express.json` | Body parsing | Hard `1mb` limit. |
| 4 | `requestId` | Correlation id | Honors incoming `x-request-id` (≤128 chars) or generates a UUID; echoes on the response. |
| 5 | `requestLogger` | HTTP access logging | `pino-http`; skips `*/health`; level by status; records `durationMs`. |

`app.disable('x-powered-by')` precedes them all, removing the framework-fingerprint header.

### 13.2 Per-Route Middleware

`authRateLimiter`, `authenticate`, `authorize`, and `validate` are attached per route as shown in §6.3. They run only where declared — e.g. the rate limiter is scoped to `/auth`, and `authorize` appears only on role-restricted routes.

### 13.3 Terminal Middleware

`notFoundHandler` converts any unmatched route into a `NotFoundError` (so 404s use the standard envelope), and `errorHandler` is the final `use()` — the single place errors become responses (§15). Their position last in `app.ts` is essential and intentional.

---

## 14. Validation Strategy

All request validation is **schema-first with Zod**, executed by one reusable middleware before any controller runs.

### 14.1 The `validate` Middleware

`validate({ body?, params?, query? })` iterates the three request segments, `safeParse`s each against its schema, and — on success — **replaces the raw segment with the parsed value**:

```ts
const result = schema.safeParse(req[segment]);
if (result.success) req[segment] = result.data;   // coerced + stripped
else /* collect field-level issues */
```

Because parsed output overwrites the input, controllers downstream receive coerced, trimmed, and stripped values only. This is why controller casts like `req.body as CreateSubmissionInput` are safe — the shape is guaranteed by the time the controller executes.

### 14.2 Field-Level Error Aggregation

The middleware collects **all** issues across all segments into an `ErrorDetail[]` of `{ field, issue }` and throws a single `ValidationError` (→ `400`). Clients receive every problem at once, not one at a time, matching the error contract's `details` array.

### 14.3 Schema Locations

- **Module request schemas** live beside their module (`auth.schemas.ts`, `submission.schemas.ts`, `reward.schemas.ts`, `users.schemas.ts`) and export both the schema and its inferred TypeScript type (`z.infer`). The types the service consumes are literally derived from the validation schema — a single source of truth for shape.
- **Shared pagination** (`pagination.schema.ts`) coerces `?limit=&offset=`, clamps `limit` to `[1,100]` (default 50) and `offset` to `≥0` (default 0), so every list endpoint validates pagination identically.
- **Environment** validation reuses the same Zod discipline at startup (§17).

Schema highlights show intent: emails are trimmed and lowercased; passwords are 8–128 chars with a `confirmPassword` refinement; coordinates are range-checked (`lat ∈ [-90,90]`, `lng ∈ [-180,180]`); ids are validated as UUIDs; update schemas are `.partial()` with a "at least one field" refinement.

---

## 15. Error Handling

Error handling is **centralized and contract-driven**. There is exactly one place errors become HTTP responses: `errorHandler` (the last middleware). Everything else simply throws.

### 15.1 The Operational Error Hierarchy

`AppError` is the base class for all *expected* (operational) errors, carrying a stable `code`, an `httpStatus`, a message, and optional field `details`. Concrete subclasses map one-to-one to HTTP statuses:

| Error class | Code | HTTP |
|---|---|---|
| `ValidationError` | `VALIDATION_ERROR` | 400 |
| `UnauthorizedError` | `UNAUTHORIZED` | 401 |
| `ForbiddenError` | `FORBIDDEN` | 403 |
| `NotFoundError` | `NOT_FOUND` | 404 |
| `ConflictError` | `CONFLICT` | 409 |
| `TooManyRequestsError` | `TOO_MANY_REQUESTS` | 429 |
| `InternalError` | `INTERNAL_ERROR` | 500 |
| `ServiceUnavailableError` | `SERVICE_UNAVAILABLE` | 503 |

The `ErrorCodes` constant is the single, machine-readable vocabulary clients switch on — the same codes the Web Platform's error handling maps to user-facing messages ([06 — Web Platform Architecture], §16).

### 15.2 The Error Handler's Three Paths

```
errorHandler(err):
  1. err instanceof AppError            → res.status(err.httpStatus).json({success:false, error:{code,message,details?}})
  2. err is Prisma known request error  → map P2002→409 CONFLICT, P2025→404 NOT_FOUND (generic message; log raw)
  3. anything else                      → log full error; res.status(500) generic INTERNAL_ERROR
```

Two security properties are explicit in the code:

- **Prisma internals never reach the client.** Known Prisma codes (`P2002` unique-violation, `P2025` record-not-found) are translated to safe semantic responses with generic messages; the raw Prisma message (which may expose table/column/SQL) is logged for observability but never serialized to the client. Unlisted Prisma codes fall through to the generic 500.
- **Unexpected errors are opaque.** Any non-`AppError`, non-mapped error is logged with the full detail and request id, but the client receives only a generic 500 envelope — no stack traces, no internals.

### 15.3 How Errors Reach the Handler

Synchronous throws in middleware/controllers propagate to Express automatically. Async controllers are wrapped in routers with `(req,res,next) => controller.method(req,res).catch(next)`, converting a rejected promise into `next(err)`. This uniform idiom is why services and controllers can simply `throw new ConflictError(...)` and trust it becomes the right HTTP response.

---

## 16. Logging Architecture

Logging uses **Pino** for structured, low-overhead JSON logs, created once in `server.ts` and injected everywhere it is needed.

### 16.1 Logger Construction

`createLogger(config, destination?)` configures:

- **Level** from `LOG_LEVEL`.
- **Redaction** of sensitive paths — `req.headers.authorization`, `req.headers.cookie`, `password`, `token`, `secret` — censored to `[REDACTED]`. Secrets structurally cannot appear in logs.
- **Base fields** `{ service: 'ecotrace-backend' }` and ISO timestamps.
- **Transport**: `pino-pretty` (colorized, single-line) in development; raw JSON in test/production; an explicit destination stream may be injected (used by tests to capture output).

### 16.2 Request Logging & Correlation

`requestLogger` wraps `pino-http` and reuses `req.id` (set by the `requestId` middleware) as the log correlation id. Each completion log carries `requestId`, `status`, and `durationMs` (measured by pino-http, not recomputed). Log level is derived from outcome: `error` for ≥500 or thrown errors, `warn` for ≥400, else `info`. Health checks are excluded from access logging to keep probe noise out of the logs.

### 16.3 Domain Logging

Services log meaningful domain events with structured context — `"User logged in"` with `userId`, `"Submission created"`, `"Collector assigned"`, `"Reward issued for recycled submission"` with points and balance, and security-relevant events like `"Revoked refresh token reused; revoking all sessions"`. Logs carry ids and outcomes, never secrets or PII beyond identifiers.

---

## 17. Configuration Management

Configuration is **typed, validated, immutable, and cached** — assembled once from the environment and frozen.

### 17.1 Schema-Validated Environment

`env.schema.ts` defines a Zod schema for every environment variable, with sensible development defaults so an empty environment still boots locally and in tests. `loadConfig()` `safeParse`s `process.env`; on failure it throws a single readable message listing every offending variable, so misconfiguration fails fast at startup rather than surfacing as a runtime error later.

### 17.2 The `AppConfig` Contract

The parsed result is mapped into a `readonly` `AppConfig` object and `Object.freeze`d — configuration cannot be mutated after load. `getConfig()` caches it process-wide (loading lazily on first access); `resetConfigForTesting()` clears the cache for tests.

### 17.3 Production Hardening (superRefine)

The schema's `superRefine` adds production-only invariants that are the backend's first line of security defense:

- `DATABASE_URL` is **required** in production.
- `JWT_SECRET` / `JWT_REFRESH_SECRET` must not retain their `dev-insecure-` placeholder values in production.
- The two JWT secrets **must differ** — access and refresh tokens can never be signed with the same key.

Non-production environments get working placeholder secrets (≥32 chars) so development and CI need zero secret configuration, while production categorically refuses to start with weak or shared secrets. This satisfies the repository's security mandate to never rely on default or shared secrets in production.

### 17.4 Configuration Surface

| Variable | Default | Meaning |
|---|---|---|
| `NODE_ENV` | `development` | Environment mode |
| `PORT` | `3000` | Listen port |
| `API_PREFIX` | `/api/v1` | Route mount prefix + version source |
| `LOG_LEVEL` | `info` | Pino level |
| `DATABASE_URL` | — (required in prod) | Prisma connection |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowlist |
| `JWT_SECRET` / `JWT_REFRESH_SECRET` | dev placeholders | Signing keys (must differ, non-placeholder in prod) |
| `JWT_ACCESS_EXPIRY` / `JWT_REFRESH_EXPIRY` | `15m` / `7d` | Token lifetimes |
| `BCRYPT_ROUNDS` | `10` | Password hash cost (4–15) |
| `AUTH_RATE_LIMIT_WINDOW_MS` / `AUTH_RATE_LIMIT_MAX` | `900000` / `10` | Auth brute-force limits |

`CORS_ORIGINS` is parsed from a comma-separated string into a trimmed, non-empty `string[]` by the schema itself — a small example of pushing normalization into validation.

---

## 18. Health & Diagnostics

Two dedicated modules provide operational visibility without authentication, so gateways and orchestrators can probe them cheaply.

### 18.1 Liveness — `GET /health`

`health.service.getStatus()` returns a synchronous snapshot — `status: 'ok'`, service name, version (read from `package.json` via `getAppVersion`), environment, `uptime`, and an ISO timestamp — and **never touches external systems**. It is a pure liveness signal and is excluded from access logging. It always returns `200` while the process is serving.

### 18.2 Readiness — `GET /ready`

`getReadiness()` verifies downstream dependencies by calling the injected `pingDatabase()` probe (`SELECT 1` via Prisma). If the database is unreachable it throws `ServiceUnavailableError`, which the global handler maps to a `503` envelope; otherwise it returns `{ database: 'connected', ready: true }`. The probe never throws — connectivity failures resolve to `false` and are turned into the correct HTTP status by the service. `pingDatabase` is injectable (`AppDeps.pingDatabase`) so readiness is deterministically testable.

### 18.3 API Metadata — `GET /`

`api-info.service` returns the product-facing API name, the version label derived from the prefix, the environment, and the documentation path (`{apiPrefix}/docs`). It is the discovery/root endpoint.

---

## 19. Request Lifecycle

Bringing the layers together, this is the complete path of a representative authenticated, role-guarded, body-validated request — `PATCH /api/v1/submissions/:id/assign`.

**Request Lifecycle Diagram**

```
 CLIENT
   │  PATCH /api/v1/submissions/{id}/assign
   │  Authorization: Bearer <access>    Body: { collectorId }
   ▼
 ┌────────────────────── GLOBAL MIDDLEWARE ──────────────────────┐
 │ securityHeaders → cors → json(1mb) → requestId → requestLogger │
 │   • req.id assigned / echoed as x-request-id                   │
 └───────────────────────────────┬───────────────────────────────┘
                                  ▼
 ┌──────────────────── SUBMISSION ROUTER (matched) ──────────────┐
 │ authenticate(tokenService)                                    │
 │   • verify Bearer → req.user = { userId, role }               │
 │ authorize(ADMIN, GOVERNMENT)                                  │
 │   • 401 if no principal · 403 if role not allowed             │
 │ validate({ params: submissionIdSchema, body: assignSchema })  │
 │   • parse/coerce; replace req.params/body; 400 on failure     │
 └───────────────────────────────┬───────────────────────────────┘
                                  ▼
 ┌───────────── CONTROLLER: assignCollector ─────────────────────┐
 │ actor = actorOf(req)      id = req.params.id                   │
 │ { collectorId } = req.body                                     │
 │ result = await service.assignCollector(actor, id, collectorId) │
 └───────────────────────────────┬───────────────────────────────┘
                                  ▼
 ┌───────────── SERVICE: assignCollector ────────────────────────┐
 │ canAssign(actor)?                     else → ForbiddenError    │
 │ submissions.findById(id)              else → NotFoundError     │
 │ submissions.findCollectorById(cId)    active COLLECTOR?        │
 │ if !admin: validateTransition(status,'ASSIGNED')              │
 │ submissions.assignCollector(id,cId)   → row ASSIGNED           │
 │ logger.info("Collector assigned")     map → PublicSubmission   │
 └───────────────────────────────┬───────────────────────────────┘
                                  ▼
 ┌───────────── REPOSITORY (Prisma boundary) ────────────────────┐
 │ prisma.submission.update({ assignedCollectorId, status })     │
 └───────────────────────────────┬───────────────────────────────┘
                                  ▼
        res.status(200).json({ success:true, data: <PublicSubmission> })
                                  │
              (any throw / rejection anywhere above)
                                  ▼
                     errorHandler(logger) → one JSON error envelope
```

Every request — success or failure — exits through exactly one of two points: a controller's explicit `res.json`, or the global `errorHandler`. There is no third way for a response to leave the backend.

## 20. Dependency Injection Strategy

The backend uses **manual, constructor-style dependency injection with zero framework**. This is a deliberate architectural choice, not an omission.

### 20.1 The Composition Root

`createApp()` is the single composition root. It is the only place where concrete implementations are constructed and wired: repositories are built from the Prisma singleton, services receive their repositories and collaborators, controllers receive services, and routers receive controllers plus middleware. Read top to bottom, `app.ts` *is* the dependency graph — no annotations, no reflection, no container to reason about.

```ts
const users = authRepositories?.users ?? createUserRepository({ prisma: getPrismaClient() });
const tokenService = createTokenService({ accessSecret, refreshSecret, accessExpiry, refreshExpiry });
const authService  = createAuthService({ users, refreshTokens, passwords, tokens: tokenService, logger });
const authRouter   = createAuthRouter(createAuthController(authService),
                       { authenticate: authenticate(tokenService), rateLimiter: authRateLimiter(...) });
```

### 20.2 The Factory Convention

Every component — service, repository, controller, router, middleware — is a `createX(deps)` factory returning a plain object or `RequestHandler`, where `deps` is a typed, mostly `readonly` interface. No classes with hidden state, no singletons beyond the two that must be (`getPrismaClient`, `getConfig`). This makes dependencies explicit at every call site and every component trivially constructable in a test with fakes.

### 20.3 Test Seams

`AppDeps` exposes explicit **test seams** that let integration tests replace infrastructure without touching production wiring:

- `authRepositories` — inject in-memory `UserRepository` / `RefreshTokenRepository`.
- `submissionRepository`, `rewardRepository` — inject in-memory fakes.
- `pingDatabase` — override the readiness probe deterministically.

Each defaults (`??`) to the Prisma-backed implementation, so production wiring is the zero-config path and tests opt in. This single design decision is what makes the entire HTTP surface testable without a database (§22).

---

## 21. Performance Considerations

The backend is small and I/O-bound; its performance posture is about efficient database access and cheap request handling rather than compute optimization.

- **Lazy, singleton database connection.** `getPrismaClient()` constructs the client once and connects lazily on first query; nothing requires a database until a route actually needs one. Health-liveness and API-info never touch it.
- **Constrained `select` projections.** Every query fetches only declared fields, minimizing row width and payload size and avoiding accidental N+1 via explicit relation `select`s (e.g. reward history joins the submission projection in one query).
- **Offset pagination with a hard ceiling.** All list endpoints validate pagination, capping `limit` at 100 to bound query and response size; unpaginated internal callers pass no window and are unaffected.
- **Atomic writes over round-trips.** The reward workflow's three related writes execute in one `$transaction`, avoiding partial-state races and multiple client round-trips.
- **Cheap middleware.** Security headers, CORS, id assignment, and logging are all constant-time; the JSON body is capped at 1 MB; auth verification is a single JWT `verify`.
- **Low-overhead structured logging.** Pino is among the fastest Node loggers; health probes are excluded from access logging.
- **Stateless horizontal scalability.** The service holds no in-process session state — sessions live in signed tokens and the refresh-token table — so instances scale horizontally behind a load balancer. (One caveat: the auth rate limiter uses the default in-memory store; see §24.)

---

## 22. Testing Strategy

Testing is a first-class concern that directly shaped the architecture, and the layering exists in large part to make it possible. Tests use **Jest + ts-jest**, with **Supertest** for HTTP-level integration.

### 22.1 Two Test Tiers

- **Unit tests** (`tests/unit/`) cover services, middleware, and utilities in isolation — the token service, password service, auth service, submission/reward services and controllers, both authorization and validation middleware, the error handler, config loading, and the logger. Because services are framework-agnostic factories, each is tested by constructing it with fakes and asserting behavior — no HTTP, no Express.
- **Integration tests** (`tests/integration/`) exercise the real Express app end-to-end (auth, health, reward, submission) via Supertest, driving actual routes, middleware, controllers, and services.

### 22.2 Database-Free Integration

Integration tests build the real app through `createApp` but inject in-memory repositories via the `AppDeps` test seams (`tests/helpers/in-memory-*`). The full request pipeline — routing, authentication, RBAC, validation, error mapping, envelope shaping — runs exactly as in production, but against fakes. For example, the auth suite builds the app with `createInMemoryAuthRepositories()`, sets `BCRYPT_ROUNDS: '4'` for speed, raises the rate limit so unrelated tests don't trip it, and asserts full envelopes — including a guard that serialized responses **never contain `passwordHash`**.

### 22.3 Determinism

Injectable `now()` clocks (auth, submission) and injectable `pingDatabase`/`uptime` probes (health) make time- and dependency-sensitive logic deterministic without global mocking.

### 22.4 Quality Gates

`package.json` scripts define the verification surface used in CI and pre-commit: `typecheck` (strict `tsc --noEmit`), `lint` (ESLint), `format:check` (Prettier), and `test` / `test:coverage` (Jest). `lint-staged` + Husky enforce lint and format on staged files. TypeScript runs in strict mode with `noUncheckedIndexedAccess`, `noUnusedLocals`, and `noUnusedParameters`, so the compiler itself is a correctness gate.

---

## 23. Extension Points

The architecture is designed to grow along its existing seams without structural change:

- **New feature module.** Add `src/modules/<name>/` with the standard slice (routes, controller, service, schemas, types, repository, barrel `index.ts`) and wire it in `createApp` with one `app.use(config.apiPrefix, router)`. No other file changes.
- **New endpoint on an existing module.** Add a schema, a service method, a controller method, and a route line — the layers guide exactly where each piece goes.
- **New persistence backend.** Because services depend on repository *interfaces*, an alternative implementation (a different database, a cache-through, a remote service) is a drop-in at the composition root.
- **AI / Blockchain integration.** `src/infrastructure/ai/` and `src/infrastructure/fabric/` already exist as client seams. A service can receive an injected AI or Fabric client the same way it receives a repository, letting the backend call into the Device Intelligence ([03 — Device Intelligence Architecture]) or on-chain ledger ([05 — Blockchain Architecture]) subsystems without those concerns leaking into the HTTP layers.
- **New error type.** Add an `AppError` subclass and an `ErrorCodes` entry; the global handler serializes it automatically.
- **API documentation.** The `/docs` path and CSP accommodation already anticipate a Swagger/OpenAPI UI (§24).

---

## 24. Current Limitations

Stated honestly, and grounded in the implementation as it exists today:

- **No OpenAPI/Swagger yet.** The `documentationPath` (`{apiPrefix}/docs`) is advertised by `api-info` and `securityHeaders` deliberately disables CSP to accommodate a future docs UI, but **no OpenAPI document or Swagger route is implemented**. API documentation currently lives in `docs/engineering/05_API.md` and this document.
- **In-memory rate-limit store.** `authRateLimiter` uses `express-rate-limit`'s default in-process store. Across multiple horizontally-scaled instances the limit is per-instance, not global; a shared store (e.g. Redis) would be needed for a true cluster-wide limit.
- **Response `meta` not yet populated.** The envelope supports a pagination `meta` (`page/pageSize/total`), but list endpoints currently return arrays under `data` without a `meta` block; total counts are not returned.
- **Offset pagination only.** Simple `limit`/`offset` is used everywhere; deep pages incur increasing scan cost and there is no cursor pagination.
- **AI/Fabric clients unwired.** The infrastructure seams exist but no route yet invokes them; cross-subsystem calls are anticipated, not active.
- **Single-node assumptions.** The Prisma client and config caches are per-process; horizontal scale is supported for stateless request handling but shared concerns (rate limiting) are not yet externalized.
- **No refresh-token pruning job.** Revoked/expired refresh-token rows accumulate; a cleanup task is not implemented.

None of these compromise correctness or security today; they are the natural next increments.

---

## 25. Future Backend Evolution

Prioritized, and consistent with the platform roadmap in `PROJECT.md`:

1. **OpenAPI 3 + Swagger UI** served at `{apiPrefix}/docs`, generated from the existing Zod schemas so documentation stays in lockstep with validation.
2. **Populated pagination `meta`** (total counts) and optional **cursor pagination** for large collections.
3. **Distributed rate limiting** via a shared store, plus broader rate limits beyond auth.
4. **AI subsystem integration** — wire `infrastructure/ai` into a service so submissions can be enriched by Device Intelligence classification/valuation ([03 — Device Intelligence Architecture], [04 — Decision Intelligence Architecture]).
5. **Blockchain anchoring** — on lifecycle-terminal events (e.g. `RECYCLED`), record an immutable audit entry through `infrastructure/fabric` ([05 — Blockchain Architecture]), keeping only hashes/events on-chain per the blockchain rules.
6. **Observability** — metrics (Prometheus) and distributed tracing keyed on the existing `x-request-id` correlation id.
7. **Background jobs** — refresh-token pruning, scheduled reporting, and notification dispatch.
8. **Idempotency keys** for mutating endpoints to make client retries safe.

---

## 26. Design Rationale

Every significant decision in this backend trades a little upfront structure for long-term correctness, security, and testability — the priority order mandated by the repository's engineering charter.

**Why manual DI instead of a container?** The dependency graph is small enough to read in one file. A container would add indirection and runtime magic for no benefit at this scale, while manual wiring keeps every dependency explicit and every component constructable in a test. The composition root *is* the documentation.

**Why separate `app.ts` from `server.ts`?** So assembly is pure. Nothing about building the application should require a port, environment access, or a database — and because it doesn't, the entire HTTP surface is testable in-process. This one split is the foundation of the testing strategy.

**Why the strict Router → Controller → Service → Repository layering?** Each layer has exactly one reason to change. HTTP concerns stop at the controller, business rules concentrate in the service, and Prisma is quarantined in the repository. The payoff is concrete: swapping the database, faking it in tests, or changing the wire format each touches exactly one layer.

**Why centralize the state machine and the error handler?** Correctness. A single `validateTransition` and a single `errorHandler` mean the lifecycle rules and the error contract each exist in one place and cannot drift. There is no second opinion on whether `COLLECTED → RECYCLING` is legal, or on how a `ConflictError` is serialized.

**Why hash-only, rotating refresh tokens with reuse detection?** Security in depth. A database leak yields no usable tokens; a stolen token is single-use; and replay of a rotated token trips a family-wide revocation. Combined with fail-fast secret validation, generic credential errors, redacted logs, and Prisma-detail suppression, the backend treats security as a design property, not an afterthought.

**Why schema-first validation with inferred types?** One source of truth. The Zod schema validates the request *and* generates the TypeScript type the service consumes, so the validated shape and the compiled shape can never disagree. Invalid input is rejected at the edge, and controllers operate only on trusted, typed data.

**Why factories and injected middleware everywhere?** Uniformity and substitutability. When every unit is a `createX(deps)` factory, the whole system is composed the same way, learned once, and rewired freely — for a new module, a new backend, or a test double.

Together these choices produce a backend that is deliberately unremarkable in its parts and robust in their composition: conventional libraries, strict boundaries, explicit wiring, and a single well-defined path in and out for every request. That is the intended character of the EcoTrace India API — a maintainable, secure, production-shaped core the rest of the platform can build on with confidence.

---

*This document was reverse-engineered from the backend implementation under `backend/` and reflects the source as the single authoritative reference. Where behavior and prior documentation might diverge, the code in `backend/src/` is the source of truth. It is consistent with, and cross-references, Documents 01–06; database internals are deferred to Document 08.*
