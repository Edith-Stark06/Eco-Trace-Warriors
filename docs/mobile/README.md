# EcoTrace India — Mobile Apps (React Native + Expo)

Version: 1.0 · Status: Active

Superseded (P9.3) a planned Flutter/Dart mobile stack that was never
shipped to source — see `reports/P9_3_MOBILE_REACT_NATIVE.md` for the
full migration record, including the git-history audit.

---

## Architecture

Two independent Expo projects, `mobile/collector_app/` and
`mobile/consumer_app/` — not a shared codebase. Each is a real,
independently runnable React Native app.

```
mobile/<app>/
├── App.tsx                 # entrypoint: SafeAreaProvider > AuthProvider > RootNavigator
├── src/
│   ├── api/                # apiClient (fetch + token refresh), per-domain API modules
│   ├── auth/                # AuthContext (session lifecycle, secure-storage-backed)
│   ├── components/          # shared UI: LoadingIndicator, ErrorState, EmptyState, NetworkStatusBanner
│   ├── config/               # env.ts — EXPO_PUBLIC_* build-time config + release HTTPS guard
│   ├── hooks/                # useNetworkStatus, useSyncManager, useSubmissions, ...
│   ├── navigation/            # RootStackParamList + RootNavigator (@react-navigation/native-stack)
│   ├── screens/               # one file per screen
│   ├── storage/               # secureStorage (expo-secure-store), syncQueue (AsyncStorage)
│   └── types/                  # TypeScript types mirroring the real backend/device_ai response shapes
```

Prerequisites:
- Node.js 20+ (this repo was validated against Node 24.18.0)
- npm
- Expo SDK 57 / React Native 0.86.3 / React 19.2.3 / TypeScript ~6.0.3 (pinned via `npx expo install`, not hand-picked)
- For a real device/emulator build: Android Studio + Android SDK (Android), or macOS + Xcode (iOS) — neither is required for `typecheck`/`lint`/`test`, only for `expo run:android`/`expo run:ios`/EAS builds

## Two-system split (why Collector never creates a Submission)

Two independent backend systems exist (`docs/engineering/03_ARCHITECTURE.md`):

- **The Node backend's `Submission` model** — a pickup job.
  `POST /submissions` requires the **CONSUMER** role
  (`backend/src/modules/submission/submission.routes.ts`). A **COLLECTOR**
  only acts on a submission an Admin/Government has already assigned to
  them: accept → start → complete.
- **`intelligence/device_ai`'s Device/passport/trust lifecycle** — the
  AI-side record. A Collector's camera-capture flow classifies, confirms,
  and finalizes a device record here; it does not touch the Submission
  model at all.

This matters for the Collector app specifically: `RegisterDeviceScreen`
intentionally never calls `POST /submissions` — that authorization
mismatch was found and fixed during P9.3's own implementation (see the
report).

## Backend/device_ai configuration

Neither app has a runtime `.env` file — Expo bakes `EXPO_PUBLIC_*`
variables in at build time (`src/config/env.ts`):

| Variable | Default (dev) | Purpose |
|---|---|---|
| `EXPO_PUBLIC_API_BASE_URL` | `http://localhost:3000/api/v1` | Node backend (auth, submissions, rewards) |
| `EXPO_PUBLIC_DEVICE_AI_BASE_URL` | `http://localhost:8100` | Python device_ai service (AI inference, passport, trust) |
| `EXPO_PUBLIC_DEVICE_AI_SERVICE_API_KEY` | unset | Only needed if the device_ai deployment has `SERVICE_API_KEY` set (P8.7) |

`src/config/env.ts` calls `assertSecureApiUrl()` at import time, which
throws in a release build (`!__DEV__`) if either URL is not HTTPS —
mirrors the superseded Flutter app's `secure_url_guard.dart` (P8.7).

## Authentication

`src/auth/AuthContext.tsx` owns the session: login/register call the real
`/auth/login`/`/auth/register` endpoints, tokens are stored via
`expo-secure-store` (`src/storage/secureStorage.ts` — Keychain on iOS,
Keystore-backed EncryptedSharedPreferences on Android), and a role guard
rejects a login/register response whose `user.role` isn't the app's own
role (COLLECTOR — or ADMIN, which can also drive the Collector API — for
the Collector app; CONSUMER for the Consumer app). `apiClient` refreshes
an expired access token exactly once per request via
`POST /auth/refresh` and retries.

## Offline-first sync

Both apps queue locally (AsyncStorage, `src/storage/syncQueue.ts`) and
drain the queue via `useSyncManager` whenever `useNetworkStatus`
(`@react-native-community/netinfo`) reports connectivity:

- **Collector**: queues AI device *confirmations* (`deviceAiApi.finalize`) captured while offline.
- **Consumer**: queues waste *reports* (`POST /submissions`) captured while offline.

A queued item that fails for a non-network reason (e.g. validation) is
retried up to 5 times before being marked `failed` and surfaced with a
manual retry action in the submission history screen.

## Blockchain/trust verification (mobile never touches Fabric directly)

Per the architecture rule: `Mobile → Backend/device_ai REST API →
FabricGatewayClient → Hyperledger Fabric`. The Consumer app's
`DevicePassportScreen` reads `GET /devices/{id}/passport`,
`/trust`, and `/passport/verify` from `intelligence/device_ai` — the
service that owns the real `FabricGatewayClient` (validated against a
real local Fabric network in P9.2) — and never handles a peer address,
wallet, or private key itself.

## Testing

```bash
cd mobile/collector_app   # or consumer_app
npm run typecheck          # tsc --noEmit
npm run lint                # eslint . (flat config, eslint-config-expo)
npm test                     # jest (jest-expo preset)
```

Two real, non-obvious things to know if you add tests on this exact
dependency stack (React 19.2.3 + `@testing-library/react-native` 14.0.1 +
the `test-renderer` package, all current-latest as of this migration):

1. **`render()` returns a `Promise`** — `const { getByTestId } = await render(<Component />)`, not a plain call.
2. **Every `fireEvent.*` call also returns a `Promise`** — `await fireEvent.press(...)`, `await fireEvent.changeText(...)`. Skipping either produces "overlapping act() calls" warnings and queries that silently miss the current tree.

`jest.setup.js` in each app wires the official
`@react-native-async-storage/async-storage/jest/async-storage-mock` —
without it, any test touching `syncQueue`/AsyncStorage fails with
`NativeModule: AsyncStorage is null`.

## Building for a device

Neither Android SDK nor a macOS/Xcode toolchain existed in the
environment this migration was performed in — `npm run android` /
`npm run ios` (`expo run:android` / `expo run:ios`) and any EAS build
are classified `BLOCKED — ENVIRONMENT` in `reports/P9_3_MOBILE_REACT_NATIVE.md`,
not fabricated. `npx expo start` (Metro bundler) and the typecheck/lint/test
commands above were run and verified for real.

## Troubleshooting

- **`Cannot find module '@react-native-community/netinfo'`**: install it in *that specific app* — the two apps are independent projects with independent `node_modules`; a dependency installed in one is not automatically available in the other.
- **A hook that fetches on mount trips `react-hooks/set-state-in-effect`**: don't call a `useCallback`-wrapped async function directly from `useEffect`; inline the fetch in the effect body instead (see `src/hooks/useSubmissions.ts` for the pattern) — calling a same-file callback that eventually calls `setState`, even after an `await`, is flagged by this newer, stricter ESLint rule.
