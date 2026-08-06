# Database Architecture

**Version:** 1.0.0  
**Status:** Active  
**Last Updated:** 2026-08-06

**Scope:** Database layer only (PostgreSQL schema, Prisma ORM, and the persistence boundary under `backend/prisma/` and `backend/src/infrastructure/prisma/`)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Database Overview](#2-database-overview)
3. [Layered Persistence Architecture](#3-layered-persistence-architecture)
4. [Prisma Architecture](#4-prisma-architecture)
5. [PostgreSQL Architecture](#5-postgresql-architecture)
6. [Schema Organization](#6-schema-organization)
7. [Entity Model](#7-entity-model)
8. [Relationships](#8-relationships)
9. [Constraints](#9-constraints)
10. [Index Strategy](#10-index-strategy)
11. [Repository Integration](#11-repository-integration)
12. [Transactions](#12-transactions)
13. [Query Patterns](#13-query-patterns)
14. [Pagination Strategy](#14-pagination-strategy)
15. [Migration Strategy](#15-migration-strategy)
16. [Seed Strategy](#16-seed-strategy)
17. [Data Integrity](#17-data-integrity)
18. [Error Handling](#18-error-handling)
19. [Configuration](#19-configuration)
20. [Performance](#20-performance)
21. [Testing](#21-testing)
22. [Extension Points](#22-extension-points)
23. [Current Limitations](#23-current-limitations)
24. [Future Database Evolution](#24-future-database-evolution)
25. [Design Rationale](#25-design-rationale)
26. [Conclusion](#26-conclusion)

---

## 1. Executive Summary

The EcoTrace India database is a **relational PostgreSQL store accessed exclusively through Prisma ORM**. It is the durable system-of-record that the backend REST API ([07 — Backend API Architecture]) reads and writes: identities and roles, authentication sessions, the e-waste submission lifecycle, and the reward/sustainability ledger. It is the persistence tier of the overall system described in [01 — System Architecture].

The design is defined by a small set of verifiable commitments, each drawn directly from the implementation:

- **A single declarative schema.** `backend/prisma/schema.prisma` is the one source of truth for every table, column, enum, relation, index, and constraint. There are **5 models** (`Role`, `User`, `RefreshToken`, `Submission`, `RewardTransaction`) and **3 enums** (`UserRole`, `SubmissionStatus`, `RewardReason`). Nothing in the schema is invented in this document — every object below appears in that file or in a committed migration.
- **Migration-driven evolution.** The physical database is not hand-crafted; it is the deterministic replay of **6 committed SQL migrations** under `prisma/migrations/`, tracked with a `migration_lock.toml` pinned to `postgresql`. The schema's history — from the initial auth tables, through the role enum conversion, refresh tokens, submissions, the recycler workflow, and the rewards engine — is fully recoverable from those files.
- **A quarantined access boundary.** Only the Prisma Client touches the database, and only repositories touch the Prisma Client. This is the same layering enforced in [07 — Backend API Architecture]: services depend on repository interfaces, never on Prisma, so the ORM is a replaceable implementation detail.
- **Integrity enforced at the database, not just the application.** Foreign keys, unique constraints, referential actions (`CASCADE`, `RESTRICT`, `SET NULL`), and a one-to-one reward guard are declared in the schema and materialized as PostgreSQL constraints — the database refuses invalid states even if application code were to err.

This document reverse-engineers that persistence layer and explains why it is shaped the way it is. It deliberately excludes the API, AI, decision, passport, blockchain, frontend, and deployment concerns documented elsewhere (Documents 01–07); it covers the data tier only.

---

## 2. Database Overview

### 2.1 Technology

| Concern | Technology | Source of truth |
|---|---|---|
| RDBMS | PostgreSQL | `datasource db { provider = "postgresql" }` |
| ORM / query builder | Prisma 6 (`prisma` + `@prisma/client` ^6.2.1) | `package.json` |
| Client generator | `prisma-client-js` | `generator client` block |
| Migration engine | Prisma Migrate | `prisma/migrations/` + `migration_lock.toml` |
| Seeding | `tsx prisma/seed.ts` | `package.json` → `prisma.seed` |
| Connection string | `DATABASE_URL` (env) | `datasource db { url = env("DATABASE_URL") }` |

### 2.2 What the Database Stores

The store owns exactly five tables, mapped to snake_case/plural physical names:

| Model | Table | Purpose |
|---|---|---|
| `Role` | `roles` | The five system roles (reference data, seeded) |
| `User` | `users` | Accounts, credentials (hash), profile, GreenCoins balance |
| `RefreshToken` | `refresh_tokens` | Hashed, rotating session tokens |
| `Submission` | `submissions` | E-waste items and their full lifecycle state + recovery data |
| `RewardTransaction` | `reward_transactions` | The immutable reward ledger (one per recycled submission) |

### 2.3 What the Database Does *Not* Store

Consistent with the platform's separation of concerns, the relational store deliberately **does not** hold: AI models or inference artefacts ([02]–[04]), digital-passport documents or the append-only ledger, or blockchain state ([05]). Where those subsystems need durable anchoring, they use their own stores or the on-chain ledger — the PostgreSQL database is the transactional operational record only. The `Submission` table carries denormalized sustainability outputs (`co2Saved`, `energySaved`, `landfillDiverted`) computed by the reward service, but the computation itself belongs to the application, not the database.

---

## 3. Layered Persistence Architecture

The database sits at the base of the same strict layering the backend uses. Access flows in exactly one direction, and each layer may only speak to the one beneath it.

**Overall Persistence Architecture Diagram**

```
┌──────────────────────────────────────────────────────────────────────┐
│  APPLICATION SERVICES  (business logic, framework-agnostic)           │
│  auth · submission · rewards · users        [07 — Backend API Arch.]  │
│  depend on repository INTERFACES only — never import Prisma           │
└─────────────────────────────────┬────────────────────────────────────┘
                                   │  UserRepository · SubmissionRepository
                                   │  RewardRepository · RefreshTokenRepository
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│  REPOSITORY LAYER   (src/modules/*/**.repository.ts)                  │
│  the ONLY callers of Prisma · select projections · Record mapping     │
└─────────────────────────────────┬────────────────────────────────────┘
                                   │  prisma.<model>.<operation>()
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│  PRISMA CLIENT   (src/infrastructure/prisma/prisma.client.ts)         │
│  single lazy singleton · $queryRaw ping · $transaction · $disconnect  │
└─────────────────────────────────┬────────────────────────────────────┘
                                   │  parameterized SQL over a connection pool
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│  POSTGRESQL   (5 tables · 3 enums · FKs · unique + secondary indexes) │
│  physical schema materialized by Prisma Migrate                       │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.1 The Boundary Rule

Every repository file states the invariant in a header comment: *"Repositories are the only place Prisma is used … Services depend on these interfaces, never on Prisma directly."* This document's concern — everything from the repository's Prisma call downward — is precisely the shaded lower half of that stack. The upper half (controllers, request handling) is [07 — Backend API Architecture].

### 3.2 Why the Boundary Matters for the Data Tier

Because the only entry point to the database is the Prisma Client singleton, and the only callers of that client are repositories, the database has a **small, auditable surface**. There is no ambient SQL scattered through the codebase; every query is a named repository method with a fixed projection. This is what makes the query patterns (§13), the index strategy (§10), and the transaction boundaries (§12) analysable at all.

---

## 4. Prisma Architecture

Prisma is used in three distinct capacities, each backed by a different part of the toolchain.

**Prisma Layer Diagram**

```
                         backend/prisma/schema.prisma
                    (single declarative source of truth)
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
 ┌─────────────────┐      ┌──────────────────┐      ┌──────────────────┐
 │ prisma generate │      │  prisma migrate  │      │   seed (tsx)     │
 │                 │      │                  │      │                  │
 │ → @prisma/client│      │ → prisma/        │      │ prisma/seed.ts   │
 │   typed client  │      │   migrations/*.sql│      │ upsert roles+users│
 │   + model types │      │ → migration_lock │      │                  │
 └────────┬────────┘      └─────────┬────────┘      └────────┬─────────┘
          │                         │                        │
          ▼                         ▼                        ▼
 ┌─────────────────┐      ┌──────────────────┐      ┌──────────────────┐
 │ RUNTIME         │      │ SCHEMA STATE      │      │ REFERENCE DATA   │
 │ getPrismaClient │      │ applied to the    │      │ 5 roles + 5 demo │
 │ (singleton)     │      │ PostgreSQL DB     │      │ accounts         │
 └─────────────────┘      └──────────────────┘      └──────────────────┘
```

### 4.1 Schema Definition (`schema.prisma`)

The schema declares the generator (`prisma-client-js`), the datasource (`postgresql`, URL from `env("DATABASE_URL")`), the 5 models, and the 3 enums. Models use Prisma attributes that map directly onto PostgreSQL DDL: `@id`, `@default(uuid())`, `@unique`, `@default(now())`, `@updatedAt`, `@relation(...)`, `@@index([...])`, and `@@map("...")`. There is no `@@schema` or multi-schema directive — everything lives in the default `public` schema (per the `?schema=public` in the connection string, §19).

### 4.2 Client Generation

`prisma generate` (invoked standalone via `npm run prisma:generate`, and as the first step of `npm run build`) produces the typed `@prisma/client`. The generated types — `PrismaClient`, model types, and the enums `UserRole`, `SubmissionStatus`, `RewardReason` — are imported across the backend and are the same enum values the services switch on. Generating the client is a build-time prerequisite, which is why `build` runs `prisma generate` before `tsc`.

### 4.3 The Runtime Client (`prisma.client.ts`)

At runtime a **single lazy `PrismaClient` instance** is exposed by `getPrismaClient()` in `src/infrastructure/prisma/prisma.client.ts`:

```ts
let prismaClient: PrismaClient | undefined;
export function getPrismaClient(): PrismaClient {
  prismaClient ??= new PrismaClient();
  return prismaClient;
}
```

This file — detailed as infrastructure in [07 — Backend API Architecture] — is the *only* place a `PrismaClient` is constructed for the application (the seed script constructs its own, separate instance for offline use). It also owns `pingDatabase()` (a `SELECT 1` readiness probe) and `disconnectPrisma()` (graceful pool teardown on shutdown). The connection is lazy: no database is contacted until the first query.

### 4.4 Prisma ↔ PostgreSQL Type Mapping

The schema's field types map to PostgreSQL column types as materialized in the migrations:

| Prisma type | PostgreSQL type (from migration DDL) |
|---|---|
| `String` / `String?` | `TEXT` |
| `String[]` | `TEXT[]` (default `ARRAY[]::TEXT[]`) |
| `Boolean` | `BOOLEAN` |
| `Int` | `INTEGER` |
| `Float` | `DOUBLE PRECISION` |
| `DateTime` | `TIMESTAMP(3)` |
| `Json` / `Json?` | `JSONB` |
| `enum` | native PostgreSQL `ENUM` type |

UUID primary keys are declared `@default(uuid())`, meaning the **UUID is generated by Prisma Client at insert time**, and stored in a `TEXT` column (not a native `uuid` column) — as confirmed by the `"id" TEXT NOT NULL` columns in every `CREATE TABLE`.

---

## 5. PostgreSQL Architecture

### 5.1 Engine Choice

PostgreSQL is selected as the sole datastore (`provider = "postgresql"`), pinned in `migration_lock.toml` (`provider = "postgresql"`), which prevents accidental cross-provider migration drift. The choice is well matched to the workload: strong relational integrity, native enum types, array columns (`imageUrls TEXT[]`), `JSONB` for the semi-structured `materialRecovery` breakdown, and transactional guarantees for the reward ledger.

### 5.2 Physical Schema

The database is a single logical schema (`public`) containing five tables and three enum types. Every table has:

- A `TEXT` primary key holding an application-generated UUID (`*_pkey`).
- `createdAt TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP` (except `RewardTransaction`, which has `createdAt` but no `updatedAt` — it is an append-only ledger).
- `updatedAt TIMESTAMP(3)` maintained by Prisma's `@updatedAt` on the mutable entities (`Role`, `User`, `Submission`).

### 5.3 Native Enum Types

Three PostgreSQL `ENUM` types are created by migrations and used as column types:

- `UserRole` — `ADMIN, GOVERNMENT, RECYCLER, COLLECTOR, CONSUMER`
- `SubmissionStatus` — `PENDING, ASSIGNED, ACCEPTED, IN_PROGRESS, COLLECTED, RECYCLING, RECYCLED, COMPLETED, REJECTED`
- `RewardReason` — `RECYCLING, BONUS, CAMPAIGN, ADJUSTMENT, REDEMPTION`

Using native enums (rather than free-text with a check constraint) means the database itself rejects any status or role outside the allowed set — an integrity guarantee that complements the application-level state machine in [07 — Backend API Architecture].

### 5.4 Connection Pooling

Connections are managed by Prisma's built-in pool over the single client instance. Because the client is a process-wide singleton and lazily connected, each backend instance maintains one pool; horizontal scaling means multiple pools, one per instance (a scaling consideration noted in §23).

---

## 6. Schema Organization

### 6.1 File Layout

```
backend/prisma/
├── schema.prisma          # the declarative source of truth (5 models, 3 enums)
├── seed.ts                # idempotent reference-data + demo-account seeding
├── migration_lock.toml    # provider pin: postgresql
└── migrations/
    ├── 20260721114642_init_auth/
    ├── 20260721120341_role_enum/
    ├── 20260721200918_add_refresh_tokens/
    ├── 20260722120000_add_submissions/
    ├── 20260722130000_add_recycler_workflow/
    └── 20260724160937_add_rewards_engine/
```

### 6.2 Model → Table Naming

Models are PascalCase in Prisma and mapped to snake_case plural tables via `@@map`:

| Prisma model | `@@map` physical table |
|---|---|
| `Role` | `roles` |
| `User` | `users` |
| `RefreshToken` | `refresh_tokens` |
| `Submission` | `submissions` |
| `RewardTransaction` | `reward_transactions` |

Field names remain camelCase at the column level (Prisma quotes them, e.g. `"roleId"`, `"tokenHash"`, `"assignedCollectorId"`), so the physical columns are quoted mixed-case identifiers — visible directly in the migration DDL.

### 6.3 Logical Grouping

The five models fall into three cohesive concerns:

- **Identity & access:** `Role`, `User`, `RefreshToken` — who a user is, what they may do, and their live sessions.
- **Operational lifecycle:** `Submission` — the central e-waste record and its full state machine.
- **Incentive ledger:** `RewardTransaction` (plus the denormalized `greenCoins` on `User` and sustainability columns on `Submission`) — the immutable reward history.

---

## 7. Entity Model

Every field below is taken verbatim from `schema.prisma`; nothing is added.

### 7.1 `Role` → `roles`

| Field | Type | Attributes |
|---|---|---|
| `id` | `String` | `@id @default(uuid())` |
| `name` | `UserRole` | `@unique` |
| `description` | `String?` | |
| `createdAt` | `DateTime` | `@default(now())` |
| `updatedAt` | `DateTime` | `@updatedAt` |
| `users` | `User[]` | reverse relation |

Reference data: exactly five rows, one per `UserRole` value, seeded (§16). `name` is unique, so a role enum value can exist at most once.

### 7.2 `User` → `users`

| Field | Type | Attributes / notes |
|---|---|---|
| `id` | `String` | `@id @default(uuid())` |
| `fullName` | `String` | |
| `email` | `String` | `@unique` |
| `passwordHash` | `String` | bcrypt hash — never a plaintext password |
| `phone` | `String?` | |
| `address` | `String?` | |
| `region` | `String?` | |
| `emailVerified` | `Boolean` | `@default(false)` |
| `isActive` | `Boolean` | `@default(true)` |
| `lastLogin` | `DateTime?` | |
| `roleId` | `String` | FK → `roles.id` |
| `greenCoins` | `Int` | `@default(0)` — denormalized reward balance |
| `createdAt` / `updatedAt` | `DateTime` | `@default(now())` / `@updatedAt` |

Relations: `role` (many-to-one), `refreshTokens`, `rewardTransactions`, and three distinct submission relations (`submissions` as owner, `collectedSubmissions`, `recycledSubmissions`). Indexed on `roleId`.

### 7.3 `RefreshToken` → `refresh_tokens`

| Field | Type | Attributes / notes |
|---|---|---|
| `id` | `String` | `@id @default(uuid())` |
| `tokenHash` | `String` | `@unique` — the token is stored hashed, never raw |
| `userId` | `String` | FK → `users.id`, `onDelete: Cascade` |
| `expiresAt` | `DateTime` | absolute expiry |
| `revokedAt` | `DateTime?` | null ⇒ still live; set ⇒ rotated/revoked |
| `createdAt` | `DateTime` | `@default(now())` |

No `updatedAt`: a token is created, optionally revoked once, then expires — it is not "edited". Indexed on `userId`.

### 7.4 `Submission` → `submissions`

The central lifecycle entity. Fields group into four phases:

**Intake (consumer-provided):** `id`, `userId` (FK), `category`, `description?`, `estimatedWeight Float`, `address`, `latitude Float`, `longitude Float`, `imageUrls String[] @default([])`.

**Lifecycle state:** `status SubmissionStatus @default(PENDING)`, `assignedCollectorId String?`, `assignedRecyclerId String?`, `pickupScheduledAt DateTime?`, `completedAt DateTime?`, `createdAt`, `updatedAt`.

**Recycler recovery (added later, §15):** `materialRecovery Json?` (JSONB breakdown), `processingStartedAt DateTime?`, `recoveredWeight Float?`, `recycledAt DateTime?`, `recyclerNotes String?`.

**Sustainability & reward outputs (added with the rewards engine):** `co2Saved Float?`, `energySaved Float?`, `landfillDiverted Float?`, `rewardIssued Boolean @default(false)`.

Relations: `user` (owner, `SubmissionOwner`), `assignedCollector` (`SubmissionCollector`), `assignedRecycler` (`SubmissionRecycler`), and an optional one-to-one `rewardTransaction`. Indexed on `userId`, `status`, `assignedCollectorId`, `assignedRecyclerId`.

### 7.5 `RewardTransaction` → `reward_transactions`

| Field | Type | Attributes / notes |
|---|---|---|
| `id` | `String` | `@id @default(uuid())` |
| `userId` | `String` | FK → `users.id` |
| `submissionId` | `String` | `@unique` FK → `submissions.id` |
| `points` | `Int` | GreenCoins awarded |
| `reason` | `RewardReason` | why the award was made |
| `createdAt` | `DateTime` | `@default(now())` |

No `updatedAt` — the ledger is append-only. The `@unique` on `submissionId` is the structural guarantee that **a submission can be rewarded at most once** (§9, §12).

---

## 8. Relationships

**Entity Relationship Overview Diagram**

```
                     ┌───────────────┐
                     │     roles     │
                     │  (5 seeded)   │
                     └───────┬───────┘
                             │ 1
                             │  roleId  (RESTRICT)
                             │ *
                     ┌───────▼───────────────────────────────┐
                     │                users                   │
                     │  greenCoins (denormalized balance)     │
                     └───┬─────────┬───────────┬──────────┬───┘
             owner 1│*   │ 1     * │ 1       * │ 1      * │ 1
        (SubmissionOwner)│         │           │          │
                     │   │         │           │          │
        ┌────────────▼┐  │  ┌──────▼───────┐   │   ┌──────▼──────────────┐
        │ submissions │  │  │refresh_tokens│   │   │ reward_transactions │
        │  status FSM │  │  │  (CASCADE)   │   │   │   (append-only)     │
        └──┬───────┬──┘  │  └──────────────┘   │   └──────────┬──────────┘
           │       │     │                     │              │ 1
   collector│    recycler│                     │              │ submissionId
    (SET NULL)   (SET NULL)                    └──────────────┘  @unique
           │       │                             userId (RESTRICT)
           └───────┴─── assignedCollectorId / assignedRecyclerId → users
                        (nullable, SET NULL on delete)

        submissions 1 ─── 0..1 reward_transactions   (submissionId @unique)
```

### 8.1 One-to-Many

- **`roles` → `users`** — a role has many users; each user has exactly one role (`roleId`, non-null).
- **`users` → `refresh_tokens`** — a user has many session tokens.
- **`users` → `reward_transactions`** — a user has many reward entries.
- **`users` → `submissions`** — three separate collections: as **owner** (`SubmissionOwner`), as **collector** (`SubmissionCollector`), and as **recycler** (`SubmissionRecycler`). The three named relations let one `users` table serve three distinct roles on the same `submissions` row without ambiguity.

### 8.2 One-to-One

- **`submissions` → `reward_transactions`** — optional (`0..1`). Enforced physically by `reward_transactions.submissionId @unique`. This is the only 1:1 relation and the backbone of reward idempotency.

### 8.3 Self-Referencing Through `users`

A single `submissions` row can reference up to three different `users` rows (owner, collector, recycler). The two assignment references are nullable and independently settable as the submission moves through its lifecycle.

---

## 9. Constraints

All constraints below are declared in `schema.prisma` and materialized in the migration DDL.

### 9.1 Primary Keys

Every table has a single-column `TEXT` primary key (`*_pkey`) holding an application-generated UUID.

### 9.2 Unique Constraints

| Table | Column | Constraint | Purpose |
|---|---|---|---|
| `roles` | `name` | `Role_name_key` (→ `roles_name_key`) | one row per role enum value |
| `users` | `email` | `users_email_key` | one account per email |
| `refresh_tokens` | `tokenHash` | `refresh_tokens_tokenHash_key` | no two live tokens share a hash |
| `reward_transactions` | `submissionId` | `reward_transactions_submissionId_key` | ≤ 1 reward per submission |

### 9.3 Foreign Keys and Referential Actions

| FK | References | On delete | On update |
|---|---|---|---|
| `users.roleId` | `roles.id` | `RESTRICT` | `CASCADE` |
| `refresh_tokens.userId` | `users.id` | `CASCADE` | `CASCADE` |
| `submissions.userId` | `users.id` | `RESTRICT` | `CASCADE` |
| `submissions.assignedCollectorId` | `users.id` | `SET NULL` | `CASCADE` |
| `submissions.assignedRecyclerId` | `users.id` | `SET NULL` | `CASCADE` |
| `reward_transactions.userId` | `users.id` | `RESTRICT` | `CASCADE` |
| `reward_transactions.submissionId` | `submissions.id` | `RESTRICT` | `CASCADE` |

The referential actions encode deliberate policy:

- **`RESTRICT`** on `users.roleId`, `submissions.userId`, and both `reward_transactions` FKs: you cannot delete a role that has users, a user who owns submissions, or a user/submission that has a reward ledger entry. History and ownership are protected.
- **`CASCADE`** on `refresh_tokens.userId`: deleting a user cleans up their sessions automatically — sessions are disposable.
- **`SET NULL`** on the two assignment FKs: removing a collector or recycler account detaches them from submissions without destroying the submission record; the work item survives, merely unassigned.

### 9.4 Not-Null and Defaults

Non-null columns without a default (e.g. `users.email`, `users.passwordHash`, `submissions.category`, `submissions.estimatedWeight`) must be supplied on insert. Defaults (`emailVerified=false`, `isActive=true`, `greenCoins=0`, `status=PENDING`, `rewardIssued=false`, `imageUrls=[]`, `createdAt=now()`) let callers omit them safely.

---

## 10. Index Strategy

**Index inventory (from schema `@@index`/`@unique` and migration DDL):**

| Table | Index | Kind | Rationale |
|---|---|---|---|
| `roles` | `roles_name_key` | unique | role lookup by enum value (§16 seed, auth role resolution) |
| `users` | `users_email_key` | unique | login by email (the hot auth path) |
| `users` | `users_roleId_idx` | secondary | filter/join users by role |
| `refresh_tokens` | `refresh_tokens_tokenHash_key` | unique | O(1) token verification on refresh |
| `refresh_tokens` | `refresh_tokens_userId_idx` | secondary | revoke-all-for-user, list a user's sessions |
| `submissions` | `submissions_userId_idx` | secondary | "my submissions" listing |
| `submissions` | `submissions_status_idx` | secondary | queue views by lifecycle state |
| `submissions` | `submissions_assignedCollectorId_idx` | secondary | a collector's assigned pickups |
| `submissions` | `submissions_assignedRecyclerId_idx` | secondary | a recycler's assigned items |
| `reward_transactions` | `reward_transactions_submissionId_key` | unique | idempotency guard + 1:1 lookup |
| `reward_transactions` | `reward_transactions_userId_idx` | secondary | a user's reward history |

### 10.1 Design Notes

- **Every foreign key that is queried is indexed.** All four `submissions` FK/filter columns, both `refresh_tokens`/`reward_transactions` `userId` FKs, and `users.roleId` have secondary indexes, so the common "find children of X" queries avoid sequential scans.
- **Unique indexes double as lookup indexes.** `email`, `tokenHash`, and `submissionId` each serve both as an integrity constraint and as the access path for the query that uses them.
- **No composite indexes exist yet.** All indexes are single-column. Multi-column filters (e.g. status + collector) currently rely on the single-column indexes; composite indexes are an identified extension point (§22, §23).

---

## 11. Repository Integration

Repositories are the sole callers of the Prisma Client. They translate between the database's row shape and the domain `Record` types the services consume, applying a fixed `select` projection to each query.

**Repository Flow Diagram**

```
 service method                 repository method                Prisma / PostgreSQL
 ─────────────                  ─────────────────                ───────────────────
 authService.login(email)
        │
        ▼
 UserRepository.findByEmail(email)
        │   prisma.user.findUnique({
        │     where: { email },
        │     select: userSelect      ◄── fixed projection (no SELECT *)
        │   })
        │                                   ──►  SELECT <userSelect cols>
        │                                        FROM users
        │                                        WHERE email = $1   (unique idx)
        │   maps row → UserRecord
        ▼
 returns UserRecord (or null)
```

### 11.1 Projections (`select`)

Each repository defines a constant `select` object — e.g. `userSelect` in `auth.repository.ts` and `submissionSelect` in `submission.repository.ts`. Queries pass this projection so the database returns only the needed columns, never `SELECT *`. This keeps the wire payload stable and prevents accidental leakage of columns like `passwordHash` where it is not wanted.

### 11.2 The Four Repositories

| Repository | Model(s) | Representative methods |
|---|---|---|
| `UserRepository` | `User`, `Role` | `findByEmail`, `findById`, `create`, `updateLastLogin`, `findRoleId`, `findByRole` |
| `RefreshTokenRepository` | `RefreshToken` | `store`, `findByHash`, `revokeByHash`, `revokeAllForUser` |
| `SubmissionRepository` | `Submission` | list (paginated), `findById`, `create`, update (via `toUpdateData`) |
| `RewardRepository` | `RewardTransaction`, `User`, `Submission` | `executeRewardTransaction` (atomic, §12) |

### 11.3 Update Hygiene

The submission repository builds update payloads with a `toUpdateData()` helper that **strips `undefined` keys** so a partial update never overwrites unspecified columns, and maps a null JSON to `Prisma.JsonNull` so `materialRecovery` can be explicitly cleared. This preserves the "modify only what was provided" contract at the persistence boundary.

---

## 12. Transactions

### 12.1 The One Multi-Table Atomic Operation

The reward flow is the only place multiple tables must change together, and it is the only interactive transaction in the codebase. `RewardRepository.executeRewardTransaction` wraps three writes in `prisma.$transaction`:

**Transaction Flow Diagram**

```
 rewardService.issueReward(submission)
        │
        ▼
 prisma.$transaction(async (tx) => {
        │
        │  ① tx.rewardTransaction.create({            ← insert ledger row
        │        data: { userId, submissionId,           (submissionId UNIQUE ⇒
        │                points, reason }                  duplicate ⇒ P2002 abort)
        │     })
        │
        │  ② tx.user.update({                          ← increment balance
        │        where: { id: userId },
        │        data:  { greenCoins: { increment: points } }
        │     })
        │
        │  ③ tx.submission.update({                    ← flip idempotency flag
        │        where: { id: submissionId },
        │        data:  { rewardIssued: true, ...sustainability }
        │     })
 })     │
        ▼
   all three commit together, or none do
```

If any step throws — most importantly a `P2002` unique-violation on `reward_transactions.submissionId` when a reward already exists — the whole transaction rolls back. The ledger insert, the balance increment, and the `rewardIssued` flag can never diverge.

### 12.2 Why a Transaction Is Required Here

Without atomicity, a crash between steps ② and ③ would credit GreenCoins while leaving `rewardIssued=false`, allowing a double reward on retry; a crash between ① and ② would record a ledger entry with no balance change. The transaction plus the `submissionId` unique constraint together make reward issuance exactly-once.

### 12.3 Elsewhere: Single-Statement Atomicity

Every other write is a single Prisma statement and therefore already atomic at the row level — `create`, `update`, `updateMany` (e.g. `revokeAllForUser` sets `revokedAt` on all a user's live tokens in one statement). No explicit transaction is needed for those.

---

## 13. Query Patterns

All queries are named repository methods with fixed projections. The recurring shapes are shown below, preceded by the end-to-end path any single query travels from a repository call down to a physical read and back.

**Database Access Flow Diagram**

```
 repository method
   prisma.<model>.<op>({ where, select, skip?, take?, orderBy? })
        │
        ▼
 getPrismaClient()  ── lazy singleton ──►  connection pool (one per instance)
        │                                        │
        │                                        ▼
        │                         parameterized SQL ($1,$2…)  ── prevents injection
        │                                        │
        │                                        ▼
        │                         PostgreSQL planner
        │                           ├─ unique/secondary index?  ─► index scan
        │                           └─ else                     ─► seq scan
        │                                        │
        │                                        ▼
        │                         rows (projected columns only)
        ▼                                        │
 map row → domain Record  ◄──────────────────────┘
        │
        ▼
 return Record | Record[] | Page<Record>   ─►  service layer
```

The recurring query shapes:

### 13.1 Unique Lookups (index-backed point reads)

- `findUnique({ where: { email } })` — login.
- `findUnique({ where: { tokenHash } })` — refresh-token verification.
- `findUnique({ where: { id } })` — entity fetch by primary key.

Each rides a unique index (`users_email_key`, `refresh_tokens_tokenHash_key`, `*_pkey`), so these are O(log n) point reads.

### 13.2 Filtered Lists

- Submissions by owner (`where: { userId }`), by `status`, by `assignedCollectorId`, or by `assignedRecyclerId` — each backed by a dedicated secondary index (§10).
- Users by role (`findByRole`) — backed by `users_roleId_idx`.

### 13.3 Scoped Mutations

- `updateMany({ where: { userId, revokedAt: null }, data: { revokedAt } })` — bulk session revocation in a single statement.
- `update({ where: { id }, data: increment/flag })` — targeted field updates (GreenCoins increment, `rewardIssued` flip, `lastLogin` stamp).

### 13.4 Projection Discipline

Because every read passes an explicit `select`, the executed SQL projects a stable, minimal column list. This is what makes the read patterns predictable and index-friendly, and it is enforced at the only layer that talks to Prisma (§11).

---

## 14. Pagination Strategy

### 14.1 Offset Pagination via `toPage()`

Submission listings use classic offset pagination. The repository exposes a `toPage()` helper that combines a **count** query with a **windowed find** using Prisma's `skip`/`take`:

```
 page, pageSize  ─►  skip = (page - 1) * pageSize
                     take = pageSize
                     orderBy = { createdAt: desc }   (newest first)

 total   = prisma.submission.count({ where })
 rows    = prisma.submission.findMany({ where, skip, take, orderBy, select })

 result  = { data: rows, page, pageSize, total,
             totalPages = ceil(total / pageSize) }
```

The same `where` filter is applied to both the count and the windowed read, so the reported `total` is consistent with the filtered result set. Ordering is deterministic (`createdAt` descending) so pages are stable within a snapshot.

### 14.2 Trade-off

Offset pagination is simple and supports random page access, at the cost of a full `COUNT` per request and increasing `skip` cost deep into large result sets. For the current data volumes this is appropriate; cursor (keyset) pagination is a documented future option (§24) if submission volumes grow.

---

## 15. Migration Strategy

The physical schema is produced entirely by Prisma Migrate. Six migrations, applied in timestamp order, reconstruct the database deterministically.

**Migration Lifecycle Diagram**

```
 schema.prisma changed
        │
        ▼
 prisma migrate dev --name <change>
        │
        ├─► diff schema vs. migration history
        ├─► emit prisma/migrations/<ts>_<name>/migration.sql
        └─► apply SQL to the dev database
                     │
                     ▼   (CI / production)
        prisma migrate deploy  ──►  replay every pending migration.sql
                                    in order, tracked in _prisma_migrations
```

### 15.1 The Six Migrations (real lineage)

| # | Migration | What it does |
|---|---|---|
| 1 | `20260721114642_init_auth` | Creates `Role` and `User` (originally PascalCase tables, `name` as `TEXT`); unique indexes on `Role.name` and `User.email`; FK `User.roleId → Role.id` `ON DELETE RESTRICT`. |
| 2 | `20260721120341_role_enum` | Introduces `CREATE TYPE "UserRole"`; **drops and recreates** `Role`/`User` as snake_case `roles`/`users` with `name` typed `"UserRole"`; adds `users_roleId_idx`. Carries a data-loss warning (see §15.2). |
| 3 | `20260721200918_add_refresh_tokens` | Creates `refresh_tokens`; unique `tokenHash`; `userId` index; FK → `users.id` `ON DELETE CASCADE`. |
| 4 | `20260722120000_add_submissions` | `CREATE TYPE "SubmissionStatus"` (initially **without** `RECYCLING`); creates `submissions` (`imageUrls TEXT[]`, `Float`→`DOUBLE PRECISION`); four secondary indexes; FKs `userId` `RESTRICT`, `assignedCollectorId`/`assignedRecyclerId` `SET NULL`. |
| 5 | `20260722130000_add_recycler_workflow` | `ALTER TYPE "SubmissionStatus" ADD VALUE 'RECYCLING' BEFORE 'RECYCLED'`; adds recovery columns (`materialRecovery JSONB`, `processingStartedAt`, `recoveredWeight`, `recycledAt`, `recyclerNotes`). |
| 6 | `20260724160937_add_rewards_engine` | `CREATE TYPE "RewardReason"`; adds `submissions` sustainability columns + `rewardIssued`; adds `users.greenCoins`; creates `reward_transactions` with unique `submissionId`, `userId` index, and `RESTRICT` FKs. |

### 15.2 Notable Evolutionary Events

- **Enum conversion with data loss (migration 2).** Converting `name` from free text to the `UserRole` enum required dropping and recreating the auth tables; the generated SQL includes Prisma's explicit data-loss warning. This is safe pre-production (the tables were empty/seed-only) and is preserved honestly in history rather than being rewritten.
- **In-place enum extension (migration 5).** `RECYCLING` was inserted into an existing enum with `ADD VALUE ... BEFORE 'RECYCLED'`, extending the state machine without recreating the type — the correct additive approach for a live enum.

### 15.3 Provider Lock

`migration_lock.toml` pins `provider = "postgresql"`. Prisma refuses to run migrations against a different provider, preventing silent drift from PostgreSQL-specific DDL (enums, `TEXT[]`, `JSONB`).

---

## 16. Seed Strategy

### 16.1 Purpose and Registration

`prisma/seed.ts` (run via `prisma db seed`, registered as `"prisma": { "seed": "tsx prisma/seed.ts" }`) populates the database with the reference roles and a set of demo accounts. It constructs its **own** `PrismaClient` (separate from the runtime singleton, §4.3) and disconnects in a `finally` block.

### 16.2 Idempotent Upserts

Seeding is safe to run repeatedly. It uses `upsert` throughout:

```
 for each of the 5 roles (ADMIN, GOVERNMENT, RECYCLER, COLLECTOR, CONSUMER):
     prisma.role.upsert({ where: { name }, update: {...}, create: {...} })

 for each of the 5 demo users:
     resolve roleId by role name
     prisma.user.upsert({
       where:  { email },
       update: {...},
       create: { ..., emailVerified: true, isActive: true }
     })
```

Because `roles.name` and `users.email` are unique, the `where` clause matches at most one row, so a second run updates rather than duplicates.

### 16.3 Credential Handling

The seed hashes the shared demo password with **bcrypt at `SALT_ROUNDS = 12`** before insert — the database only ever receives `passwordHash`, never a plaintext password. This mirrors the production auth flow ([07 — Backend API Architecture]) and honours the repository security rules (no secrets at rest in plaintext). The demo accounts are `admin@`, `government@`, `collector@`, `recycler@`, and `consumer@ecotrace.com`, one per role.

### 16.4 Reference Data vs. Operational Data

Only the five roles are true reference data required for the system to function (a user cannot be created without a valid `roleId`). The five demo users are convenience fixtures for development and review, not a production requirement.

---

## 17. Data Integrity

Integrity is enforced in depth, at the layer closest to the data:

### 17.1 Database-Level Guarantees

- **Referential integrity** — every FK (§9.3) is a real PostgreSQL constraint; orphaned `refresh_tokens`, `submissions`, or `reward_transactions` cannot exist.
- **Uniqueness** — `email`, `tokenHash`, `roles.name`, and `reward_transactions.submissionId` are enforced by unique indexes; duplicates are rejected with `P2002`.
- **Enum domains** — `status`, `role name`, and `reason` columns are native enums; out-of-range values are impossible.
- **Not-null** — required columns cannot be null; the database refuses incomplete rows.

### 17.2 Application-Level Complements

- **Reward idempotency** — the `$transaction` + `submissionId @unique` pair guarantees exactly-once reward issuance (§12).
- **State machine** — the ordered `SubmissionStatus` transitions are governed by the submission service ([07]); the enum bounds the *set* of legal states, the service governs legal *transitions*.
- **Update masking** — `toUpdateData()` prevents partial updates from nulling untouched columns (§11.3).

### 17.3 Denormalization Under Control

`users.greenCoins` duplicates the sum of a user's `reward_transactions.points`, and `submissions.co2Saved`/`energySaved`/`landfillDiverted` cache computed sustainability figures. These denormalizations are written **only** inside the reward transaction, so the cached values and the ledger are always mutated together and stay consistent.

---

## 18. Error Handling

### 18.1 Prisma Error Surfaces

Database errors reach the application as typed Prisma errors, chiefly:

- **`P2002`** — unique constraint violation (duplicate email, or a second reward for the same submission). The reward path relies on this as its concurrency guard; the auth path surfaces it as a registration conflict.
- **`P2003`** — foreign-key violation (referencing a non-existent `roleId`, `userId`, or `submissionId`).
- **`P2025`** — record required by an `update`/`delete` not found.

### 18.2 Translation at the Boundary

Repositories and services translate these low-level failures into the API's structured error envelope ([07 — Backend API Architecture]); this document's concern is only that the constraints exist to be violated. The database is the last line of defence: even if a validation layer were bypassed, the unique/FK/enum/not-null constraints reject the bad write.

### 18.3 Connectivity Failures

`pingDatabase()` runs `SELECT 1` and returns a boolean without throwing, so a database outage surfaces as a clean "not ready" health signal rather than an unhandled exception. Graceful shutdown calls `disconnectPrisma()` to drain the pool.

---

## 19. Configuration

### 19.1 Connection String

The datasource reads a single environment variable:

```prisma
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}
```

`backend/.env.example` documents the shape:

```
DATABASE_URL=postgresql://ecotrace:ecotrace@localhost:5432/ecotrace?schema=public
```

The `?schema=public` confirms the single-schema layout (§4.1). The credentials in `.env.example` are placeholders for local development; real credentials live only in the environment, never in the repository (per the security rules in CLAUDE.md).

### 19.2 Toolchain Configuration

- **Generation** — `npm run prisma:generate` / the `build` step run `prisma generate`.
- **Seeding** — `package.json` `prisma.seed = "tsx prisma/seed.ts"`.
- **Provider pin** — `prisma/migrations/migration_lock.toml`.

No connection-pool tuning parameters are set explicitly; Prisma's defaults apply (§5.4, §20).

---

## 20. Performance

### 20.1 Read Performance

- **Point reads** (login, token verify, fetch-by-id) are index-backed and O(log n) (§10, §13.1).
- **Filtered lists** all hit a dedicated secondary index; there are no known unindexed filter paths on the hot tables.
- **Explicit projections** minimize row width on the wire (§11.1).

### 20.2 Write Performance

- Most writes are single-statement and row-atomic.
- The reward `$transaction` performs three writes but touches indexed rows by primary key / unique key, keeping the transaction short and lock scope small (§12).

### 20.3 Known Cost Centres

- **Offset pagination** issues a `COUNT` per page and grows more expensive at deep offsets (§14.2).
- **Denormalized aggregates** trade a small write-time cost (updating `greenCoins` in the reward transaction) for cheap reads of a user's balance — a deliberate read-optimization.
- **UUID `TEXT` keys** are wider than native `uuid`/`bigint` keys, marginally increasing index size; chosen for portability and application-side generation (§25).

### 20.4 Connection Pooling

One pool per backend instance over the lazy singleton (§5.4). Under horizontal scaling the aggregate connection count is (instances × pool size), which is the primary database-side scaling parameter to watch (§23).

---

## 21. Testing

### 21.1 Where the Database Is Exercised

The persistence layer is validated indirectly through the backend's service and repository tests ([07 — Backend API Architecture]) and directly through the migration/seed toolchain:

- **Migration replay** — `prisma migrate deploy` against a clean database is the definitive test that the six migrations apply cleanly in order and reproduce the schema `prisma generate` expects.
- **Seed idempotency** — running `prisma db seed` twice must leave exactly five roles and five demo users, proving the `upsert` logic (§16.2).
- **Schema/client agreement** — `prisma generate` failing would indicate the schema and client have drifted; it runs as the first `build` step, so a broken schema breaks the build.

### 21.2 Readiness Probe as a Test Surface

`pingDatabase()` provides a runtime assertion that the connection and credentials are valid — usable by health checks and smoke tests to confirm the data tier is reachable before traffic is served.

### 21.3 Determinism

Because the schema is migration-driven and the seed is idempotent, a test database can be reconstructed deterministically from source: `migrate deploy` → `db seed`. There are no hand-applied DDL steps that would make a test environment diverge from production.

---

## 22. Extension Points

The schema is structured so that the most likely growth is additive:

- **New enum values** — additional `SubmissionStatus`, `RewardReason`, or `UserRole` members can be added with `ALTER TYPE ... ADD VALUE`, exactly as `RECYCLING` was (§15.2), without table rewrites.
- **New reward reasons already reserved** — `RewardReason` already declares `BONUS`, `CAMPAIGN`, `ADJUSTMENT`, and `REDEMPTION` beyond `RECYCLING`, so incentive features can be added without a migration.
- **Composite indexes** — multi-column access patterns (e.g. `status` + `assignedCollectorId`) can be introduced as `@@index([...])` additions when query profiles justify them (§10.1, §23).
- **New entities** — a new model plus its migration slots into the existing repository/boundary pattern without disturbing existing tables.
- **JSON evolution** — `submissions.materialRecovery` is `JSONB`, so its internal shape can evolve without DDL, while promotion of a stabilized field to a typed column remains a clean future migration.

---

## 23. Current Limitations

Stated honestly, from the implementation as it stands:

- **No composite indexes.** Combined filters rely on single-column indexes; heavy multi-key queue queries may benefit from composite indexes not yet present (§10.1).
- **Offset-only pagination.** No cursor/keyset pagination; deep pages incur growing `skip` and per-page `COUNT` cost (§14.2).
- **UUIDs stored as `TEXT`.** Wider than native `uuid`; a portability/simplicity trade-off, not a tuned choice (§20.3).
- **One pool per instance.** No external pooler (e.g. PgBouncer) is configured; connection count scales linearly with instances (§5.4, §20.4).
- **No soft-delete or partitioning.** Deletes are physical (governed by referential actions); large tables are not partitioned. Adequate at prototype scale, revisited under growth (§24).
- **Denormalized aggregates require discipline.** `greenCoins` and the sustainability columns are correct only because they are written solely inside the reward transaction; any future writer must preserve that invariant (§17.3).

---

## 24. Future Database Evolution

Consistent with the roadmap in [01 — System Architecture], plausible next steps for the data tier — none of which are implemented today — include:

- **Keyset pagination** for high-volume submission feeds, removing deep-offset cost.
- **Composite and partial indexes** informed by production query plans (e.g. partial index on `refresh_tokens` where `revokedAt IS NULL`).
- **Native `uuid` columns** if key width becomes material at scale.
- **External connection pooling** (PgBouncer / a serverless-friendly pooler) to decouple pool size from instance count.
- **Read replicas** for analytics/government reporting reads ([06 — Web Platform Architecture]) without loading the primary.
- **Table partitioning / archival** of historical `submissions` and `reward_transactions` as the ledger grows.
- **Anchoring hooks** — should the platform choose to anchor reward-ledger hashes on-chain ([05 — Blockchain Architecture]), the append-only `reward_transactions` table is the natural source; the relational store would remain the system-of-record.

---

## 25. Design Rationale

Why the database is shaped the way it is:

- **PostgreSQL, single schema.** One capable relational engine covers every requirement — enums, arrays, `JSONB`, transactions, strong constraints — without the operational overhead of multiple stores. Simplicity over premature polyglot persistence.
- **Prisma as the sole gateway.** A single typed client with a repository-only boundary yields an auditable data surface (§3.2) and keeps the ORM replaceable. Services never depend on Prisma types, only on repository interfaces.
- **Migration-driven schema.** The database is reproducible from committed SQL, and its history — including the honest data-loss enum conversion — is recoverable, not folklore.
- **Constraints in the database.** Integrity that must never be violated (uniqueness, FKs, enum domains, one reward per submission) lives in PostgreSQL, so it holds even if application code is wrong or bypassed.
- **UUID, application-generated.** IDs are created by the client at insert time, so an entity's identity is known before it is persisted and does not depend on a database round-trip — convenient for the service layer and for cross-subsystem references.
- **Targeted denormalization.** `greenCoins` and sustainability columns are cached for cheap reads and kept correct by confining their writes to the one reward transaction — a controlled, not accidental, denormalization.
- **Append-only ledger.** `reward_transactions` has no `updatedAt` and a unique `submissionId`; rewards are recorded, never edited, giving an immutable incentive history that complements the auditability goals of [05 — Blockchain Architecture] without putting application data on-chain.

---

## 26. Conclusion

The EcoTrace India database is a deliberately small, strongly-constrained PostgreSQL store fronted exclusively by Prisma and reached only through repositories. Five tables and three enums — reconstructable from six committed migrations and made usable by an idempotent seed — carry identity, sessions, the e-waste submission lifecycle, and an append-only reward ledger. Its integrity is enforced where it matters most: foreign keys, unique constraints, native enums, referential actions, and a one-reward-per-submission guard live in the database itself, with the reward `$transaction` providing exactly-once atomicity across the three tables that must move together.

Every object described here is present in `backend/prisma/schema.prisma`, the migration SQL, the seed, and the Prisma client singleton — nothing is invented. The result is a persistence tier that is auditable, reproducible, and honest about its trade-offs (offset pagination, single-column indexes, `TEXT` UUIDs, one pool per instance), with a clear additive path forward. It is the durable foundation beneath the API ([07]) and the wider platform ([01]–[06]), and it is engineered to the standard EcoTrace India holds itself to for IEEE YESIST 2026: correct, maintainable, and production-minded.

---

*Source of truth: `backend/prisma/schema.prisma`, `backend/prisma/migrations/*`, `backend/prisma/seed.ts`, `backend/prisma/migration_lock.toml`, and `backend/src/infrastructure/prisma/prisma.client.ts`. This document reverse-engineers the database layer only and does not modify Documents 01–07.*
