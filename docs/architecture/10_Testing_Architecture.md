# Testing Architecture

**Version:** 1.0.0  
**Status:** Active  
**Last Updated:** 2026-08-06

**Scope:** Testing and quality-assurance layer only — the test suites, test tooling, and static-analysis configuration that actually exist in the repository (`backend/jest.config.cjs` and `backend/tests/`, `intelligence/device_ai/pyproject.toml` and `intelligence/device_ai/tests/`, the frontend lint/type tooling, and `.github/workflows/backend-ci.yml`).

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Testing Philosophy](#2-testing-philosophy)
3. [Testing Architecture](#3-testing-architecture)
4. [Test Organization](#4-test-organization)
5. [Unit Testing](#5-unit-testing)
6. [Integration Testing](#6-integration-testing)
7. [End-to-End Testing](#7-end-to-end-testing)
8. [AI Engine Testing](#8-ai-engine-testing)
9. [Backend Testing](#9-backend-testing)
10. [Frontend Testing](#10-frontend-testing)
11. [Mock Strategy](#11-mock-strategy)
12. [Dependency Injection](#12-dependency-injection)
13. [Fixtures & Test Data](#13-fixtures--test-data)
14. [Deterministic Testing](#14-deterministic-testing)
15. [Regression Protection](#15-regression-protection)
16. [Static Analysis](#16-static-analysis)
17. [Formatting & Style](#17-formatting--style)
18. [Type Safety](#18-type-safety)
19. [Build Verification](#19-build-verification)
20. [Continuous Integration](#20-continuous-integration)
21. [Quality Gates](#21-quality-gates)
22. [Current Limitations](#22-current-limitations)
23. [Future Testing Evolution](#23-future-testing-evolution)
24. [Design Rationale](#24-design-rationale)
25. [References](#25-references)
26. [Conclusion](#26-conclusion)

---

## 1. Executive Summary

EcoTrace India's quality assurance is built on **two mature, independently-configured automated test suites plus a uniform static-analysis gate**, all verifiable in the repository. This document reverse-engineers exactly that apparatus — it does not describe test infrastructure that is not present.

What exists today:

- **A Jest test suite for the backend.** `backend/tests/` holds **22 test files** — 16 unit specs and 4 integration specs, supported by 3 in-memory repository helpers — run by Jest 29 with `ts-jest`, path-alias mapping, and Supertest for HTTP-level integration ([07 — Backend API Architecture]).
- **A pytest test suite for the AI Device Intelligence Engine.** `intelligence/device_ai/tests/` holds **84 test files** plus a shared `conftest.py`, run by pytest 8 with `pytest-cov` and FastAPI's `TestClient` (over `httpx`), covering every engine, service, route, and the training platform ([03 — Device Intelligence Architecture]).
- **A uniform static-analysis and formatting gate.** The backend uses ESLint 9, Prettier, and `tsc --noEmit`; the AI service uses Ruff, Black, isort, and mypy — each pinned and configured (`eslint.config.mjs`, `pyproject.toml`). Type safety is a first-class gate in both stacks (strict TypeScript, `disallow_untyped_defs` for Python).
- **One CI workflow.** `.github/workflows/backend-ci.yml` runs the backend quality gate (lint → typecheck → format check → test → build) followed by a Docker image build ([09 — Deployment Architecture]).

The design's defining traits — grounded in the code — are **dependency injection for testability** (the backend injects repositories into `createApp()`; the AI service overrides FastAPI dependencies), **deterministic-by-construction tests** (seeded RNG, fixed clocks, mock encoders, in-memory stores), and **no reliance on external systems** (no live database, network, or trained model weights are needed to run either suite).

What does **not** yet exist, stated plainly (and detailed in §22): there is **no frontend test suite** (the frontend ships static analysis only), **no implemented end-to-end tests** (the `testing/{e2e,integration,unit}` directories are empty placeholders), and **CI covers the backend only** — the AI suite and static-analysis tools are run locally, not yet gated in CI. No coverage thresholds are configured, so this document invents none.

---

## 2. Testing Philosophy

The repository's testing approach is consistent across both languages and follows a small set of principles that can be read directly from the configuration and the tests themselves.

**Test Pyramid Diagram**

```
                        ▲  fewer, broader
                        │
        ┌───────────────┴────────────────┐
        │        END-TO-END               │   NOT IMPLEMENTED
        │   testing/e2e (empty)           │   (placeholder dirs only)
        ├─────────────────────────────────┤
        │        INTEGRATION              │   backend: 4 specs
        │  HTTP stack via Supertest /     │   (Supertest + in-memory repos)
        │  FastAPI TestClient             │   AI: route/endpoint specs
        │                                 │   (TestClient + dependency overrides)
        ├─────────────────────────────────┤
        │            UNIT                  │   backend: 16 specs
        │  services · middleware · repos  │   AI: the bulk of 84 specs
        │  pure functions, injected deps  │   (engines, models, parsers, rules)
        └─────────────────────────────────┘
                        │
                        ▼  many, narrow, fast
```

### 2.1 Principles Actually Enforced

- **Fast, hermetic, deterministic.** Every test runs without a network, a real database, or trained model weights. The backend integration tests substitute in-memory repositories; the AI suite degrades to deterministic mock encoders/backends and uses seeded randomness (§11, §14).
- **Test through the seams, not around them.** Both stacks are architected for injection — the backend passes repositories into `createApp()`; the AI service exposes overridable FastAPI dependency providers — so tests exercise real code paths with controlled collaborators (§12).
- **Behaviour over implementation.** Tests assert observable behaviour (HTTP status/body, returned records, engine outputs) and security invariants (e.g. `passwordHash` never appears in a response), not internal call sequences where avoidable.
- **Static analysis is part of testing.** Linting, formatting, and type-checking are treated as quality gates alongside the runtime suites, and are wired into the same local and CI workflows (§16–§18, §21), consistent with the Definition of Done in `CLAUDE.md`.
- **Pinned tooling for reproducibility.** Test and lint tools are version-pinned (`requirements-dev.txt`, `package.json`), so a suite behaves identically on any machine or in CI.

### 2.2 Consistency With the Wider Architecture

This philosophy is the natural consequence of the layering documented elsewhere: the backend's repository boundary ([07], [08 — Database Architecture]) is exactly what makes in-memory substitution possible, and the AI service's settings-driven, mock-capable engines ([02 — AI Platform Architecture], [03 — Device Intelligence Architecture]) are what make the pytest suite runnable without heavy models.

---

## 3. Testing Architecture

**Overall Testing Architecture Diagram**

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                        DEVELOPER / CI ENVIRONMENT                          │
 └──────────────────────────────────────────────────────────────────────────┘
        │                              │                              │
        ▼                              ▼                              ▼
 ┌───────────────┐            ┌───────────────┐              ┌───────────────┐
 │  BACKEND      │            │  AI SERVICE   │              │  FRONTEND     │
 │  (Node/TS)    │            │  (Python)     │              │  (React/TS)   │
 ├───────────────┤            ├───────────────┤              ├───────────────┤
 │ Jest 29       │            │ pytest 8      │              │ (no runtime   │
 │  + ts-jest    │            │  + pytest-cov │              │  test suite)  │
 │  + Supertest  │            │  + httpx      │              │               │
 │ jest.config   │            │ pyproject.toml│              │ static only:  │
 │  .cjs         │            │ conftest.py   │              │  eslint,      │
 ├───────────────┤            ├───────────────┤              │  tsc -b,      │
 │ STATIC GATE:  │            │ STATIC GATE:  │              │  prettier     │
 │  eslint 9     │            │  ruff 0.8.6   │              │               │
 │  prettier     │            │  black 24.10  │              │               │
 │  tsc --noEmit │            │  isort 5.13   │              │               │
 │               │            │  mypy 1.14    │              │               │
 └───────┬───────┘            └───────┬───────┘              └───────┬───────┘
         │                            │                              │
         ▼                            ▼                              ▼
 ┌───────────────┐            (run locally / documented         (lint + type +
 │ CI: backend-  │             in README; not yet in CI)         format only)
 │ ci.yml gates  │
 │ the backend   │
 └───────────────┘
```

### 3.1 Two Suites, One Discipline

The backend and AI suites are technologically distinct (Jest vs. pytest) but share the same architecture: a runtime test layer that injects controlled dependencies, plus a static-analysis layer that enforces style and types. The frontend participates only in the static layer today (§10).

### 3.2 Where Each Layer Lives

- **Runtime tests:** `backend/tests/` (Jest) and `intelligence/device_ai/tests/` (pytest).
- **Static configuration:** `backend/eslint.config.mjs` + `.prettierrc.json` + `tsconfig.json`; `intelligence/device_ai/pyproject.toml` (Ruff/Black/isort/mypy/pytest all configured in one file).
- **Automation:** `backend/package.json` scripts + Husky/lint-staged; `.github/workflows/backend-ci.yml`; the AI README documents the equivalent commands.

---

## 4. Test Organization

**Repository Test Organization Diagram**

```
 backend/
 ├── jest.config.cjs              # roots: src + tests; ts-jest; alias mapping
 └── tests/
     ├── unit/                    # 16 specs — services, middleware, repos, utils
     │   ├── auth.service.test.ts        token.service.test.ts
     │   ├── password.service.test.ts    submission.service.test.ts
     │   ├── reward.service.test.ts       reward.repository.test.ts
     │   ├── submission.repository.test.ts  reward.controller.test.ts
     │   ├── submission.controller.test.ts  health.service.test.ts
     │   ├── api-info.service.test.ts     config.test.ts  logger.test.ts
     │   ├── authenticate.middleware.test.ts  authorize.middleware.test.ts
     │   ├── validate.middleware.test.ts  error-handler.middleware.test.ts
     │   └── request-logger.middleware.test.ts
     ├── integration/             # 4 specs — full HTTP stack via Supertest
     │   ├── auth.test.ts   health.test.ts
     │   ├── reward.test.ts submission.test.ts
     └── helpers/                 # in-memory repository test doubles
         ├── in-memory-auth-repositories.ts
         ├── in-memory-reward-repository.ts
         └── in-memory-submission-repository.ts

 intelligence/device_ai/
 ├── pyproject.toml               # pytest + ruff + black + isort + mypy config
 └── tests/                       # 84 specs + shared fixtures
     ├── conftest.py              # fixtures: TestClient, seeded images, settings
     ├── test_meta.py             # /, /health, /version endpoints
     ├── test_predict*.py         # prediction pipeline & detection
     ├── test_dataset_*.py        # dataset pipeline (M1.2)
     ├── test_training_*.py       # training/MLOps platform (M1.3)
     ├── test_yolo_*.py           # detector (M1.4)
     ├── test_fingerprint_*.py / test_clip_encoder.py / test_similarity.py  (M1.5)
     ├── test_ocr_*.py            # OCR & barcode (M1.6)
     ├── test_recoverability_*.py / test_component_*.py / test_material_*.py
     ├── test_environmental_*.py / test_decision_*.py / test_circular_*.py
     ├── test_passport_*.py / test_integrity_*.py / test_trust_*.py  (M2.x)
     └── test_ledger_*.py / test_lifecycle_*.py                       (M3.x)

 testing/                         # top-level cross-service harness (PLACEHOLDER)
 ├── e2e/           (empty)
 ├── integration/   (empty)
 └── unit/          (empty)

 frontend/                        # NO test directory (static analysis only)
```

### 4.1 Co-located, Per-Service Suites

Each service owns its tests next to its code: the backend under `backend/tests/`, the AI service under `intelligence/device_ai/tests/`. This mirrors the deployment boundary ([09 — Deployment Architecture]) — a service is tested, linted, and shipped as a self-contained unit.

### 4.2 Naming Conventions

- **Backend:** `*.test.ts`, split into `unit/` and `integration/` folders; `tests/helpers/` holds reusable in-memory doubles.
- **AI:** `test_*.py`, flat under `tests/`, named by the engine/milestone they cover (e.g. `test_fingerprint_service.py`, `test_circular_rules.py`). The suffix (`_service`, `_rules`, `_models`, `_routes`, `_inference`) signals the layer under test.

### 4.3 The Empty Cross-Service Harness

The top-level `testing/e2e`, `testing/integration`, and `testing/unit` directories exist but are empty. They mark an intended cross-service test tier that is **not implemented** (§7, §22); this document reports them as placeholders rather than describing behaviour they do not have.

---

## 5. Unit Testing

Unit tests are the base of the pyramid in both suites and exercise a single unit — a service, engine, parser, rule set, middleware, or repository — with its collaborators replaced by controlled doubles.

### 5.1 Backend Unit Tests

The 16 backend unit specs test framework-agnostic logic in isolation. For example, `reward.service.test.ts` builds a `RewardService` with hand-written repository stubs and a silent logger (`createLogger({ logLevel: 'fatal' })`), then asserts behaviour and error mapping (`ConflictError`, `NotFoundError`). A local `submission()` factory constructs a fully-typed `SubmissionRecord` with per-test overrides, so each test states only what it varies. The middleware specs (`authenticate`, `authorize`, `validate`, `error-handler`, `request-logger`) test the Express seam directly; the config and logger specs pin cross-cutting infrastructure.

### 5.2 AI Unit Tests

The bulk of the 84 AI specs are unit tests: rule catalogues (`test_*_rules.py`), models (`test_*_models.py`), inference/scoring (`test_*_inference.py`, `test_recoverability_scoring.py`), parsers (`test_ocr_parser.py`, `test_ocr_patterns.py`), similarity metrics (`test_similarity.py`), and each engine's service (`test_*_service.py`). They instantiate the unit under test with test settings or fixtures and assert deterministic outputs. Because the engines are settings-driven and mock-capable ([03 — Device Intelligence Architecture]), no unit test requires a trained model.

### 5.3 What Makes Them "Unit"

In both stacks a unit test never crosses a process boundary: no HTTP server is bound, no database is contacted, no file is read except through an isolated temp directory (§13). Collaborators are injected (§12) or mocked (§11).

---

## 6. Integration Testing

Integration tests exercise multiple layers wired together through the real application entry point, but still without external infrastructure.

**Backend Test Flow Diagram**

```
 backend integration spec (e.g. auth.test.ts)
        │
        │  buildTestApp():
        │    config = loadConfig(TEST_ENV)      # NODE_ENV=test, BCRYPT_ROUNDS=4
        │    createApp({ config, logger,
        │                authRepositories:
        │                  createInMemoryAuthRepositories() })  ◄── injected doubles
        ▼
 supertest(request(app)).post('/api/v1/auth/register').send(body)
        │
        ▼
 REAL middleware + routes + controllers + services  ([07 — Backend API Arch.])
        │
        │  repository calls hit IN-MEMORY Maps, not PostgreSQL
        ▼
 assert HTTP status + body shape
 assert security invariant: JSON.stringify(res.body) has no 'passwordHash'
```

### 6.1 Backend Integration (Supertest + in-memory repositories)

The 4 integration specs (`auth`, `health`, `reward`, `submission`) drive the **entire HTTP stack** — middleware, routing, controllers, services — via Supertest, while substituting in-memory repository implementations passed into `createApp()`. `auth.test.ts` sets a test environment (`NODE_ENV=test`, `LOG_LEVEL=fatal`, `BCRYPT_ROUNDS=4` for speed, a generous auth rate-limit for unrelated tests) and asserts real behaviours: `201` with a token pair on register, `409` on duplicate email, and — a security regression guard — that the serialized response never contains `passwordHash`. This validates the composition of the whole request lifecycle ([07 — Backend API Architecture]) against a fast, deterministic fake of the persistence tier ([08 — Database Architecture]).

### 6.2 AI Integration (FastAPI TestClient + dependency overrides)

The AI suite's integration-style specs (`test_meta.py`, `test_predict*.py`, `test_dataset_endpoints.py`, `test_fingerprint_routes.py`, `test_ocr_routes.py`) use FastAPI's `TestClient` against an app built by `create_app(settings=...)` with dependency providers overridden (§12). `test_meta.py`, for instance, calls `GET /`, `/health`, and `/version` and asserts the readiness contract (status in `{"healthy","degraded"}`, per-component readiness, model-contract version) — the same endpoints the container health checks probe ([09 — Deployment Architecture], §16 there).

### 6.3 No External Dependencies

Neither integration layer touches a real database, network service, or model file — the defining constraint that keeps these tests fast and deterministic (§14).

---

## 7. End-to-End Testing

### 7.1 Current State: Not Implemented

There is **no implemented end-to-end test suite** in the repository. The top-level `testing/e2e/` directory exists but is empty, as are `testing/integration/` and `testing/unit/`. No Playwright, Cypress, or other browser/e2e harness is present or configured anywhere in the tree.

### 7.2 What Stands in for E2E Today

The closest realized coverage is the per-service integration testing of §6: the backend's full HTTP stack via Supertest and the AI service's full ASGI app via `TestClient`. These exercise each service end-to-end **in isolation**, but there is no cross-service journey (frontend → backend → AI/database) under automated test.

### 7.3 Honest Reporting

Per the "document only what exists" rule, this section deliberately describes an absence. A cross-service E2E tier is an intended future addition (§23), and the empty `testing/` directories are the placeholder for it — not evidence of existing coverage.

---

## 8. AI Engine Testing

The AI suite is the largest in the repository (84 files) and is architected to test sophisticated ML-adjacent behaviour deterministically, without GPUs, network access, or trained weights.

**AI Test Flow Diagram**

```
 pytest  (config: pyproject.toml → testpaths=["tests"], pythonpath=[".."])
        │
        ▼
 conftest.py fixtures
   ├── test_settings / ocr_settings / fingerprint_settings / dataset_settings /
   │   training_settings         ─► small, isolated Settings objects
   ├── client / ocr_client / fingerprint_client / dataset_client
   │        │  reset_dependency_caches(); get_settings.cache_clear()
   │        │  app = create_app(settings=...)
   │        │  app.dependency_overrides[...] = test providers
   │        ▼  TestClient(app)  ── real routes, mock engines
   ├── png_bytes / jpeg_bytes / make_image_bytes(noise, seed)  ─► seeded images
   ├── fake_encoder (MockEmbeddingEncoder) / fake_ocr_backend (injected recognize)
   ├── mock_trainer_cls (deterministic decreasing losses)
   └── sample_fingerprint / sample_spans / populated_dataset (tmp_path)
        │
        ▼
 test_*.py  ─►  assert deterministic engine / service / route outputs
```

### 8.1 Base-Environment, Mock-Capable Design

Every engine that would normally require a heavy dependency (YOLO/Ultralytics detector, OpenCLIP encoder, EasyOCR reader) has a deterministic mock fallback selected automatically in the base environment ([03 — Device Intelligence Architecture]). The fixtures rely on this: `fingerprint_client`'s docstring notes the encoder/repository come from reset cached singletons — *"in the base environment that is the deterministic mock encoder and the in-memory repository, so no torch/OpenCLIP is required."* The `ocr_client` similarly uses `ocr_backend="mock"`. This is what lets 84 test files run fast and offline.

### 8.2 Coverage Breadth (by milestone)

The test filenames map one-to-one onto the engine milestones documented in [03] and [04 — Decision Intelligence Architecture]: dataset pipeline (`test_dataset_*`), training/MLOps (`test_training_*`), detector (`test_yolo_*`, `test_detection_evaluation`), fingerprinting (`test_fingerprint_*`, `test_clip_encoder`, `test_similarity`), OCR (`test_ocr_*`), recoverability/component/material/environmental engines, decision and circular engines, passport/integrity/trust (`test_passport_*`, `test_integrity_*`, `test_trust_*`), and the ledger/lifecycle engines (`test_ledger_*`, `test_lifecycle_*`). The engine *algorithms* themselves are out of scope here ([03], [04]); this document covers only how they are tested.

### 8.3 Route, Service, and Model Layering

Within each engine, tests are stratified: `_models` (data structures/validation), `_rules`/`_knowledge`/`_profiles` (the external YAML catalogues loaded per [03]'s configuration model), `_inference`/`_scoring`/`_engine` (core logic), `_service` (orchestration), and `_routes`/`_endpoints` (HTTP contract via `TestClient`). This layering makes a failure localizable to the exact tier that broke.

---

## 9. Backend Testing

### 9.1 Runner Configuration (`jest.config.cjs`)

The backend uses **Jest 29** with the following configuration, read directly from the file:

- `testEnvironment: 'node'` — no DOM.
- `roots: ['<rootDir>/src', '<rootDir>/tests']` — tests may live beside code or under `tests/`.
- `transform` via `ts-jest` using `tsconfig.json` — TypeScript is compiled per-test-run, so tests type-check against the same config as the app.
- `moduleNameMapper` mirrors the app's path aliases (`@shared/*`, `@modules/*`, `@infrastructure/*`), so tests import exactly as production code does.
- `clearMocks: true` — mock state is reset between tests, preventing cross-test bleed.
- `collectCoverageFrom: ['src/**/*.ts', '!src/server.ts', '!src/types/**']` — coverage, when collected, targets application source but excludes the process entry point and type-only files. **No coverage threshold is configured**, so none is asserted here.

### 9.2 Tooling

`ts-jest`, `@types/jest`, `supertest`, and `@types/supertest` are the test dependencies (`package.json`). Supertest drives HTTP for integration specs (§6.1); `ts-jest` provides TypeScript execution and type-awareness.

### 9.3 Scripts

`package.json` exposes `test` (`jest`), `test:watch` (`jest --watch`), and `test:coverage` (`jest --coverage`). These are the same commands developers run locally and that CI invokes (§20).

### 9.4 Scope of the Backend Suite

The 22 specs cover the auth, submission, reward, and health modules, plus shared middleware, config, and logging — the surfaces documented in [07 — Backend API Architecture]. Persistence is always faked (in-memory repositories), consistent with the repository-boundary design of [08 — Database Architecture]; the ORM and real database are therefore out of the unit/integration scope by construction.

---

## 10. Frontend Testing

### 10.1 Current State: Static Analysis Only

The frontend (`frontend/`, React 19 + Vite, [06 — Web Platform Architecture]) has **no runtime test suite**. Its `package.json` defines no `test` script and includes no test runner (no Vitest, Jest, Testing Library, Playwright, or Cypress). Its quality tooling is entirely static:

- `lint` — ESLint (`eslint .`).
- `typecheck` — `tsc -b --noEmit`.
- `format:check` — Prettier.

### 10.2 What This Means

Frontend correctness is currently guarded by type-checking and linting, not by behavioural tests. Component/interaction/rendering tests are an identified gap (§22) and a natural next step (§23). This is reported as-is, without implying coverage that does not exist.

---

## 11. Mock Strategy

Both suites prefer **hand-written, deterministic test doubles injected at a seam** over heavy auto-mocking of internals.

### 11.1 Backend: In-Memory Repositories and Stubs

The integration tier substitutes complete in-memory implementations of the repository interfaces. `createInMemoryAuthRepositories()` backs `UserRepository`/`RefreshTokenRepository` with `Map`s, generates UUIDs with `node:crypto`, and — per its header comment — *"pre-seeds the CONSUMER role to mirror `prisma/seed.ts`"*, so the fake faithfully reproduces the real seed state ([08 — Database Architecture]). Parallel helpers exist for rewards and submissions (`in-memory-reward-repository.ts`, `in-memory-submission-repository.ts`). Unit specs use narrower stubs — e.g. a `subRepo` exposing only `findById`, the one method the service reads. `jest.fn()` is used for fine-grained collaborators, with `clearMocks: true` guaranteeing isolation.

### 11.2 AI: Deterministic Mock Engines

The AI service's mock strategy is architectural, not test-local: the engines themselves ship deterministic mock backends selected when heavy dependencies are absent (the mock YOLO detector, `MockEmbeddingEncoder`, mock OCR backend) ([03 — Device Intelligence Architecture]). Tests lean on these via settings (`ocr_backend="mock"`, `fingerprint_backend="memory"`) and via fixtures like `fake_encoder` (`MockEmbeddingEncoder`) and `fake_ocr_backend` (an `EasyOCRBackend` with an injected `recognize_fn` returning fixed `(bbox, text, confidence)` rows). This lets a test exercise the *real* adapter's row-mapping path without `easyocr` installed.

### 11.3 Principle

In both stacks the double replaces an **external or expensive collaborator at an interface boundary**, never the logic under test. This keeps tests honest — the production code path runs; only its dependencies are controlled.

---

## 12. Dependency Injection

Testability is designed into both services through dependency injection, which is why the mock strategy of §11 is possible at all.

### 12.1 Backend: Constructor/Factory Injection via `createApp()`

The backend's composition root, `createApp()`, accepts its collaborators as parameters — `{ config, logger, authRepositories, ... }`. Tests pass fakes directly (`createApp({ config, logger, authRepositories: createInMemoryAuthRepositories() })`), so the entire HTTP stack runs unchanged over an in-memory persistence tier. Services are likewise built by factory functions (`createRewardService(...)`, `createTokenService(...)`) that take their dependencies as arguments, so a unit test supplies stubs without any framework magic. This is the same inversion that lets Prisma be a replaceable detail in [07 — Backend API Architecture] and [08 — Database Architecture].

### 12.2 AI: FastAPI `dependency_overrides`

The AI service uses FastAPI's dependency-injection system. Route handlers depend on provider functions (`get_settings`, `get_dataset_service`, `get_fingerprint_service`, `get_ocr_service`) declared in `device_ai.api.dependencies`. Test fixtures build an app with `create_app(settings=...)` and then replace providers via `app.dependency_overrides[...]`, wrapping cleanup so overrides are cleared afterward. Two supporting calls make this deterministic: `dependencies.reset_dependency_caches()` and `get_settings.cache_clear()` (the settings singleton is `@lru_cache`d, [09 — Deployment Architecture] §8) ensure each test starts from a clean, test-scoped configuration rather than inheriting cached state.

### 12.3 Why It Matters

Both mechanisms mean tests configure the system the way production does — through its real wiring — rather than reaching into internals. Injection is the single most important enabler of the fast, hermetic, deterministic suites this document describes.

---

## 13. Fixtures & Test Data

### 13.1 AI Fixtures (`conftest.py`)

The AI suite centralizes reusable fixtures and data builders in `tests/conftest.py`:

- **App clients:** `client`, `ocr_client`, `fingerprint_client`, `dataset_client` — each yields a `TestClient` wired to a fresh app with the matching settings and overrides (§12.2).
- **Settings variants:** `test_settings`, `ocr_settings`, `fingerprint_settings`, `dataset_settings`, `training_settings` — small, purpose-built `Settings` objects (e.g. 1 MB `max_file_size` to keep large-file tests fast; `WARNING` log level; temp-dir roots).
- **Image builders:** `make_image_bytes(...)` and `write_image(...)` generate encoded images in-memory or on disk, with a `noise` mode backed by a **seeded** `numpy` RNG so bytes are reproducible.
- **Domain fixtures:** `sample_fingerprint` (a fixed `DeviceFingerprint` with a pinned timestamp), `sample_spans` (deterministic OCR spans covering every field type), `mock_trainer_cls` (a trivial `BaseTrainer` producing deterministic decreasing losses), and `populated_dataset` (writes four raw images — including an exact duplicate and a dark image — plus YOLO labels into an isolated `tmp_path`).
- **Filesystem isolation:** fixtures that touch disk use pytest's `tmp_path`, so no test writes into the repository or a shared location (§14).

### 13.2 Backend Fixtures/Builders

The backend favours inline, typed factory functions over a shared fixture file: e.g. the `submission()` builder in `reward.service.test.ts` returns a complete `SubmissionRecord` with overridable fields, and integration specs define request bodies (`registerBody`) and a `TEST_ENV` constant. The in-memory repositories (§11.1) double as test-data stores, pre-seeded to mirror the real seed.

### 13.3 Data Realism

Fixtures use realistic, domain-shaped values (Indian addresses and coordinates, `ET-2026-…` EcoIDs, plausible serial/IMEI/MAC spans) so tests read as executable specifications of real behaviour.

---

## 14. Deterministic Testing

Determinism is a first-class, verifiable property of both suites — the same inputs always produce the same result, so tests never flake.

### 14.1 Seeded Randomness

Wherever randomness would otherwise leak in, it is seeded. `make_image_bytes(noise=True)` uses `np.random.default_rng(seed=size[0]*size[1])`; `write_image(noise=True, seed=...)` seeds per-image; training fixtures pin `training_seed=7` and `RunConfig(..., seed=7)`. The settings model itself exposes `split_seed`/`training_seed` defaults ([09 — Deployment Architecture] §8) so dataset splitting and training runs are reproducible by design.

### 14.2 Fixed Clocks and IDs

Time-dependent data uses explicit timestamps, not `now()` — e.g. `sample_fingerprint` pins `created_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)`, and backend record builders use fixed ISO dates (`new Date('2026-07-20T…')`). This removes wall-clock and ordering nondeterminism from assertions.

### 14.3 Mock Backends Remove Model Nondeterminism

Because the heavy ML backends are replaced by deterministic mocks (§11.2), engine outputs are stable across runs and machines — there is no GPU, no network model download, and no floating-point drift from real inference in the default suite.

### 14.4 State Reset Between Tests

`clearMocks: true` (Jest) and `reset_dependency_caches()` + `get_settings.cache_clear()` (pytest fixtures) ensure no cached singleton or mock state carries between tests. Combined with `tmp_path` isolation, every test starts from a clean, identical baseline.

---

## 15. Regression Protection

Tests encode not just correctness but **invariants that must never regress**, several of them security-critical.

### 15.1 Security Regressions

The auth integration suite asserts that no serialized response ever leaks a credential: `expect(JSON.stringify(res.body)).not.toContain('passwordHash')`. This is a standing guard against an accidental change to a serializer or DTO re-exposing the hash ([07 — Backend API Architecture]). Duplicate-registration is pinned to `409 Conflict`, and successful registration/login to a `201`/token-pair shape, so contract drift is caught immediately.

### 15.2 Contract and Metadata Regressions

`test_meta.py` locks the service's public metadata: `GET /` returns `status: "ok"`, `GET /health` returns a status in `("healthy", "degraded")` with per-component readiness, and `GET /version` returns `model_version "1.0.0"` and `api "v1"`. These freeze the operational contract relied on by the compose health checks and clients ([09 — Deployment Architecture]).

### 15.3 Behavioural Invariants

Milestone-aligned specs (§8.2) protect the AI engines' documented behaviour — e.g. near-duplicate fingerprints must exceed the similarity threshold, deterministic OCR spans must map to the correct passport fields, and training losses must decrease monotonically under the mock trainer. Because these run on every invocation of the suite, a change that breaks a documented guarantee fails fast.

### 15.4 Mechanism

Regression protection is emergent from the test organization (§4) rather than a separate tool: the unit + integration tiers are the regression suite, and CI (§20) makes passing them a merge precondition for the backend.

---

## 16. Static Analysis

Static analysis runs **before** tests in both stacks and is treated as an equal member of the quality gate (§21).

### 16.1 AI: Ruff and mypy

Configured in `pyproject.toml`:

- **Ruff 0.8.6** — `line-length = 88`, `target-version = "py312"`. The lint rule set is explicit: `select = ["E", "F", "I", "N", "UP", "B", "A", "C4", "SIM", "ANN", "D"]` (pycodestyle, pyflakes, isort, naming, pyupgrade, bugbear, builtins, comprehensions, simplify, annotations, docstrings). `ignore = ["D203", "D213", "D107", "ANN401", "B008"]` (the last accommodating FastAPI's `Depends()` default-argument idiom). `per-file-ignores` relaxes `"D"` and `"ANN"` for `tests/*`, so tests are not required to carry full docstrings or annotations. Docstring convention is `google`.
- **mypy 1.14.1** — `python_version = "3.12"`, `disallow_untyped_defs = true`, `warn_return_any = true`, `warn_unused_configs = true`, `ignore_missing_imports = true`, with the `pydantic.mypy` plugin enabled for model-aware checking.

### 16.2 Backend: ESLint and `tsc`

- **ESLint 9** (flat config) with `typescript-eslint` and `eslint-config-prettier` (so ESLint and Prettier never fight over formatting). Invoked as `npm run lint` (`eslint .`).
- **`tsc --noEmit`** (`npm run typecheck`) performs whole-project type-checking against `tsconfig.json`, independent of the per-test `ts-jest` transform.

### 16.3 Frontend

The frontend runs the same class of checks — ESLint and `tsc -b --noEmit` — as its *only* automated quality gate (§10).

---

## 17. Formatting & Style

Formatting is enforced mechanically so it is never a review topic.

### 17.1 AI: Black and isort

- **Black 24.10.0** — `line-length = 88`, `target-version = ["py312"]`.
- **isort 5.13.2** — `profile = "black"` (so import sorting agrees with Black), `line_length = 88`, `known_first_party = ["device_ai", "tests"]`.

Ruff's `I` rules and isort are aligned on the same import ordering, and Ruff's `E`/line-length agrees with Black, so the three tools form a consistent, non-conflicting style front.

### 17.2 Backend/Frontend: Prettier

**Prettier 3** is the single formatter for TypeScript, JSON, Markdown, and YAML. `format` writes, `format:check` verifies. `eslint-config-prettier` disables all ESLint rules that would overlap Prettier, mirroring the Black/isort alignment on the Python side.

### 17.3 Pre-Commit Enforcement (Backend)

The backend wires formatting/lint into the commit itself via **Husky 9** + **lint-staged 15**: staged `*.ts` files run `eslint --fix` then `prettier --write`; staged `*.{json,md,yml,yaml}` run `prettier --write`. Style is thus corrected locally before code ever reaches CI.

---

## 18. Type Safety

Both stacks are statically typed end-to-end, and type-checking is a gate, not a suggestion.

### 18.1 TypeScript (Backend & Frontend)

TypeScript 5.7 compiles under `--noEmit` for checking (`typecheck`) and separately for the build (§19). Because `ts-jest` compiles specs against the same `tsconfig.json`, a type error in a test is a test failure — tests and app share one type universe. Path aliases are declared once and honoured by `tsc`, ESLint, Jest (`moduleNameMapper`), and the build (`tsc-alias`).

### 18.2 Python (AI)

The AI service is fully type-annotated and checked by mypy under `disallow_untyped_defs = true`, so every non-test function must carry a signature. Pydantic v2 models provide runtime validation at the API boundary ([07 — Backend API Architecture]) that complements mypy's static guarantees, and the `pydantic.mypy` plugin makes the static checker aware of model semantics. Tests are exempt from `ANN` (§16.1) to keep them terse.

---

## 19. Build Verification

A successful production build is the final automated proof that the code is not merely well-typed in isolation but assembles into a shippable artifact.

### 19.1 Backend Build

`npm run build` runs `prisma generate && tsc -p tsconfig.build.json && tsc-alias -p tsconfig.build.json`: it regenerates the Prisma client, compiles with the build-specific tsconfig, and rewrites path aliases to relative paths for the emitted JavaScript ([09 — Deployment Architecture]). CI runs this after tests, so a merge candidate must both pass tests and build cleanly.

### 19.2 Frontend Build

`npm run build` runs `tsc -b && vite build` — a type-checked, bundled production build. Though not yet in CI (§20), it is the same command the container image would run ([09 — Deployment Architecture]).

### 19.3 AI "Build"

The Python service has no compile step; its equivalent gate is the packaged import surface plus `pip install` of pinned requirements ([09 — Deployment Architecture]). Correctness is established by the pytest suite rather than a compiler.

---

## 20. Continuous Integration

### 20.1 The One Workflow: `backend-ci.yml`

CI is implemented by a **single** GitHub Actions workflow, `.github/workflows/backend-ci.yml`. It is reported exactly as it exists — no other pipeline is inferred.

- **Triggers:** `workflow_dispatch`, and `push`/`pull_request` to `develop` and `main`, path-filtered to `backend/**` and the workflow file itself. Changes elsewhere do not trigger it.
- **Defaults:** `run.working-directory: backend`.
- **Job `quality`** (`ubuntu-latest`): checkout → `setup-node@v4` (Node 20, npm cache) → `npm ci` → `npm run lint` → `npm run typecheck` → `npm run format:check` → `npm test` → `npm run build`.
- **Job `docker`** (`needs: quality`): checkout → `docker/build-push-action@v6` building `backend/` with `push: false`, tag `ecotrace-backend:ci` — a build-only validation, no registry push ([09 — Deployment Architecture]).

```
┌──────────────────────────────────────────────────────────────────────┐
│                    CI WORKFLOW — backend-ci.yml                        │
└──────────────────────────────────────────────────────────────────────┘

  Trigger: push / pull_request → (develop | main)   [paths: backend/**]
           or manual workflow_dispatch
                              │
                              ▼
        ┌───────────────────────────────────────────────┐
        │  job: quality            (runs-on: ubuntu-latest)│
        │  working-directory: backend                     │
        │                                                 │
        │   1. actions/checkout                           │
        │   2. setup-node@v4  (Node 20, npm cache)        │
        │   3. npm ci                                      │
        │   4. npm run lint          ── ESLint            │
        │   5. npm run typecheck     ── tsc --noEmit      │
        │   6. npm run format:check  ── Prettier          │
        │   7. npm test              ── Jest (22 specs)   │
        │   8. npm run build         ── prisma+tsc+alias  │
        └───────────────────────────────────────────────┘
                              │  needs: quality (must pass)
                              ▼
        ┌───────────────────────────────────────────────┐
        │  job: docker             (runs-on: ubuntu-latest)│
        │   1. actions/checkout                           │
        │   2. docker/build-push-action@v6                │
        │        context: backend/                        │
        │        push: false                              │
        │        tags: ecotrace-backend:ci                │
        └───────────────────────────────────────────────┘
                              │
                              ▼
                   ✅ green check on PR / branch
```

**Figure 20.1 — CI Workflow Diagram**

### 20.2 What CI Does Not Do (Reported As-Is)

- **No AI CI.** The pytest suite is not run by any workflow; it runs locally/on-demand only.
- **No frontend CI.** Neither the frontend lint/typecheck nor its build runs in CI.
- **No coverage gate.** Coverage is collectable (`test:coverage`) but never enforced (§9.1).
- **No E2E stage** (none exists, §7).
- **No deploy/publish.** The Docker job validates the build but pushes nothing ([09 — Deployment Architecture]).

CI therefore protects the **backend** on `develop`/`main`; all other quality enforcement is developer-driven (§17.3, §21).

---

## 21. Quality Gates

A **quality gate** is an ordered set of checks that code must pass before it is considered mergeable. The backend has a fully automated gate (local + CI); the AI and frontend stacks have the same *checks* defined but enforced by developers rather than CI.

### 21.1 Backend Gate (Automated)

The backend gate is the union of the local pre-commit hook (§17.3) and the CI `quality` job (§20.1): lint → typecheck → format:check → test → build, followed by a Docker build validation. All must pass for a green check on `develop`/`main`.

### 21.2 AI Gate (Developer-Enforced)

The AI stack defines an equivalent ordered gate through its tooling — `ruff check` → `black --check` → `isort --check` → `mypy` → `pytest` — using the versions pinned in `requirements-dev.txt`. These are not yet wired into a workflow (§20.2), so they are run by developers.

### 21.3 Frontend Gate

`lint` → `typecheck` → `format:check` → `build`, developer-run (§10, §19.2).

```
┌──────────────────────────────────────────────────────────────────────┐
│                        QUALITY GATE PIPELINE                          │
│           (code must clear every gate, left → right, to pass)         │
└──────────────────────────────────────────────────────────────────────┘

 BACKEND  (automated: Husky pre-commit + CI quality job)
 ─────────────────────────────────────────────────────────────────────
   [ ESLint ]→[ tsc --noEmit ]→[ Prettier ]→[ Jest ]→[ build ]→[ docker ]
     lint        typecheck       format       test     compile   image
       │            │              │            │         │         │
       └── style ───┴── types ─────┴── style ───┴─ behav ─┴─ assemble┘
                                                            │
                                            all green ▶ mergeable

 AI  (same shape, developer-enforced — not in CI)
 ─────────────────────────────────────────────────────────────────────
   [ ruff ]→[ black --check ]→[ isort --check ]→[ mypy ]→[ pytest ]
     lint      format            imports          types    behaviour

 FRONTEND  (developer-enforced — not in CI)
 ─────────────────────────────────────────────────────────────────────
   [ ESLint ]→[ tsc -b --noEmit ]→[ Prettier ]→[ vite build ]
     lint         typecheck          format        compile
   (no runtime tests — gap, see §22)

 Legend:  [ x ]  a blocking check      ▶  outcome
          Order within a stack is the order tools run.
```

**Figure 21.1 — Quality Gate Pipeline Diagram**

### 21.4 Gate Ordering Rationale

Cheap, fast checks run first (lint, format), then type-checking, then the more expensive test and build steps — so the fastest-failing problem is reported first. This is why the CI `quality` job orders its steps lint → typecheck → format:check → test → build (§20.1).

---

## 22. Current Limitations

Reported honestly and grounded in the repository, so reviewers see the true testing posture:

1. **No frontend runtime tests.** The React app has only static analysis (§10); no component, interaction, or rendering tests exist.
2. **No end-to-end tests.** `testing/{unit,integration,e2e}/` are empty placeholders; no cross-service or browser flow is exercised (§7).
3. **AI and frontend are outside CI.** Only the backend runs in GitHub Actions (§20.2); the AI pytest suite and both frontends' checks depend on developer discipline.
4. **No enforced coverage.** Coverage is collectable but no threshold gates a merge (§9.1) — coverage numbers are therefore deliberately not quoted anywhere in this document.
5. **No integration against real infrastructure.** Persistence is always in-memory (§11.1) and heavy ML backends are always mocked in the default suite (§11.2); the real Prisma/Postgres path ([08 — Database Architecture]) and real model inference ([03 — Device Intelligence Architecture]) are not exercised by automated tests.
6. **No performance, load, or security scanning** in the automated pipeline.

None of these are defects in what exists — they bound its scope.

---

## 23. Future Testing Evolution

A pragmatic path that builds on the current seams, consistent with the roadmap in [01 — System Architecture]:

1. **Add an AI CI workflow** mirroring `backend-ci.yml` (ruff → black → isort → mypy → pytest), path-filtered to `intelligence/**`.
2. **Add a frontend CI workflow** (lint → typecheck → format:check → build) and introduce a runtime test runner (e.g. Vitest + Testing Library) for components.
3. **Introduce E2E** in the reserved `testing/e2e/` directory, driving the composed stack ([09 — Deployment Architecture]) through representative lifecycle flows.
4. **Add a real-infrastructure integration tier** using ephemeral containers (Postgres, and optionally a real model backend) to complement the in-memory suites.
5. **Adopt coverage thresholds** once suites mature, turning today's collectable coverage into an enforced gate.
6. **Contract tests** between backend and AI service to lock their HTTP interface ([07 — Backend API Architecture]).

Each step reuses an existing seam (DI, mock backends, empty placeholder dirs), so none requires re-architecting.

---

## 24. Design Rationale

Why the testing architecture looks the way it does:

- **Injection over patching.** Because both services expose their collaborators as parameters (§12), tests configure the system through its real wiring. This yields fast, hermetic tests without brittle monkey-patching and keeps production and test code paths identical.
- **Deterministic mock backends over real models.** Shipping mock engines in the product (§11.2) means the *default* test suite needs no GPU, no model downloads, and no network — so it is reproducible on any machine and in CI, and free of floating-point flakiness (§14.3).
- **Static analysis as a peer of testing.** Type-checking, linting, and formatting run in the same gate as tests (§21) because in a typed codebase many defect classes are cheaper to catch statically than with a test.
- **In-memory persistence for the HTTP tier.** Faking at the repository boundary (§11.1) lets the full request pipeline — routing, validation, auth, error mapping — be tested end-to-end within the process, fast enough to run on every commit, while keeping the database an implementation detail ([08 — Database Architecture]).
- **Honest scope over aspirational coverage.** The suite tests what exists and the document reports exactly that (§22). No coverage number is invented; no CI stage is claimed that is not in `backend-ci.yml`. This integrity is itself a design goal for an IEEE-reviewed prototype.
- **Milestone-aligned tests as living specification.** Naming AI specs after milestones (§8.2) makes the suite a traceable map from requirement to verification.

---

## 25. References

**Internal — Companion Architecture Documents**

- [01 — System Architecture] — overall system context and roadmap.
- [02 — AI/Intelligence Architecture] — the intelligence platform under test.
- [03 — Device Intelligence Architecture] — engines and their mock backends.
- [06 — Web Platform Architecture] — the React frontend (static-analysis only here).
- [07 — Backend API Architecture] — endpoints and contracts asserted by the suites.
- [08 — Database Architecture] — repository boundary faked by in-memory doubles.
- [09 — Deployment Architecture] — build, images, health contracts, and CI's Docker job.

**Repository Sources of Truth (read for this document)**

- `backend/jest.config.cjs`, `backend/package.json` — backend runner, scripts, tooling.
- `backend/tests/integration/*.test.ts`, `backend/tests/unit/*.test.ts` — backend specs.
- `backend/tests/helpers/in-memory-*.ts` — in-memory repository doubles.
- `intelligence/device_ai/pyproject.toml` — pytest, Ruff, Black, isort, mypy config.
- `intelligence/device_ai/requirements-dev.txt` — pinned test/QA tool versions.
- `intelligence/device_ai/tests/conftest.py` — fixtures, builders, DI overrides.
- `intelligence/device_ai/tests/test_*.py` — the AI engine suites.
- `frontend/package.json` — frontend scripts (no test runner).
- `.github/workflows/backend-ci.yml` — the sole CI workflow.
- `testing/{unit,integration,e2e}/` — reserved, currently empty.

**External — Tooling**

- Jest 29, ts-jest, Supertest — backend testing.
- pytest 8.3.4, pytest-cov 6.0.0, httpx 0.28.1, FastAPI `TestClient` — AI testing.
- ESLint 9, typescript-eslint, Prettier 3, TypeScript 5.7, Husky 9, lint-staged 15 — TS static analysis/formatting.
- Ruff 0.8.6, Black 24.10.0, isort 5.13.2, mypy 1.14.1 — Python static analysis/formatting.
- GitHub Actions, `docker/build-push-action@v6` — CI.

---

## 26. Conclusion

EcoTrace India's testing architecture is a **layered, deterministic, injection-driven** quality system. Two backend-language stacks — a Jest/Supertest suite for the Node.js API and a pytest suite for the FastAPI intelligence service — sit on a shared foundation: collaborators are injected at interface boundaries (§12), external and expensive dependencies are replaced by faithful in-memory and mock doubles (§11), and every source of nondeterminism is seeded or pinned (§14). Above the tests, an equally weighted static-analysis and formatting front (Ruff, Black, isort, mypy; ESLint, Prettier, `tsc`) forms the rest of the quality gate (§16–§21), enforced locally by Husky pre-commit and, for the backend, by a single GitHub Actions workflow (§20).

The architecture's defining virtue is **honesty of scope**. It tests thoroughly what it covers — the backend HTTP pipeline and the AI engines — and this document reports the boundaries of that coverage without embellishment: no frontend runtime tests, no E2E, AI and frontend outside CI, and no enforced coverage threshold (§22). Those boundaries are not weaknesses hidden behind invented numbers; they are a clear-eyed statement of the current prototype's posture and a concrete roadmap for its evolution (§23). For IEEE reviewers, QA engineers, and developers alike, the result is a test architecture that is fast, reproducible, and trustworthy — one whose green check genuinely means what it claims.

---

*This document reverse-engineers the testing and quality-assurance architecture strictly from the EcoTrace India repository as implemented. Every framework, tool version, configuration value, script, fixture, workflow step, and stated limitation is drawn directly from the source files enumerated in §25; nothing — including coverage figures, CI stages, or test frameworks — has been inferred or invented. Where the implementation and aspirational engineering notes diverge, the implementation is the source of truth.*
