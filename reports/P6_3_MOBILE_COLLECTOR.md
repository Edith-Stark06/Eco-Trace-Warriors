# P6.3 — Mobile Collector Application

## 1. Objective

Build the EcoTrace Collector Flutter app (`mobile/collector_app/`) — the field
app collectors use to manage e-waste pickup assignments — against the
**actual** backend contract, not an assumed one.

---

## 2. Reconnaissance: the real backend contract (not assumed)

`mobile/collector_app/` and `mobile/consumer_app/` existed as empty
placeholder directories only. Before writing any screen, the actual backend
(`backend/` — Express + Prisma + Zod, **not** the Python
`intelligence/device_ai` AI microservice used in P6.1/P6.2) was read
directly: `auth`, `submission`, `rewards`, `users` modules, routes, Zod
schemas, services, and `prisma/schema.prisma`.

This reconnaissance **overturned the mobile-design brief's implicit
assumption** that the collector workflow is AI-detection-driven ("Device
Capture", "Device Registration" screens, camera → class detection →
register). The real backend has no such flow for collectors. It is a
**pickup-logistics** system:

- `Submission` (`prisma/schema.prisma`): a consumer-created waste-pickup
  request (`category`, `estimatedWeight`, `address`, `latitude`/`longitude`,
  `imageUrls`, `status`) that moves through
  `PENDING → ASSIGNED → ACCEPTED → IN_PROGRESS → COLLECTED → RECYCLING → RECYCLED → COMPLETED` (or `REJECTED`).
- A collector's job is to **accept, start, and complete an assigned
  pickup** — `PATCH /submissions/:id/{accept,start,complete}` — not to
  detect/register a device.

Three further findings changed the app's design directly:

1. **`POST /auth/register` always creates a `CONSUMER` account**
   (`backend/src/modules/auth/auth.service.ts` — `findRoleId(UserRole.CONSUMER)`
   is hard-coded; `registerSchema` has no role field). There is no
   self-service way to create a `COLLECTOR` account. **The app does not ship
   a functional Register screen** — a self-service form that cannot do what
   it implies would itself be "fake production behavior". Login shows an
   honest "accounts are provisioned by your coordinator" dialog instead (§6).
2. **`GET /submissions/:id` is owner/admin-only**
   (`submission.service.ts` → `loadAccessible`: `record.userId !== actor.userId` → 404
   for anyone else, including the assigned collector). A collector fetching
   their own assigned pickup by id via this route gets `404 Not Found`. The
   app never calls it; the detail screen resolves a submission from the
   local cache populated by the dashboard call instead (§5).
3. **There is no collector history endpoint.** The repository layer has a
   `findByCollector` query returning every submission ever assigned
   (`submission.repository.ts`) — but it is never called from the service or
   wired to a route. Only `GET /collector/submissions` (active assignments:
   `ASSIGNED`/`ACCEPTED`/`IN_PROGRESS`, via `findCollectorAssignments`) is
   exposed. The Submission History screen is therefore built on the local
   cache ("everything this device has seen"), not a fabricated server-side
   history call (§5, §9 limitations).

Per the work order's own instruction ("If previous documentation conflicts
with actual source code, follow the source and document the discrepancy"),
the app follows the real backend on all three points.

---

## 3. Architecture

```
mobile/collector_app/
├── lib/
│   ├── core/            # config, network (Dio + error mapping), secure storage, SQLite, theme
│   ├── features/
│   │   ├── auth/        # login, session bootstrap, CollectorProfile/AuthTokens models
│   │   ├── tasks/        # Submission model, dashboard + cache repository, accept/start/complete
│   │   ├── sync/         # offline queue (SQLite), SyncManager reconciliation, connectivity
│   │   ├── capture/      # CameraService / BarcodeScannerService abstractions (§7)
│   │   ├── home/         # tabbed shell (Tasks / History / Sync / Profile)
│   │   └── profile/      # profile, settings
│   └── shared/           # reusable loading/empty/error/network-banner widgets
└── test/
    ├── unit/             # model, sync-queue-dedup, repository (real SQLite via sqflite_common_ffi)
    └── widget/           # login screen
```

- **State management**: `flutter_riverpod` (pinned to the resolved `3.4.2`,
  which **removed `StateNotifier`/`StateNotifierProvider`** in favor of
  `Notifier`/`NotifierProvider` — discovered by actually running `flutter
  analyze`, not assumed from memory; see §8).
- **Networking**: `dio`, wrapped in `ApiClient` (attaches `Authorization:
  Bearer` + `X-Request-ID`, mirroring the backend's own request-context
  middleware) and `mapDioExceptionToFailure` (translates the backend's
  `{success:false, error:{code, message}}` envelope —
  `backend/src/shared/middleware/error-handler.middleware.ts` — into the
  app's `AppFailure`).
- **Secrets**: `flutter_secure_storage` (Android Keystore / iOS Keychain) —
  the only place tokens are read/written; never logged, never in
  `SharedPreferences`.
- **Offline-first**: `sqflite`, two tables — `sync_queue` (queued
  accept/start/complete actions) and `submission_cache` (last-known state of
  every submission this collector has seen).
- **No hard-coded API URL**: `AppConfig.apiBaseUrl`/`apiPrefix` are
  `String.fromEnvironment` with dev defaults, overridable via
  `--dart-define`.

---

## 4. Screens

| Screen | Status |
|---|---|
| Splash | Implemented — validates any stored session against `GET /auth/me` before routing |
| Login | Implemented — email/password, backend-role check (rejects a non-COLLECTOR account client-side) |
| ~~Register~~ | **Not implemented — see §2.1**; an honest info dialog explains why |
| Home / Task List | Implemented as one tabbed shell (Tasks/History/Sync/Profile) — consolidating these avoids a redundant near-duplicate "Home" screen |
| Device Capture / Registration | **Not implemented — see §2** (no such backend flow for collectors) |
| Task Detail | Implemented — full submission detail + the one valid next action (`accept`/`start`/`complete`) |
| Submission History | Implemented — **cache-backed**, not server-backed (§2.3) |
| Sync Queue | Implemented — per-item status, manual retry for exhausted items |
| Profile | Implemented — profile fields from `GET /auth/me`, logout |
| Settings | Implemented — read-only config/about |

---

## 5. Offline-first / sync design

- **Queueing**: `SyncQueueRepository.enqueue` deduplicates by
  `(submissionId, actionPath)` — re-tapping "Accept" twice before
  connectivity returns replaces the pending row instead of creating a
  second one.
- **Draining**: `SyncManager.drainQueue()` replays pending items when
  connectivity returns (`connectivityProvider` → `syncOnReconnectProvider`).
- **Reconciliation, not blind retry** (avoiding duplicate submissions): the
  collector-workflow endpoints are PATCH *state transitions*, not idempotent
  creates — replaying `accept` after it already reached the server (response
  merely lost) would otherwise fail server-side transition validation.
  `SyncManager._reconcileAgainstServerState` re-fetches the submission's
  current status on a 4xx failure and treats the action as already-applied
  (drops it from the queue) if the status shows it took effect, rather than
  endlessly retrying or duplicating. `rejected` is handled as an explicit
  terminal-exception state, not an ordinal "further along" one (an earlier
  draft used `.index >=` comparisons, which is exactly the kind of subtle
  bug this kind of state-machine logic invites — fixed to explicit status-set
  membership before it shipped).
- **No retry of a write already attempted this call**: `performOrQueue` (the
  online-first path) tries once; on a retryable failure it queues rather
  than looping.

---

## 6. Security

- Tokens: `flutter_secure_storage` only (Keystore/Keychain), never logged,
  never in plain prefs.
- No self-service collector account creation (§2.1) — the app cannot be used
  to mint privileged accounts.
- Client input validated before submission (email format, non-empty
  password) in addition to server-side validation.
- The backend remains authoritative for every lifecycle transition — the
  app never fabricates a status locally; every state change comes from the
  API response (or, for a queued action, is only reflected once the queue
  drains successfully).
- `AppConfig` documents that a production build must override
  `API_BASE_URL` at compile time — no production endpoint is hard-coded.

---

## 7. Camera / QR abstractions

`CameraService` (`image_picker`) and `BarcodeScannerService`
(`mobile_scanner`) are implemented as required capabilities, but are
**not wired into a submission-affecting flow**: the collector-workflow
endpoints accept no photo payload, and general submission updates
(`imageUrls` included) are restricted to the owning consumer while the
submission is still `PENDING` (`submission.service.ts`). Wiring a
"photo of the pickup, for reference" feature through these services is a
natural next step once a backend endpoint exists to receive it — building
that UI now, with nowhere real for the data to go, would itself be the "fake
production behavior" the work order warns against.

---

## 8. Environment: Flutter SDK

No Flutter/Dart SDK was present at the start of this phase (`which flutter`
→ not found). Two install paths were attempted:

1. **Chocolatey** (`choco install flutter`) — failed: `Access to the path
   'C:\ProgramData\chocolatey\lib-bad' is denied` (no admin rights in this
   environment).
2. **Direct SDK download** (`storage.googleapis.com/flutter_infra_release`,
   Flutter 3.47.2 stable, ~1.93 GB) to a user-writable directory, no
   elevation required — **succeeded** after one truncated download was
   retried to completion and its zip integrity verified
   (`zipfile.testzip()`).

This is the "Flutter unavailable → implement source + static validation +
document SDK limitation → CONTINUE" scenario the work order explicitly
anticipates, except it did not end up unavailable — the fallback download
path worked, which meaningfully upgrades the honesty of everything below:
this is not "carefully hand-written but unverified" Dart, it is **compiled,
analyzed, and tested**.

Discovering a working SDK also surfaced a real API mismatch no amount of
careful hand-writing would have caught: **`flutter_riverpod` 3.4.2 removed
`StateNotifier`/`StateNotifierProvider`** (superseded by `Notifier`/
`NotifierProvider`, with dependencies read via `ref` inside methods rather
than constructor-injected). The two controllers (`AuthController`,
`TaskActionController`) were rewritten against the actual installed
package source (`flutter_riverpod-3.4.2`) once this was caught by `flutter
analyze`, not left on the outdated 2.x-shaped API.

---

## 9. Test Results

All commands run from `mobile/collector_app/` with the locally-installed
Flutter 3.47.2 (channel stable).

- **`flutter pub get`**: resolved cleanly — every pinned version (fetched
  live from the pub.dev API before writing `pubspec.yaml`, not guessed)
  resolves against the current package graph.
- **`flutter analyze`**: **0 issues** (after fixing the riverpod 3.x API
  mismatch, an exhaustive-switch gap from a `dio` `DioExceptionType` value
  added after this file was first written, a `flutter_secure_storage` 11.x
  constructor-parameter rename, two unused imports, and a dangling doc
  comment — all real issues the compiler found, not hypothetical).
- **`flutter test`**: **18 / 18 passed** —
  - 14 unit tests: `SubmissionStatus`/`Submission` JSON parsing and
    `nextAction` mapping, `SyncQueueItem` row round-tripping, and — using
    `sqflite_common_ffi` against a real in-memory SQLite database (the
    native `sqlite3` library **is** available in this environment, so this
    ran for real, not just compiled) — `SyncQueueRepository`'s
    enqueue/dedup/pending-count/retry behavior.
  - 4 widget tests: `LoginScreen` validation errors, password-visibility
    toggle, and the collector-access info dialog (proving §2.1's decision is
    reflected in the actual UI, not just the repository layer).
- **APK build**: **not attempted.** `flutter doctor` confirms no Android SDK
  in this environment (`Unable to locate Android SDK`) — a much larger
  install (Android Studio + SDK + license acceptance) than the Flutter SDK
  itself, and outside what installing Flutter was reasonably justified to
  chase. Windows desktop and web build targets are available
  (`flutter doctor` reports them healthy) but were not exercised — the
  code-correctness value they'd add on top of a clean `analyze` + a real
  `flutter test` run (which already executes real Dart, real SQLite, real
  widget pumping) is marginal relative to the platform-plugin-compatibility
  risk of chasing a build for platforms this app isn't targeting.

---

## 10. Known Limitations

1. **No APK build** (§9) — analyze/test-verified, not device/emulator-run.
2. **No self-service collector registration** (§2.1) — by backend design,
   not an app gap.
3. **Submission History is cache-only** (§2.3) — reflects what this device
   has seen via the active-assignments dashboard, not a complete
   server-side history (no such endpoint exists).
4. **Camera/scanner abstractions are not wired to a live flow** (§7) — ready
   for a future backend capability, not connected to one that doesn't exist
   yet.
5. **No push notifications** for new assignments — the collector must open
   the app / pull-to-refresh to see new work. Out of scope for this phase.
6. **Windows/web build targets untested** (§9) — the app targets
   Android/iOS; those platforms' plugin implementations
   (`sqflite`/`flutter_secure_storage`/`mobile_scanner`/`image_picker`) were
   not exercised on desktop/web, where some have no or partial support.

---

## 11. Definition of Done

- [x] Reconnaissance against actual backend source, not the design brief's assumptions (§2).
- [x] Real, working Flutter project: `pubspec.yaml` with live-verified package versions, full `lib/` architecture.
- [x] Offline-first architecture: local queue, dedup, connectivity-triggered drain, reconciliation against server state.
- [x] Idempotency / no-duplicate-submission handling for the queued actions that actually exist on this backend.
- [x] Secure token storage; no hard-coded secrets/URLs.
- [x] Required camera/QR abstractions implemented (not fake-wired to a nonexistent flow).
- [x] `flutter analyze`: 0 issues.
- [x] `flutter test`: 18/18 passed, including real SQLite execution.
- [x] Honest documentation of what does not exist on the backend and therefore isn't implemented, and why.
- [x] APK build honestly reported as not attempted (no Android SDK), not fabricated.
