# P9.5 — Mobile Offline-First + UX Hardening

Status: **PASS**

## 1. Scope

Harden both React Native apps for realistic field conditions:
intermittent connectivity, malformed/conflicting server responses, and a
genuinely expired session — with terminology-explicit queue states,
bounded backoff, crash-safety, and accessibility review.

## 2. Queue state model expanded

`SyncQueueStatus` grew from `pending | syncing | failed` to
`pending | syncing | conflict | failed` (both apps). `conflict`
(triggered by a real HTTP 409 from the server) is terminal immediately —
retrying it would only conflict again — distinct from `failed`, which is
reached only after `MAX_ATTEMPTS` (5) non-conflict failures. There is no
explicit "synced" status: a successfully synced item is simply removed
from the queue, matching the existing, already-established convention
rather than introducing a redundant terminal state.

## 3. Bounded retry backoff

Each `SyncQueueItem` gained `nextRetryAt: string | null`. On a
non-conflict failure, the item's next eligible retry time is set via
exponential backoff (5s, 10s, 20s, 40s, capped at 2 minutes) rather than
being immediately re-attempted on every reconnect event. `useSyncManager`
now filters the batch to only items whose `nextRetryAt` has elapsed (or
is unset), verified by two new tests per app (`does not retry an item
still inside its backoff window` / `retries an item whose backoff window
has already elapsed`).

## 4. A second real defect found and fixed: silent session expiry

Reviewing the actual token-refresh code path (not just the happy path)
surfaced a genuine, user-facing bug: when `apiClient`'s background 401 →
refresh cycle discovered a truly expired/revoked refresh token, it
cleared secure storage but never told `AuthContext`. The app would stay
on `status: 'authenticated'` — the user remained parked on
Dashboard/other authenticated screens, with every subsequent API call
silently 401ing and no path back to the login screen short of manually
finding the sign-out button.

**Fix**: `client.ts` gained `setSessionExpiredHandler()` (registration)
and `triggerSessionExpired()` (invocation, called only when a refresh
token existed and was genuinely rejected by the server — never for "no
token, never logged in" or a network/timeout failure during refresh,
neither of which is a real expiry). `AuthContext` registers a handler on
mount that flips to `unauthenticated` with a clear "Your session has
expired. Please sign in again." message, which `LoginScreen` already
displays via its existing error-alert rendering.

Verified with 2 new tests per app in a new `src/auth/AuthContext.test.tsx`:
a genuinely-authenticated session flips to `unauthenticated` with the
correct message when `triggerSessionExpired()` fires (simulating exactly
what `refreshTokens()` does internally), and a never-logged-in session
is unaffected (no spurious error shown).

## 5. Crash-safety review (re-verified, not assumed)

| Scenario | Behavior |
|---|---|
| Camera permission denied | `CameraView`-using screens (`CaptureScreen`, `ScanScreen`) render `ErrorState` with a retry action when `useCameraPermissions()` reports not-granted; established in P9.3, re-confirmed unchanged |
| Malformed/unreadable QR code | `ScanScreen` shows an inline error message rather than crashing or navigating on an empty scan result |
| Network unavailable | `apiClient`'s offline pre-check (P9.4) and every screen's `ErrorState`/`ApiError` handling |
| API unavailable / 5xx | Falls through `apiClient`'s standard error path — a real `ApiError` is thrown and rendered, not an unhandled rejection |
| Expired token | §4 — now recovers to a clear login prompt instead of a silent stuck state |
| Malformed server response (invalid JSON) | `apiClient`'s `response.json().catch(() => null)` already converts a JSON-parse failure into `null`, which the following `!json` check turns into a standard `ApiError('Request failed with status ...')` — verified by reading the code path, not merely assumed |

## 6. Accessibility

Every new UI element this phase (the `conflict` sections in both apps'
`SubmissionHistoryScreen`) carries `accessibilityRole="alert"` for the
warning text, consistent with the existing P9.3 pattern for error/status
messaging (color is never the only signal). No regressions to previously
audited screens.

## 7. Performance

No mobile-device-level performance profiling was possible — no physical
device or emulator exists in this environment (unchanged from P9.3/§8
below). What was reviewed by inspection: the sync batch processes items
sequentially with an explicit `syncingRef` guard preventing overlapping
batches (no uncontrolled concurrent request storms); the offline queue
and submission lists are bounded by realistic pilot-scale data volumes,
not paginated infinitely-growing structures that would need virtualization
review at this stage; no screen holds a captured image in memory beyond
the single in-flight capture/preview it's actively showing.

## 8. Native builds

Unchanged from P9.3/P9.4: `BLOCKED — ENVIRONMENT`. No Android SDK, no
macOS/Xcode in this environment. Not attempted, not fabricated.
Expo/TypeScript-level validation (typecheck, lint, test) was performed
in full — see §9.

## 9. Tests

| File (both apps unless noted) | New/changed tests |
|---|---|
| `src/hooks/useSyncManager.test.ts` | Rewritten: 8 tests (was 5) — added conflict-terminal, backoff-window-skip, backoff-window-elapsed; fixed two pre-existing tests that had accidentally used a 409 status to mean "generic retryable failure" (now correctly a distinct scenario) |
| `src/auth/AuthContext.test.tsx` (new) | 2 tests — session-expiry flip, never-logged-in unaffected |
| Totals | **collector_app 32/32** (was 27), **consumer_app 31/31** (was 26) — all genuinely run and passing |

## 10. Full-system regression

| Suite | Result |
|---|---|
| Backend (Jest) | 341/341 |
| Chaincode (Jest) | 47/47 |
| device_ai (pytest, junitxml) | 1121/1121, 0 errors, 0 failures |
| Frontend | typecheck clean, lint clean (untouched this phase) |
| Collector mobile | 32/32 |
| Consumer mobile | 31/31 |

No files outside `mobile/` were modified this phase.

## 11. Protected asset verification

| Asset | Result |
|---|---|
| P4.4.2 YOLO11n | MATCH |
| P4.11 Targeted Aug | MATCH |
| P4.12 YOLO11s | MATCH |
| P4.14 Targeted Aug | MATCH |
| P4.5 Data YAML | MATCH |
| P4.7 Data YAML | MATCH |

All 6/6 MATCH, verified before and after this phase.

## 12. Files changed

- `mobile/{collector_app,consumer_app}/src/types/syncQueue.ts` — expanded status enum, `nextRetryAt` field
- `mobile/{collector_app,consumer_app}/src/storage/syncQueue.ts` — set `nextRetryAt: null` on enqueue
- `mobile/{collector_app,consumer_app}/src/hooks/useSyncManager.ts` — backoff filtering, conflict handling, `conflictCount`
- `mobile/{collector_app,consumer_app}/src/hooks/useSyncManager.test.ts` — rewritten/expanded
- `mobile/{collector_app,consumer_app}/src/api/client.ts` — `setSessionExpiredHandler`/`triggerSessionExpired`
- `mobile/{collector_app,consumer_app}/src/auth/AuthContext.tsx` — registers the handler, surfaces the message
- `mobile/{collector_app,consumer_app}/src/auth/AuthContext.test.tsx` — new
- `mobile/{collector_app,consumer_app}/src/screens/SubmissionHistoryScreen.tsx` — conflict-state UI section
- `reports/P9_5_MOBILE_OFFLINE_UX_HARDENING.md` / `.json`

No backend, device_ai, frontend, chaincode, or protected-asset files touched.

## 13. Final verdict

**PASS.** Queue states now match the requested terminology (pending,
syncing, conflict, failed) with bounded exponential-backoff retry and no
infinite loops; a second genuine, user-facing defect (silent stuck
session on token-refresh failure) was found by reading the real code
path and fixed with real tests; crash-safety for every listed failure
mode was re-verified against the actual implementation rather than
assumed; accessibility on all new UI is consistent with the established
pattern. 63 mobile tests total (up from 53 after P9.4), all genuinely
run and passing. Native builds remain honestly `BLOCKED — ENVIRONMENT`.
