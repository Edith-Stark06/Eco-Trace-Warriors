# P6.5 — Backend Blockchain Integration

## 1. Objective

Integrate the mobile-facing `backend/` (Express/Prisma, what P6.3/P6.4 talk
to) with the working Fabric blockchain trust layer built in P6.1 (chaincode)
and P6.2 (Python Fabric Gateway client in `intelligence/device_ai`).

---

## 2. Audit: is P6.2's blockchain integration still green?

Re-run in this phase, per the instruction to always report current numbers
rather than trust prior reports:

- **`intelligence/device_ai` full suite**: `python -m pytest` → **1072
  passed, 1 failed** (`tests/test_detector_benchmark.py::test_benchmark_measures_latency_and_throughput`
  — the same pre-existing, unrelated, machine-timing-dependent failure
  documented in `reports/P6_2_FABRIC_GATEWAY_INTEGRATION.md` §10; confirmed
  via `git status` that neither that test file nor the code it exercises has
  changed since). **Unchanged from P6.2.**
- **P6.1 chaincode**: `npx jest` in `blockchain/chaincode/ecotrace-lifecycle/`
  → **45/45 passed**. Unchanged.
- **`backend/`** (not touched by P6.2, baseline for this phase): `npm test`
  → **312/312 passed** before this phase's changes.

Conclusion: P6.2's blockchain integration (device passport anchor/verify via
`FabricExternalTrustLedger` + `FabricGatewayClient`) remains fully working
and untouched. There is nothing to fix there.

---

## 3. The real integration gap: two disconnected systems

Reconnaissance (continuing from P6.4 §2) found the actual obstacle to a
deeper integration:

- `backend/`'s `Submission` model (`prisma/schema.prisma`) — the pickup
  request P6.3/P6.4 are built around — has **no `deviceId`, no
  `passportFingerprint`, no `ecoId` field**. It is a category/weight/address
  record with zero relationship to `intelligence/device_ai`'s
  `DeviceRecord`/`DevicePassport` concept.
- `backend/src` has **zero references** to `passportFingerprint`,
  `DevicePassport`, `device_ai`, or port `8100` anywhere (`grep` across the
  whole source tree) before this phase.
- `backend/src/infrastructure/fabric/fabric.client.ts` and
  `infrastructure/ai/ai.client.ts` are explicit placeholders marked "Phase 7
  (Blockchain)" / "Phase 8 (AI)" respectively, wired into no module or route.

**A genuine device-level integration** (anchor a specific submission's
device passport, verify it on-chain, show per-device trust status) would
require linking these two domain models — e.g. adding a
`devicePassportFingerprint` column to `Submission`, or a join table. That is
a real product/schema decision (which fields, which workflow step populates
them, whether a `Submission` even has a 1:1 AI-detected device at all) that
this phase's scope — "connect the existing pieces," not "invent a new data
model" — does not include. Per Phase 13's constraint carried over from
P6.2 ("Do not add a new blockchain anchor table unless the existing schema
is genuinely insufficient... only modify PostgreSQL schema if repository
inspection proves it's required") and this repository's own
`CLAUDE.md` ("Never modify database schemas without updating documentation
... Avoid destructive schema changes unless explicitly requested"), forcing
that link now — without a product decision on what it should mean — would
be exactly the kind of invented, undirected schema change these rules exist
to prevent.

---

## 4. What was actually built: a real, working blockchain health proxy

The one integration that is genuinely real, valuable, and possible without
a schema change: **`backend/` now proxies a read-only Fabric health check
to the Python service**, so anything talking to `backend/` (the mobile apps,
and the P6.6 admin dashboard) can see real blockchain connectivity status
through the same API they already use — rather than needing to know a
second service exists.

```
Mobile / Admin Dashboard
        │
        ▼
GET /api/v1/system/blockchain/health   (backend/, new — P6.5)
        │
        ▼  (HTTP, read-only, degrades gracefully)
GET /system/blockchain/health          (intelligence/device_ai, P6.2)
        │
        ▼
FabricGatewayClient.health_check()     (P6.2 — real TLS/gRPC probe)
```

- **New module**: `backend/src/modules/blockchain/` (service/controller/
  routes/types, mirroring the existing `health` module's shape).
- **Config**: `DEVICE_AI_SERVICE_URL` (default `http://localhost:8100`),
  `DEVICE_AI_TIMEOUT_MS` (default `5000`) — added to `env.schema.ts`,
  `config.ts`, `.env.example`.
- **Route**: `GET /api/v1/system/blockchain/health` — public (no auth), like
  `/health`/`/ready`, since it reports infrastructure status, not user data.
- **Degradation, never fabrication**: a network failure, timeout, non-OK
  response, or unexpected payload shape from the Python service all resolve
  to `{status: "proxy_unreachable", ...}` — the route **always returns
  HTTP 200** with an honest status field; it never throws a 5xx for "the
  other service is down," and it never reports `"connected"` unless the
  Python service's own real health check said so.
- **Node's built-in global `fetch`** (Node 18+) — no new HTTP client
  dependency was added.

`submitTransaction`/`evaluateTransaction` (the write/anchor side of
`FabricClient`) remain the Phase-7 placeholder, honestly — see §3 for why
wiring them up meaningfully requires the schema decision this phase didn't
make unilaterally.

---

## 5. Test Results

All commands run from `backend/`.

- **`npm test`**: **323 / 323 passed** (312 pre-existing + 11 new: 7 unit
  tests for `BlockchainService` — successful mapping, disabled-state
  fidelity, network-failure degradation, non-OK-response degradation,
  malformed-payload degradation, trailing-slash URL handling, and a
  dependency-shape guard — plus 4 integration tests for the route,
  including one that exercises the **real**, unmocked service against the
  configured default URL with nothing listening there, proving the
  degradation path works end-to-end, not just through an injected fake).
- **`npm run lint`**: 0 errors (after fixing 12 real `@typescript-eslint`
  findings in the new test files — `require-await` on async functions with
  no `await`, and one unnecessary type assertion; all genuine, not
  hypothetical).
- **`npm run typecheck`**: 0 errors.
- **`intelligence/device_ai` full suite**: 1072/1072 (1 pre-existing,
  unrelated failure — §2).
- **P6.1 chaincode**: 45/45 (§2).
- **Protected assets**: all 6 verified byte-for-byte unchanged (unrelated
  to this phase's scope, re-checked per the work order's standing
  requirement).

---

## 6. Known Limitations

1. **No device-level blockchain integration** — anchoring/verifying a
   specific submission's device passport is blocked on a real data-model
   decision linking `Submission` to `DevicePassport`, not attempted
   unilaterally (§3).
2. **`FabricClient.submitTransaction`/`.evaluateTransaction` remain
   unimplemented placeholders** in `backend/` — only the health/query side
   was connected.
3. **The health proxy adds one more network hop** (mobile → backend →
   device_ai) versus calling the Python service directly — acceptable
   given the mobile apps otherwise have no reason to know that service
   exists, and matches this backend's existing pattern for `ai.client.ts`.
4. **No caching** of the health result — every call to the new route makes
   a fresh upstream request (matching the Python service's own health
   check, which is itself a live probe, not cached).

---

## 7. Definition of Done

- [x] P6.2's existing blockchain integration re-verified green with current
      numbers (§2), not assumed from the prior report.
- [x] Genuine architectural gap (disconnected `Submission`/`DevicePassport`
      models) identified and documented rather than papered over (§3).
- [x] Real, working, read-only blockchain health integration connecting
      `backend/` to the P6.2 Fabric Gateway (§4).
- [x] Honest, graceful degradation — never a fabricated "connected" status,
      never a 5xx for an unreachable upstream.
- [x] No schema change made without a product decision to justify it.
- [x] `npm test`: 323/323. `npm run lint`: 0 errors. `npm run typecheck`: 0 errors.
- [x] P5/P6.1/P6.2 regressions re-verified green.
- [x] Protected assets: 6/6 MATCH.
