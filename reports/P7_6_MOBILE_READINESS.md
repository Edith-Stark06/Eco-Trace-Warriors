# P7.6 — Mobile Production Readiness

## 1. Scope

Deep review of both Flutter apps against the P7.6 checklist, building on
(not re-doing) the substantial P6.3/P6.4 implementation and P7.1/P7.3's
prior audits — verify what's already there, fix what's genuinely missing.

---

## 2. Pre-flight state

- Protected assets: 6/6 MATCH.
- Baseline: collector 22/22 (18 P6.3 baseline + 4 P7.3 `AppLogger` tests),
  consumer 13/13 (9 baseline + 4 P7.3), both `flutter analyze` clean.

---

## 3. Checklist review

### 3.1 Collector app

| Item | Status |
|---|---|
| Authentication | Real, JWT access+refresh, `flutter_secure_storage` — **PASS** (P6.3) |
| API integration | Dio + shared interceptor, `ApiClient`/`ApiException` mapping — **PASS** |
| Camera | `CameraService` abstraction over `image_picker`, honestly documented as **not wired to any upload flow** — the real backend's `accept`/`start`/`complete` endpoints take no photo payload (verified again this phase by re-reading `submission.routes.ts`) — **PASS, scope-honest** |
| QR/barcode | `BarcodeScannerService` abstraction over `mobile_scanner`, honestly documented as **not wired to a lookup flow** — no backend "resolve by code" endpoint exists — **PASS, scope-honest** |
| Device registration | **N/A** — collectors don't register devices on the real backend (established P6.3 §2, re-confirmed) |
| Offline storage | Real SQLite (`sqflite`), `sync_queue` + `submission_cache` tables — **PASS** |
| Synchronization | `SyncManager.drainQueue()`, server-state reconciliation for stale replays — **PASS** |
| Retry handling | `maxSyncRetries` (5), periodic drain-on-reconnect — **PASS** |
| Task/assignment flow | `TasksRepository`, real `GET /collector/submissions` — **PASS** |
| Submission status | `SubmissionStatus` enum with `fromWire()`, matches all 9 backend states — **PASS** |
| Error handling | `mapDioExceptionToFailure` + P7.3's structured `AppLogger` on every failure — **PASS** |
| Loading states | `AsyncValue`-driven UI throughout (Riverpod) — **PASS** |
| Connectivity handling | `connectivityProvider` (`connectivity_plus`), logged via `AppLogger` since P7.3 — **PASS** |
| Secure token storage | `flutter_secure_storage`, platform Keychain/EncryptedSharedPreferences — **PASS** |

### 3.2 Consumer app

| Item | Status |
|---|---|
| Authentication | Real, functional `register()` + login — **PASS** |
| Device lookup | **N/A** — no device-passport API exists on the real backend (P6.4 §2); `DeviceVerificationScreen` honestly states this rather than fabricating a lookup |
| QR/barcode verification | `ScanScreen` resolves a submission UUID from a scanned code — the one real scan capability, matches actual backend surface — **PASS** |
| Lifecycle view | `SubmissionDetailScreen`/`SubmissionHistoryScreen` — **PASS** |
| Trust verification | Honestly not connected (`DeviceVerificationScreen`), citing the same disconnected-domain-model finding from P6.5 — **PASS, scope-honest** |
| Rewards | Read-only `RewardsRepository` (`fetchBalance`/`fetchHistory`), documented why no redemption endpoint exists — **PASS** |
| Educational content | Static `EducationScreen` — **PASS** |
| History | `SubmissionHistoryScreen` — **PASS** |
| Error handling | Same `mapDioExceptionToFailure` + `AppLogger` pattern as collector — **PASS** |
| Accessibility | **Gap found and fixed** (§4) |

---

## 4. Accessibility audit (new this phase)

Grepped both apps for `Semantics(`/`semanticLabel` (0 hits either app) and
every `IconButton(` (5 total across both apps). Flutter's default Material
widgets (buttons with text children, `TextFormField` with `labelText`)
already carry reasonable default semantics from their visible text, so the
absence of explicit `Semantics()` wrappers isn't itself a defect — but an
icon-only `IconButton` has **no** text for a screen reader to announce
unless it carries a `tooltip` (Flutter uses `tooltip` as the accessible
label).

Of the 5 `IconButton`s found, 2 already had one (`sync_queue_screen.dart`'s
retry button: `'Retry now'`; `consumer/home_screen.dart`'s action button).
**3 password-visibility toggles had none** — a screen reader user tapping
them would hear nothing distinguishing "show password" from "hide
password":

- `mobile/collector_app/lib/features/auth/screens/login_screen.dart`
- `mobile/consumer_app/lib/features/auth/screens/login_screen.dart`
- `mobile/consumer_app/lib/features/auth/screens/register_screen.dart`
  (the confirm-password field correctly reuses the same
  `_obscurePassword` state/toggle as the password field — verified there
  is no second, separately-broken toggle to also fix)

**Fixed**: added `tooltip: _obscurePassword ? 'Show password' : 'Hide
password'` to all 3, matching the button's current dynamic state (so the
announced label always matches what tapping will actually do).

Status icons that pair with visible text (e.g. the sync-queue item's
colored status icon, always alongside a text `subtitle`) were judged
adequate as-is — status is never conveyed by icon/color alone anywhere
found, matching the frontend's own established "never color alone"
convention (P6.6).

---

## 5. Native build status (re-verified, not assumed)

- `flutter doctor` re-run this phase: **Android SDK still absent**
  (`Unable to locate Android SDK`) — `flutter build apk --debug`
  **ENVIRONMENT_BLOCKED**, honestly reported, not attempted.
- iOS: **categorically ENVIRONMENT_BLOCKED** — this is a Windows host, no
  Xcode/macOS exists or can exist here.
- Both apps continue to be verified via `flutter analyze` (real static
  analysis of real Dart source) and `flutter test` (real widget pumping,
  real SQLite via `sqflite_common_ffi` for the collector app's sync-queue
  tests) — the strongest verification actually available in this
  environment, not a substitute claimed as equivalent to a device run.

---

## 6. Mock API mode — not built, reasoning disclosed

The brief asks to "implement mock API mode if needed for deterministic
development." Assessed as **not needed here**: every widget/unit test
already runs against fake/mock repositories and a real in-memory SQLite
database (see `test/widget/login_screen_test.dart`,
`test/unit/sync_queue_repository_test.dart`) — this **is** the practical
mock-mode this environment can exercise and verify. Building a separate
interactive "point the whole app at fake data" toggle for manual
exploration would be speculative: there is no Android SDK/emulator/device
in this environment to actually run the app interactively and observe it,
so such a toggle could not itself be verified working here — it would be
exactly the kind of "add functionality beyond what the task requires" this
session's standing rules caution against. Documented rather than silently
skipped.

---

## 7. Tests

| Suite | Result |
|---|---|
| Collector `flutter analyze` | 0 issues |
| Collector `flutter test` | **22/22** (unchanged — accessibility fix doesn't add/remove tests, only tooltip strings) |
| Consumer `flutter analyze` | 0 issues |
| Consumer `flutter test` | **13/13** |

No regression from the accessibility fix — re-run both suites after the
change, identical pass counts to the P7.3 baseline.

---

## 8. Protected asset verification

Verified via `sha256sum` before and after this phase's changes — **6/6
MATCH**. No ML asset touched.

---

## 9. Git state

Diff scoped to exactly 3 files: the two apps' `login_screen.dart` and the
consumer app's `register_screen.dart` — one `tooltip:` line added to each
of 3 `IconButton`s. Verified via `git status`/`git diff --stat` before
commit.

---

## 10. Environmental limitations

- No Android SDK — `flutter build apk --debug` **ENVIRONMENT_BLOCKED**.
- No macOS/Xcode — iOS build **ENVIRONMENT_BLOCKED** (categorical, not
  fixable in this environment).

Both re-verified this phase via a fresh `flutter doctor` run, not carried
forward as an unchecked assumption.

---

## 11. Definition of Done

- [x] Both apps reviewed against every item in the P7.6 checklist,
      cross-referenced against real backend capability (not invented
      capability) — §3.
- [x] A real accessibility gap found (icon-only password toggles with no
      screen-reader label) and fixed in all 3 locations, verified no
      regression (§4, §7).
- [x] Native build status re-verified via a fresh `flutter doctor` run,
      honestly reported as environment-blocked, not attempted or assumed
      (§5).
- [x] "Mock API mode" need assessed and explicitly not built, with
      reasoning disclosed rather than silently skipped (§6).
- [x] Existing working architecture preserved — no rewrites, no removed
      functionality.
- [x] Protected assets verified before and after.

## 12. Final status: **PASS**
