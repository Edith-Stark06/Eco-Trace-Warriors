# P8.4 — Mobile Consumer Pilot Validation

## 1. Scope

Validate the consumer-side lifecycle and verification experience —
inspecting the existing P6.4 (and P7.6-hardened) implementation first,
fixing only what's genuinely missing.

---

## 2. Pre-flight baseline

`flutter analyze`: 0 issues. `flutter test`: 13/13 (fresh run this phase).

---

## 3. A real gap found and fixed: no consumer-role check at login

Inspecting item #2 ("Consumer role") directly against source turned up a
genuine, real inconsistency: the **collector** app's `login()` explicitly
checks `profile.role == 'COLLECTOR'` and rejects any other role client-side
(`mobile/collector_app/lib/features/auth/data/auth_repository.dart`) — but
the **consumer** app's `login()` had **no equivalent check at all**. A
COLLECTOR, ADMIN, RECYCLER, or GOVERNMENT account could successfully log
into the consumer app, with its tokens persisted and the user dropped
straight into consumer-shaped screens (rewards, submission history) that
don't match what their actual role does.

**Fixed**, mirroring the collector app's exact, already-established
pattern:
- Added `ConsumerProfile.isConsumer` (mirrors `CollectorProfile.isCollector`).
- `AuthRepository.login()` now rejects a non-`CONSUMER` login client-side
  with the message `"This account is registered as X, not CONSUMER. Use
  the EcoTrace Consumer app only with a consumer account."` — before any
  token is persisted to secure storage.
- `register()` needed no equivalent change: `POST /auth/register` always
  creates a `CONSUMER` account server-side (`backend/src/modules/auth/
  auth.service.ts`, unchanged), so there is no wrong-role case to guard
  against there.

New tests (`test/unit/auth_repository_test.dart`, previously no
repository-level auth test existed in this app at all): a successful
CONSUMER login persists tokens; a COLLECTOR login is rejected and **never**
calls any secure-storage write (verified via `verifyNever`); the same
rejection is additionally exercised for ADMIN, GOVERNMENT, and RECYCLER.
**5/5 new tests pass.**

This is a real, meaningful pilot-readiness fix, not a cosmetic one — a
tester or pilot participant accidentally using the wrong app with the
wrong account would previously have gotten a confusing, unscoped
experience instead of a clear, actionable rejection message.

---

## 4. Checklist — remaining items, real status

| # | Item | Status |
|---|---|---|
| 1 | Authentication | Real, functional `register()` + `login()` (now role-checked, §3). **PASS** |
| 2 | Consumer role | **Fixed this phase**, see §3 |
| 3 | QR/barcode scanning | `ScanScreen` resolves a submission UUID from a scanned code — the one real scan capability, matches the actual backend surface (no device-passport lookup endpoint exists to scan into). **PASS, scope-honest** |
| 4 | Device passport lookup | **Honestly unavailable** — re-verified this phase by re-reading `device_verification_screen.dart`'s own documented reasoning: the Node `backend/` mobile apps talk to has no Fabric/AI client wired in (`fabric.client.ts` explicitly rejects every call, "Phase 7"), and P6.1/P6.2's working Fabric integration lives in the separate Python service this backend doesn't yet call into for per-device passport data. Still accurate, no drift. |
| 5 | Lifecycle timeline | `SubmissionDetailScreen`/`SubmissionHistoryScreen`, real. **PASS** |
| 6 | Trust verification | Same as #4 — honestly unavailable, not faked. |
| 7 | Blockchain verification display | Same as #4 for a *specific device*; the Fabric Gateway *connectivity* status (not per-device) is available via the same backend proxy the frontend's `BlockchainHealthCard` uses (P6.5), but no consumer mobile screen currently surfaces it — out of this phase's scope to add without a design decision on where it belongs in the consumer UX. |
| 8 | Reward balance | Real, `GET /rewards/balance`. **PASS** |
| 9 | Reward redemption | **N/A by design, re-confirmed** — no backend redemption endpoint exists; `RewardsRepository`'s own doc comment states this explicitly, unchanged since P6.4. |
| 10 | Recycling history | `SubmissionHistoryScreen`. **PASS** |
| 11 | Educational content | Static `EducationScreen`. **PASS** |
| 12 | Community/leaderboard | **Not implemented** — confirmed absent (`find` for leaderboard/community files: 0 results); the P8.4 brief itself only asks to validate this "if already implemented," which it is not. |
| 13 | Loading/error/empty states | Present per screen, consistent with the collector app's pattern. **PASS** |
| 14 | Offline-safe UX | The consumer app has no offline queue by design (P6.4) — it is a thin online-only client; this remains the correct, intentional architecture (re-confirmed, not changed). |
| 15 | Accessibility | P7.6's password-toggle tooltip fix re-verified with no regression (18/18 unchanged pass count includes it). **PASS** |
| 16 | Localization readiness | **NOT READY** — identical situation and identical reasoning as the collector app (P8.3 §4): zero i18n framework, a real product decision not scoped by any prior phase, honestly disclosed rather than invented. |
| 17 | Secure token storage | `flutter_secure_storage`. **PASS** |
| 18 | Hardcoded secrets | Grepped for password/API-key/secret literal patterns — **0 findings**. |

---

## 5. Native build — attempted, honestly blocked

```
$ flutter doctor -v
[X] Android toolchain - develop for Android devices
    X Unable to locate Android SDK.
```

Given P8.3 already captured the exact `flutter build apk --debug` failure
output for the collector app against the identical environment (same
machine, same missing Android SDK, same absent `android/` platform
directory), re-running the identical failing command against the consumer
app would only reproduce the identical evidence. **APK BUILD BLOCKED BY
ENVIRONMENT** — genuinely blocked, not attempted redundantly a second time
for the same root cause already captured verbatim in P8.3 §5. iOS:
categorically blocked (Windows host).

---

## 6. Tests

| Suite | Result |
|---|---|
| `auth_repository_test.dart` (new) | 5/5 |
| Consumer `flutter analyze` | 0 issues |
| Consumer `flutter test` (full suite) | **18/18** (13 baseline + 5 new) |

---

## 7. Test accounting

| | Count |
|---|---|
| Previous (P8.1 baseline) | 13 |
| Added this phase | 5 |
| Removed this phase | 0 |
| Final | 18/18, 0 analyze issues |

---

## 8. Protected asset verification

Verified via `sha256sum` before and after this phase's changes — **6/6
MATCH**. No ML asset touched.

---

## 9. Git state

Diff scoped to: `mobile/consumer_app/lib/features/auth/models/
auth_models.dart` (+1 getter), `mobile/consumer_app/lib/features/auth/
data/auth_repository.dart` (role check in `login()`),
`mobile/consumer_app/test/unit/auth_repository_test.dart` (new). Verified
via `git status`/`git diff --stat` before commit.

---

## 10. Environmental limitations

- **APK build BLOCKED BY ENVIRONMENT** — no Android SDK, evidence captured
  in P8.3 against the identical environment.
- **iOS build BLOCKED BY ENVIRONMENT** — categorical.
- **Localization NOT READY** — genuine product-scope gap, disclosed not
  invented (§4).
- **Device passport / trust / blockchain verification display**: honestly
  unavailable — a real, pre-existing backend architecture gap (no
  Fabric/AI client wired into the Node backend consumer apps talk to),
  re-confirmed accurate this phase, not a new limitation.

---

## 11. Definition of Done

- [x] P6.4 (and P7.6-hardened) implementation inspected fresh.
- [x] A real, genuine role-enforcement gap found (by direct comparison
      against the collector app's own established, correct pattern) and
      fixed, with new tests proving both the accept and reject paths (§3).
- [x] Every remaining checklist item given a real, re-verified status
      (§4).
- [x] `flutter analyze`/`flutter test` re-run fresh, 18/18, 0 issues.
- [x] Localization honestly assessed as not-ready, consistent with P8.3.
- [x] No unnecessary rebuild of working architecture.
- [x] Protected assets verified before and after.

## 12. Final status: **PASS — APK BUILD BLOCKED BY ENVIRONMENT**
