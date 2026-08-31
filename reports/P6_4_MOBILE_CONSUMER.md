# P6.4 — Mobile Consumer Application

## 1. Objective

Build the EcoTrace Consumer Flutter app (`mobile/consumer_app/`) against the
real `backend/` contract, reusing the reconnaissance and architectural
lessons from P6.3 (`reports/P6_3_MOBILE_COLLECTOR.md`) — same backend, same
`Notifier`/`NotifierProvider` riverpod 3.x API, same "verify against real
source, don't assume" discipline.

---

## 2. What's real vs. what isn't (reconnaissance)

Reusing P6.3's findings (real workflow is pickup-logistics, not AI
detection) plus one more check specific to this app's design brief — the
"Device Passport" / "Blockchain Verification" requirement:

`backend/src/infrastructure/fabric/fabric.client.ts` and
`backend/src/infrastructure/ai/ai.client.ts` exist, but are **explicit,
self-documented placeholders**:

```ts
// fabric.client.ts
/** Placeholder until Phase 7: fails loudly if used before the Fabric layer exists. */
export function createFabricClient(): FabricClient {
  return {
    submitTransaction: () => Promise.reject(new Error('Fabric client is not available until Phase 7 (Blockchain).')),
    ...
```

Neither client is imported by any module or route (`grep` for
`createFabricClient`/`createAiClient` across `backend/src/modules` and
`app.ts`: zero matches). This means:

- **There is no working blockchain verification or AI device classification
  on the backend this app talks to**, despite P6.1/P6.2 having built a real,
  tested Fabric chaincode + Gateway client — in the separate Python
  `intelligence/device_ai` service, which this Node `backend/` does not yet
  call into.
- **There is no image-upload endpoint** (`grep` for `upload`/`multer`/
  `multipart` across `backend/src`: zero matches). `createSubmissionSchema`'s
  `imageUrls` field expects already-hosted URLs, not a file the app uploads
  and gets a URL back for. No camera-photo-attach flow was built for the
  same reason as the Collector app's (`reports/P6_3_MOBILE_COLLECTOR.md`
  §7): there is nowhere real to send the file.
- **Rewards have no consumer-facing redemption endpoint** —
  `POST /rewards/issue/:submissionId` is ADMIN-only (a manual override;
  rewards are issued automatically when a recycler completes processing).

Per the work order ("Do not invent reward APIs if they do not exist...
Do not create fake production behavior"), the app:
- Implements the Device Verification screen as an **honest "not yet
  connected" state**, naming the actual reason (backend's own "Phase 7"
  marker), not a fabricated pass/fail result.
- Implements Rewards as **read-only** balance + history (real, working
  endpoints) with no non-functional "Redeem" button.
- Implements Report Waste without a photo-attach step.

---

## 3. Architecture

Mirrors the Collector app's structure (`core/`, `features/*`, `shared/`),
with app-agnostic files (`ApiClient`, `AppFailure`/`Result`,
`SecureStorageService`, `AppTheme`, loading/empty/error widgets) adapted
from the already-verified Collector app source rather than re-derived.
Consumer-specific:

- **`features/auth`**: unlike the Collector app, `register()` is real and
  used — `POST /auth/register` always creates a `CONSUMER` account, which
  is exactly this app's role (the inverse of why the Collector app couldn't
  offer it — see `reports/P6_3_MOBILE_COLLECTOR.md` §2.1).
- **`features/submissions`**: create/list/detail/cancel against
  `POST/GET/PATCH/DELETE /submissions[/:id]` — this is the "device capture"
  flow from the design brief, correctly modeled as a pickup request per §2.
- **`features/rewards`**: read-only `GET /rewards/balance` +
  `GET /rewards/history`.
- **`features/trust`**: honest "not yet connected" Device Verification
  screen (§2).
- **`features/scan`**: QR scan that opens a report's detail screen when the
  scanned code is a submission UUID — the one real, backend-supported thing
  a scanned code can resolve to right now (not a device-identity lookup,
  which doesn't exist).
- **`features/education`**: static recycling-education content — genuinely
  real, no backend needed for non-account-specific informational copy.
- **Offline handling**: simpler than the Collector app's SQLite sync queue
  by deliberate scope decision — reads degrade to `ErrorState`/retry rather
  than a cached-offline view, and submission creation requires connectivity
  (fails with a clear, retryable error) rather than being queued. The
  Collector app already demonstrates the offline-queue pattern thoroughly;
  reporting waste is less field-work/connectivity-constrained than a
  collector's pickup workflow, so this is a reasonable, documented scope
  reduction rather than a gap discovered too late to fix.

---

## 4. Screens

| Screen | Status |
|---|---|
| Splash | Implemented |
| Login | Implemented |
| Register | Implemented — **real**, unlike the Collector app (§3) |
| Home | Implemented as a tabbed shell (Reports/Rewards/Learn/Profile) + Scan shortcut |
| Scan Device | Implemented — QR → submission lookup (§2), not a device-identity scan (no backend for that) |
| Device Verification | Implemented as an honest "not yet connected" state (§2) |
| Device Passport | Not implemented — no backend data model for this exists yet (no chaincode call from `backend/`) |
| Lifecycle Timeline | Covered by Submission Detail's status chip + recovered-weight/CO2 fields once recycled — a separate screen would show the same `PublicSubmission` fields with no additional backend data |
| Rewards | Implemented — balance + history, read-only (§2) |
| Redemption | Not implemented as a functional flow — no backend endpoint (§2); the Rewards screen states this |
| Recycling Education | Implemented — static content |
| Submission History | Implemented |
| Community/Leaderboard, Challenges | Not implemented — no backend data model (no leaderboard/challenge tables in `prisma/schema.prisma`); building either against nothing would be fabricated |
| Profile | Implemented |
| Settings | Folded into Profile (logout, device verification entry) rather than a separate near-empty screen |

---

## 5. Test Results

- **`flutter pub get`**: resolved cleanly.
- **`flutter analyze`**: **0 issues** (after fixing an implicit transitive
  `uuid` dependency and two `unawaited_return_in_try_block` warnings caught
  by the analyzer — real issues, not hypothetical).
- **`flutter test`**: **9 / 9 passed** — 7 unit tests (`SubmissionStatus`/
  `Submission` parsing + `isEditable`, `RewardBalance`/`RewardTransaction`
  parsing) and 2 widget tests (`RegisterScreen` validation, including the
  password-mismatch check).
- **APK build**: not attempted — same environment constraint as P6.3 (no
  Android SDK; see `reports/P6_3_MOBILE_COLLECTOR.md` §9 for what was tried).

---

## 6. Known Limitations

1. **No APK build** — analyze/test-verified only (§5).
2. **Blockchain/AI trust verification not connected** — `backend/`'s own
   Fabric/AI clients are unimplemented placeholders (§2); the P6.1/P6.2
   Python-side Fabric work is real but not yet reachable from this backend.
3. **No photo attachment** on submissions — no upload endpoint exists (§2).
4. **No functional reward redemption** — no backend endpoint exists (§2).
5. **No community/leaderboard/challenges** — no backend data model exists.
6. **Offline handling is simpler than the Collector app's** — no local
   write queue; a deliberate, documented scope choice (§3), not an
   oversight.
7. **No push notifications.**

---

## 7. Definition of Done

- [x] Reconnaissance against actual backend source (§2), including checking
      for blockchain/AI backend support before designing those screens.
- [x] Real, working Flutter project reusing verified P6.3 infrastructure.
- [x] Functional registration (unlike the Collector app, correctly).
- [x] Real report/rewards/history flows against actual endpoints.
- [x] Trust/redemption/community features honestly represented as
      unavailable rather than faked.
- [x] `flutter analyze`: 0 issues.
- [x] `flutter test`: 9/9 passed.
- [x] APK build honestly reported as not attempted (same environment
      constraint as P6.3).
