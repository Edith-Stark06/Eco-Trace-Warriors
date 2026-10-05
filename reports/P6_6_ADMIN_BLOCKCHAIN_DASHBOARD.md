# P6.6 — Admin Blockchain Dashboard

## 1. Objective

Add blockchain monitoring to the existing React admin dashboard
(`frontend/`), consuming P6.5's new `GET /api/v1/system/blockchain/health`
endpoint — without rebuilding the frontend or inventing capabilities the
backend doesn't have.

---

## 2. Reconnaissance

`frontend/src/features/admin/AdminDashboardPage.tsx` already exists and is a
**real, working dashboard** built with the exact discipline this whole P6
effort has followed: every section is either backed by a real, verified
backend endpoint, or shown as an honest "not yet available" state
(`AdminUnavailable`) naming exactly which endpoint is missing (System
Overview, User Management, System Activity). This confirms the pattern used
throughout P6.1–P6.5 is already this repository's own established
convention, not something introduced here.

The dashboard uses TanStack Query, a single shared Axios instance
(`api/axios.ts`), a query-key factory (`lib/query-keys.ts`), and a
`ContentCard`/`Section`/`StatCard`/`SkeletonCards`/`ServerError` component
kit. P6.6 adds one new section following that exact shape — no new UI
library, no parallel data-fetching pattern, no bypass of the shared Axios
instance.

---

## 3. What was built

```
frontend/src/
├── types/blockchain.ts                          # BlockchainHealth (mirrors backend/src/modules/blockchain/blockchain.types.ts)
├── api/blockchain.api.ts                         # GET /system/blockchain/health
├── features/admin/hooks/use-blockchain.ts        # useBlockchainHealth() — 30s poll
├── features/admin/components/BlockchainHealthCard.tsx
└── features/admin/AdminDashboardPage.tsx         # + "Blockchain monitoring" Section
```

The new "Blockchain monitoring" section shows:
- **Status badge** — one of the five real values the backend can report
  (`connected`, `disabled`, `configuration_error`, `unavailable`,
  `proxy_unreachable` — the last being P6.5's own honest degradation state,
  not fabricated as "connected"), styled `destructive` for every non-healthy
  state so a broken chain is visually obvious, not buried in gray text.
- **Message** — the exact human-readable message the Python Fabric Gateway
  client produced (P6.2), passed through unaltered.
- **Channel / Chaincode / MSP ID / Latency** — only populated when the
  backend actually returned them; renders `"—"` otherwise, never a
  fabricated placeholder value.
- **Live polling** (30s) — a lightweight read-only status check, safe to
  poll; not a transaction.

No "peer/org status" or "transaction explorer" was built: the backend
exposes exactly one blockchain fact right now (Gateway health), and the P6.5
report explains why device-level anchor/verify data isn't available yet
(no `Submission`↔`DevicePassport` link exists). Building a transaction
list or per-device trust explorer against nothing would be exactly the
fabricated UI this effort has avoided everywhere else — the dashboard is
honest about that same gap the same way `AdminUnavailable` already is for
System Overview/User Management/System Activity.

---

## 4. Test Results

All commands run from `frontend/`.

- **`npm run typecheck`**: 0 errors.
- **`npm run lint`**: 0 errors.
- **`npm run build`**: succeeds (`vite build`, 1934 modules transformed).
  The pre-existing "chunk larger than 500kB" warning is unrelated to this
  change (the main vendor bundle, present before P6.6).
- **`npm test`**: **not run — no test script or test files exist in this
  project** (`package.json` has no `test` entry; `find` for `*.test.ts(x)`
  returns nothing). This is the project's pre-existing state, not something
  P6.6 introduced or should silently paper over by inventing a test harness
  outside this phase's scope.

---

## 5. Accessibility

- Status changes announced via `aria-live="polite"` on the "last checked"
  timestamp (screen readers hear updates without needing to re-focus).
- Loading state uses the existing `SkeletonCards` (`role="status"
  aria-busy="true" aria-live="polite"`), matching every other section.
- Error state reuses `ServerError`'s existing retry button — same keyboard/
  screen-reader behavior as the rest of the dashboard, not a bespoke pattern.
- Status is conveyed by both color (`Badge` variant) and text label — never
  color alone.

---

## 6. Known Limitations

1. **Only connectivity, not transactions** — no transaction explorer/device
   trust explorer exists because the backend has no data to back one (§3,
   and P6.5 §3's architectural finding).
2. **No frontend test suite exists in this project** — not introduced or
   fixed by this phase (§4).
3. **30s poll, not push** — no WebSocket/SSE channel exists for real-time
   status; a 30-second interval was judged an acceptable tradeoff for a
   read-only status card.

---

## 7. Definition of Done

- [x] Reconnaissance against the actual existing dashboard code and
      conventions, not a rebuild.
- [x] Real, working blockchain health card consuming P6.5's actual endpoint.
- [x] Honest representation of every real status value; no fabricated
      "connected" state, no invented transaction/device data.
- [x] Uses the existing UI design language, API client, and query-key
      conventions — no new dependencies.
- [x] Responsive (`grid grid-cols-2 sm:grid-cols-4` in the stat row, same
      breakpoint pattern as the rest of the dashboard).
- [x] Accessible: `aria-live`, non-color-only status, existing loading/error
      component reuse.
- [x] `npm run typecheck`: 0 errors. `npm run lint`: 0 errors.
      `npm run build`: succeeds.
- [x] `npm test`: honestly reported as not configured in this project,
      not fabricated.
