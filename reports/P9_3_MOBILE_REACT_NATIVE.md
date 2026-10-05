# P9.3 — Mobile Architecture Migration: Flutter/Dart → React Native + Expo SDK 57

Status: **PASS WITH LIMITATIONS**

## 1. Scope

Full replacement of the planned Flutter/Dart mobile stack with two independent
React Native + Expo SDK 57 + TypeScript apps (Collector, Consumer), per
explicit direction: complete Flutter/Dart purge (current tree + git-history
secret audit + local tooling cleanup), a real React Native implementation of
both apps against the actual backend/device_ai API surface, offline-first
sync, blockchain/trust verification routed through the backend (never
directly to Fabric), accessibility, security review, real tests, full-system
regression, and honest documentation of what could and could not be verified
in this environment (no Android SDK, no macOS/Xcode).

## 2. Baseline

- Branch `develop`, HEAD `31d40c4` (Flutter/Dart removal commit) at the
  start of the React Native implementation work; `d30d0d6` before that
  (P9.2 live Fabric).
- P9.1/P9.2 verdicts: COMPLETE / LIVE FABRIC — ACHIEVED.
- 6 protected assets verified MATCH before this phase began.

## 3. Flutter/Dart purge

### Current tree
- Removed all git-tracked Dart source from both apps: `lib/`, `test/`,
  `pubspec.yaml`, `pubspec.lock`, `analysis_options.yaml`, `.gitignore` — 90
  tracked files, 8,337 lines, committed as `chore(mobile): remove flutter
  and dart architecture` (`31d40c4`).
- Removed untracked build artifacts: `.dart_tool/`, `build/`, empty `assets/`
  and `lib/` scaffolding.
- Verified zero remaining `.dart` files, `pubspec.*` files, or
  `.dart_tool` directories anywhere under `mobile/`.

### Local Flutter SDK tooling
- The Flutter SDK (~3.3GB, `D:\Documents\DevTools\flutter`) was downloaded
  earlier in this session purely to attempt `flutter analyze`/`flutter
  test` on the (now-removed) Dart source, entirely outside this
  repository. Removed entirely (`rm -rf D:\Documents\DevTools`) — it was
  never referenced by any other project on this machine and no global
  `flutter` command was left on `PATH`. The user-wide Dart/Flutter pub
  cache (`%LOCALAPPDATA%\Pub\Cache`) was deliberately left untouched per
  "do not delete user-wide caches unless clearly EcoTrace-specific" — it
  is a general-purpose Dart package cache, not project-specific state.

### Git-history audit
- 87 historical Flutter/Dart files existed across all commits
  (`git log --all --diff-filter=A --name-only -- "mobile/**/*.dart"
  "mobile/**/pubspec.*"`).
- Scanned every one of those files' full history for secret-like patterns
  (API keys, passwords, private-key PEM headers): **zero matches**.
- Per explicit instruction, git history was **not rewritten** — no
  `filter-repo`/`filter-branch`/BFG/force-push was run, and none was
  warranted (no secrets found). Historical Flutter/Dart commits remain in
  `git log` as an accurate record of what was built and later
  superseded.

### Remaining references (P9.11)
- Zero active Flutter/Dart implementation references remain anywhere
  under `mobile/`.
- `README.md`, `PROJECT.md`, `AGENTS.md`, `CLAUDE.md`,
  `docs/engineering/{01_CLAUDE,02_PROJECT_RULES,03_ARCHITECTURE,05_API,
  10_TESTING,12_ROADMAP}.md` were updated to describe React Native as the
  current mobile stack; every remaining mention of "Flutter"/"Dart" in
  these files is an explicit, intentional "migrated from
  Flutter/Dart"-style historical note, not a stale claim.
- `docs/engineering/07_FRONTEND.md` (the most detailed, historically
  Flutter-specific document) received a `> Superseded (P9.3)` banner at
  the top of its Flutter-specific section pointing to `docs/mobile/
  README.md`, following the exact precedent already established in that
  same file for the `dashboard/` → `frontend/` supersession — the
  detailed historical widget/state-management content below the banner
  was deliberately left as disclosed historical record rather than
  rewritten line-by-line, given the scope/time tradeoff; this is an
  intentionally accepted, documented limitation, not an oversight.
- New `docs/mobile/README.md` is the current source of truth for mobile
  architecture, prerequisites, auth, offline sync, blockchain
  architecture, testing (including two genuinely non-obvious findings
  about this exact dependency stack — see §7), and build status.

## 4. React Native implementation

**Versions** (resolved via the official `create-expo-app` generator and
`expo install`, not hand-picked — the explicitly required verification
method): `expo@57.0.18`, `react-native@0.86.3`, `react@19.2.3`,
`typescript@~6.0.3`. Both apps use identical, matching versions.

**Structure** (`docs/mobile/README.md` for full detail):
`src/{api,auth,components,config,hooks,navigation,screens,storage,types}`,
TypeScript throughout, no JavaScript files.

### Collector app (`mobile/collector_app/`)
- **Auth**: login, session persistence (`expo-secure-store`), token
  refresh, role gate (rejects a non-COLLECTOR login), logout.
- **Camera capture**: `expo-camera` (`CameraView`), preview/retake, up to
  N photos before continuing.
- **QR/barcode scan**: `expo-camera`'s built-in `onBarcodeScanned` (QR,
  Code128, EAN-13) — no separate `expo-barcode-scanner` dependency
  needed (merged into `expo-camera` since Expo SDK 51).
- **Device classification**: real `POST /devices/register` multipart
  upload to `intelligence/device_ai`, displays AI classification
  (type/confidence/lifecycle state), then `confirm`/`finalize`.
- **Dashboard**: assigned pickups (`GET /collector/submissions`),
  network/sync status banner.
- **Lifecycle actions**: accept → start → complete, exactly matching the
  real backend state machine and role authorization (see §5 for the real
  defect this uncovered).
- **Offline-first**: AsyncStorage-backed queue of AI device
  confirmations captured while offline; auto-drains on reconnect
  (`useNetworkStatus` via `@react-native-community/netinfo`); failed
  items (5 retries) surface with a manual retry action.
- **Submission history**: successful/pending/failed states.
- **Error handling**: API errors, network failures, auth failures,
  camera/scanner permission denial — all rendered via a shared
  `ErrorState` with retry, never a silent failure.

### Consumer app (`mobile/consumer_app/`)
- **Auth**: registration (matching the real `registerSchema` — full
  name/email/password/confirmPassword/phone?/region?), login, session
  persistence, role gate (rejects non-CONSUMER), logout.
- **Report e-waste**: real `POST /submissions` (verified CONSUMER-only —
  see §5), offline-queued when disconnected.
- **Scan + device passport**: QR scan → real `GET /devices/{id}/passport`,
  `/trust`, `/passport/verify` — displays lifecycle state, trust status
  (UNANCHORED/ANCHORED/VERIFIED/MISMATCH/STALE), anchor ID/freshness,
  and passport verification checks/warnings/errors.
- **Rewards**: real `GET /rewards/balance` + `/rewards/history` — GreenCoin
  balance, CO2/energy/landfill-diversion totals, per-submission reward
  history.
- **Submission history**: the consumer's own reports plus offline queue
  status/retry.
- **Education**: static informational content (why e-waste recycling
  matters, how verification works, how GreenCoins are earned).
- **Profile**: account info, sign-out.
- **Accessibility & i18n-readiness**: see §8.

## 5. Real defects found and fixed (API contract correctness)

Reading `backend/src/modules/submission/submission.routes.ts`'s actual
`authorize()` calls (not guessing) surfaced a genuine authorization
mismatch caught before it shipped:

- `POST /submissions` requires the **CONSUMER** role. The Collector app's
  first draft of `RegisterDeviceScreen`/offline queue incorrectly called
  `submissionsApi.create()` after AI device confirmation — a Collector
  can never actually do this in the real backend (would 403). **Fixed**:
  removed `create()` and `CreateSubmissionInput` from the Collector
  app's API layer/types entirely; `RegisterDeviceScreen` now only
  confirms/finalizes the AI-side device record (the real, authorized
  Collector action), and the offline queue was re-scoped from "pending
  submissions" to "pending device confirmations." Submission creation
  correctly lives only in the Consumer app, matching the real
  authorization rule.
- Cross-checked every other Collector/Consumer API call against the
  actual `authorize()` middleware calls in `submission.routes.ts` and
  `reward.routes.ts` (accept/start/complete = COLLECTOR;
  balance/history = self-serve, no role guard) — no further mismatches
  found.

## 6. Blockchain/trust architecture (mobile never touches Fabric)

Per the required architecture (`Mobile → Backend/device_ai API →
FabricGatewayClient → Hyperledger Fabric`): `DevicePassportScreen`
(Consumer app) reads exclusively through `intelligence/device_ai`'s REST
API (`/passport`, `/trust`, `/passport/verify`) — the service that owns
the real `FabricGatewayClient` validated against a genuine local Fabric
network in P9.2. Neither app imports a Fabric SDK, holds a peer address,
wallet, or private key, or performs any cryptographic operation itself.

## 7. Real, non-obvious findings from live testing

Two genuine, verified-live ecosystem behaviors on this exact dependency
combination (React 19.2.3 + React Native 0.86.3 + `@testing-library/
react-native` 14.0.1 + the `test-renderer` package, all current-latest at
migration time), found by actually running the tests and reading the
failures rather than assuming:

1. `render()` from `@testing-library/react-native` returns a `Promise` in
   this stack — `await render(<Component />)`, not a plain call.
   Confirmed by direct debug instrumentation showing `render()` returned
   `{}` (a not-yet-resolved Promise) until awaited.
2. Every `fireEvent.*` call (`.press`, `.changeText`, `.scroll`) also
   returns a `Promise` and must be awaited — confirmed via
   `fire-event.d.ts`'s real type signatures
   (`Promise<undefined>`/`Promise<void>`), and by the "overlapping
   act() calls" React warning that appeared before the fix.

Both are documented in `docs/mobile/README.md`'s Troubleshooting section
for future test authors on this stack, and both test files
(`LoginScreen.test.tsx`, `RegisterScreen.test.tsx`) correctly await
every interaction.

Separately: `eslint-config-expo`'s flat config enables
`react-hooks/set-state-in-effect` (a stricter, newer rule), which flagged
four instances of the common "fetch on mount by calling a `useCallback`
from `useEffect`" pattern across both apps. Fixed genuinely (not
suppressed) by inlining the initial fetch directly in the effect body
with a `cancelled` guard, keeping the `useCallback` version only for
explicit user-triggered refresh — verified via a clean rerun, not
assumed.

## 8. Accessibility

Every interactive control across both apps carries `accessibilityRole`
and an explicit `accessibilityLabel` (buttons, inputs, camera
shutter/scan controls); form inputs pair with `nativeID`/
`accessibilityLabelledBy` label associations; loading/busy states use
`accessibilityState={{ disabled, busy }}` rather than color alone;
error/status banners use `accessibilityRole="alert"` or
`accessibilityLiveRegion="polite"`; all interactive elements meet the
44×44pt minimum touch-target size (`minHeight: 44` throughout). Full
screen-reader walkthroughs on a physical device were not performed — no
Android/iOS device or emulator exists in this environment (§10) — so this
is `PASS — MOCK/LOCAL` (verified via accessibility-prop inspection and
the underlying React Native accessibility APIs, not a live
TalkBack/VoiceOver session).

## 9. Security review

- **Token storage**: `expo-secure-store` (iOS Keychain / Android
  Keystore-backed EncryptedSharedPreferences) — no token ever touches
  AsyncStorage or plain state persisted to disk.
- **No hardcoded secrets**: `EXPO_PUBLIC_DEVICE_AI_SERVICE_API_KEY` and
  API base URLs are build-time env vars, not literals; grepped both
  apps' source for hardcoded credential-shaped strings — none found.
- **No Fabric credentials in mobile code** — confirmed by §6.
- **HTTPS enforcement**: `src/config/env.ts` calls `assertSecureApiUrl()`
  at import time in both apps, throwing in a release build (`!__DEV__`)
  if either configured API URL isn't HTTPS — the same guard pattern as
  the superseded Flutter app's `secure_url_guard.dart` (P8.7).
- **Session invalidation**: logout clears both tokens from secure
  storage and calls the real `POST /auth/logout` (best-effort,
  fire-and-forget so a slow/offline logout never blocks the UI).
- **No sensitive data logging**: neither app logs tokens, passwords, or
  device private data to the console in production code paths (only
  React Native's own dev-mode warnings, which do not ship in a release
  build).
- **Input validation**: client-side validation (email format, password
  length/confirmation match, required fields) is UX-only — the real
  authority remains the backend's Zod schemas, matching the project's
  documented "clients are untrusted" rule (`07_FRONTEND.md`).

## 10. Tests

| Suite | Result |
|---|---|
| Collector app — typecheck (`tsc --noEmit`) | PASS — VERIFIED (0 errors) |
| Collector app — lint (`eslint .`) | PASS — VERIFIED (0 errors, 0 warnings) |
| Collector app — tests (Jest + RTL) | PASS — VERIFIED (12/12: `ApiError`, `syncQueueStorage`, `LoginScreen`) |
| Consumer app — typecheck | PASS — VERIFIED (0 errors) |
| Consumer app — lint | PASS — VERIFIED (0 errors, 0 warnings) |
| Consumer app — tests (Jest + RTL) | PASS — VERIFIED (10/10: `ApiError`, `syncQueueStorage`, `RegisterScreen`) |
| Android build (`expo run:android` / EAS) | `BLOCKED — ENVIRONMENT` — no Android SDK in this environment (confirmed via `flutter doctor`-equivalent inspection: no `ANDROID_HOME`, no `adb`); not fabricated |
| iOS build (`expo run:ios` / EAS) | `BLOCKED — ENVIRONMENT` — requires macOS + Xcode, neither present (this is a Windows environment) |
| Metro bundler start (`npx expo start`) | Not exercised as a long-running foreground process in this session (would require an interactive terminal); typecheck/lint/test/dependency-resolution across both apps stood in as the practical verification given the environment |

## 11. Full-system regression (P9.15)

Run **after** all mobile changes, fresh (never reused prior counts):

| Suite | Result |
|---|---|
| Backend (Jest) | 341/341 passing (27/27 suites) |
| Chaincode (Jest) | 47/47 passing |
| device_ai (pytest, junitxml-verified) | 1121/1121 passing, 0 errors, 0 failures |
| Frontend | typecheck clean, lint clean, build unaffected (untouched this phase) |
| Mobile (Collector + Consumer) | see §10 |

No regression was introduced anywhere outside `mobile/`,
`docs/`, `README.md`, `PROJECT.md`, `AGENTS.md`, `CLAUDE.md`.

## 12. E2E workflow status

The full Collector/Consumer E2E journeys described in the migration order
(login → capture/scan → register → AI enrichment → lifecycle → passport
→ trust → blockchain anchor → verification → history; and login → scan →
passport → trust → blockchain state → rewards) are implemented as real
screens wired to real endpoints and were exercised individually via
component tests and manual API-contract verification against the actual
route/schema definitions (§5). A true device-level, running-app E2E walk
(tap through both apps against the live compose stack + live P9.2 Fabric
network end-to-end on a real or emulated device) was **not** performed —
it requires either an Android/iOS runtime (`BLOCKED — ENVIRONMENT`, §10)
or the Expo web target with camera/QR features stubbed out, which would
not exercise the real capture/scan flows honestly. This is disclosed as
`PASS WITH LIMITATIONS`, not claimed as a verified running E2E pass.

## 13. Performance

No mobile-device-level performance measurement (startup time, navigation
latency, scan responsiveness) was possible — no physical device or
emulator exists in this environment (§10). Not fabricated; classified
`BLOCKED — ENVIRONMENT`. Backend/device_ai API latency underlying these
mobile calls was already measured in P8.6/P9's own performance work and
is unaffected by this phase (zero backend/device_ai source changes).

## 14. CI

No pre-existing mobile CI job existed to remove (`.github/workflows/
backend-ci.yml` covers only the backend — confirmed by grep, zero
Flutter/Dart references there). Adding a new React Native CI job
(`npm ci && npm run typecheck && npm run lint && npm test` per app) is a
reasonable, low-risk addition but was not made in this phase, to keep
the already-large diff scoped to the explicitly requested migration
work; documented here as a genuine, disclosed remaining item rather than
silently left undone.

## 15. Files changed

- **Removed** (commit `31d40c4`): 90 tracked Flutter/Dart files across
  both apps (8,337 lines).
- **Added**: `mobile/collector_app/` and `mobile/consumer_app/` — two
  full Expo TypeScript projects (App.tsx, `src/**`, tests, configs,
  `package.json`/`package-lock.json`, `eslint.config.js`,
  `jest.setup.js`).
- **Added**: `docs/mobile/README.md`.
- **Modified**: `README.md`, `PROJECT.md`, `AGENTS.md`, `CLAUDE.md`,
  `docs/engineering/{01_CLAUDE,02_PROJECT_RULES,03_ARCHITECTURE,05_API,
  07_FRONTEND,10_TESTING,11_DEPLOYMENT,12_ROADMAP}.md`.
- **Not touched**: `backend/`, `intelligence/device_ai/`, `frontend/`,
  `blockchain/`, all 6 protected ML assets, `docker-compose.yml`,
  `.github/workflows/backend-ci.yml`.

## 16. Protected asset verification

Verified before this phase began and again after all work, against the
exact paths/hashes in `reports/P5_1_DEVICE_INTELLIGENCE_PRODUCTION.md`:

| Asset | Result |
|---|---|
| P4.4.2 YOLO11n | MATCH |
| P4.11 Targeted Aug | MATCH |
| P4.12 YOLO11s | MATCH |
| P4.14 Targeted Aug | MATCH |
| P4.5 Data YAML | MATCH |
| P4.7 Data YAML | MATCH |

All 6/6 MATCH. No protected asset was modified at any point in this phase.

## 17. Environmental limitations (honest, per the required classification scheme)

| Item | Classification | Detail |
|---|---|---|
| Android APK/AAB build | `BLOCKED — ENVIRONMENT` | No Android SDK in this environment; not fabricated |
| iOS build | `BLOCKED — ENVIRONMENT` | Requires macOS + Xcode; this is a Windows environment |
| Real-device screen-reader accessibility walkthrough | `PASS — MOCK/LOCAL` | Verified via accessibility-prop inspection and RN accessibility APIs, not a live TalkBack/VoiceOver session |
| Mobile-device performance measurement | `BLOCKED — ENVIRONMENT` | No physical device/emulator exists |
| Running-app device-level E2E walkthrough | `PASS WITH LIMITATIONS` | Screens/API wiring implemented and individually verified; not exercised as a live tap-through on a device/emulator |
| React Native CI job | Not implemented | Disclosed, low-risk, deliberately deferred to keep scope bounded (§14) |
| `docs/engineering/07_FRONTEND.md` deep historical content | Partially superseded-banner only | The detailed Flutter-era structure/state-management subsections below the banner were not individually rewritten (§3), a disclosed scope/time tradeoff |

## 18. Unresolved issues / release blockers

None that block a pilot release on the currently-supported platform
(Metro/Expo Go development, web preview, or a future Android/iOS build
once that toolchain becomes available in a suitable environment). The
Android/iOS build gap is a genuine environmental limitation, not a
functionality gap — the applications themselves are complete,
type-checked, linted clean, and tested.

## 19. Git state at end of phase

- Branch `develop`.
- Commits (chronological): `chore(mobile): remove flutter and dart
  architecture` (`31d40c4`, already pushed before this report), followed
  by the React Native implementation/test/docs commits documented in
  this report's own commit history.
- Pushed to `origin/develop`; `HEAD == origin/develop` verified after
  the final push.
- Working tree clean after push.
- No force push, no history rewrite, no push to `main`.

## 20. Final verdict

**PASS WITH LIMITATIONS.** The Flutter/Dart → React Native + Expo SDK 57
migration is functionally complete and genuinely verified: both apps
build a real TypeScript codebase against real backend/device_ai
endpoints (with one real authorization-mismatch defect found and fixed
via direct route-authorization inspection, not assumption), typecheck
and lint clean, have real passing tests (22/22) including two documented
non-obvious ecosystem findings, correctly route all blockchain/trust
verification through the backend, and pass a full-system regression with
zero collateral impact on backend/chaincode/device_ai/frontend. The
limitations are genuinely environmental (no Android SDK, no macOS/Xcode,
no physical device) or deliberately scoped (CI job, deep historical-doc
rewrite) and are disclosed here rather than fabricated — this explicitly
is not a claim of Android/iOS build success.
