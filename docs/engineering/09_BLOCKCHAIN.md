# 09 — Blockchain

# EcoTrace India — Blockchain Engineering Standards

Version: 2.0

Status: Active

---

# Table of Contents

1. [Purpose](#purpose)
2. [Role of the Blockchain](#role-of-the-blockchain)
3. [On-Chain vs Off-Chain Data](#on-chain-vs-off-chain-data)
4. [Architecture — Two Providers, One Interface](#architecture--two-providers-one-interface)
5. [Chaincode Design](#chaincode-design)
6. [Real Network Status (P9.2 / P9.6 / P9.7)](#real-network-status-p92--p96--p97)
7. [Default Mode: In-Memory Provider](#default-mode-in-memory-provider)
8. [Optional Mode: Live Fabric](#optional-mode-live-fabric)
9. [Bring-Up Procedure](#bring-up-procedure)
10. [Shutdown](#shutdown)
11. [Health Verification](#health-verification)
12. [Troubleshooting](#troubleshooting-windows--docker-desktop)
13. [Generated Files](#generated-files)
14. [Security Precautions](#security-precautions)
15. [Identity & Security (Production Direction)](#identity--security-production-direction)
16. [Failure Handling](#failure-handling)
17. [Directory Layout](#directory-layout)
18. [Testing Expectations](#testing-expectations)

---

# Purpose

This document defines the design and standards for the Hyperledger Fabric layer of EcoTrace India: what goes on-chain, how the network is shaped, how `intelligence/device_ai` integrates with it, and — as of P10.2 — exactly how to bring the real local network up and back down without tribal knowledge.

Governing rule (`CLAUDE.md`, `AGENTS.md`): the blockchain manages **immutable records, lifecycle events, verification, and audit trails** — nothing else.

---

# Role of the Blockchain

The ledger provides what PostgreSQL cannot: **tamper-evident, independently verifiable history**.

| Concern | System |
|---|---|
| Application state, queries, analytics | PostgreSQL (`04_DATABASE.md`) |
| Immutable device lifecycle + passport-fingerprint audit trail | Hyperledger Fabric (`ecotrace-lifecycle` chaincode) |
| Local operational trust (fast, always-available) | `TrustAnchorRepository` (memory or Postgres) inside `intelligence/device_ai` |
| External / blockchain trust verification | `ExternalTrustLedger` — `InMemoryExternalTrustLedger` (default) or `FabricExternalTrustLedger` (optional, real) |

The ledger is **not** a database. If a feature needs rich queries, mutable state, or large payloads, it belongs off-chain.

---

# On-Chain vs Off-Chain Data

## Stored on-chain

- `deviceId`, `ecoId` (identifiers only)
- Lifecycle state (`DETECTED` → `CONFIRMED` → `REGISTERED` → `ENRICHED`) + timestamp (from the transaction header, never the system clock) + actor role (not personal identity)
- SHA-256 fingerprint of the off-chain Device Passport (`passportFingerprint`) — never the passport contents
- The Fabric transaction ID that produced each anchor

## Never stored on-chain

- Personal data (names, emails, phones, addresses)
- Device images, raw OCR text, or file contents
- Material/carbon/condition/brand values themselves (only their fingerprint)
- GreenCoin balances or reward logic
- Any mutable application state

```mermaid
flowchart LR
    subgraph Off-chain — device_ai / PostgreSQL
        P[Full DevicePassport<br/>identity, detection, brand,<br/>condition, material, carbon]
    end
    subgraph On-chain — Fabric
        A[PassportAnchor<br/>deviceId, passportFingerprint,<br/>algorithm, anchoredAt, txId]
    end
    P -->|canonicalize_passport + SHA-256| A
    A -->|txId stored on| P
```

`intelligence/device_ai/devices/passport_verification.py::fingerprint_passport()` computes this hash deterministically (sorted-key canonical JSON, excludes the volatile `generated_at` field) — this is the actual, already-implemented "canonical payload → hash" step, not a future plan.

---

# Architecture — Two Providers, One Interface

**`intelligence/device_ai` is the only Fabric-aware service.** The Node backend (`backend/src/modules/blockchain/blockchain.service.ts`) is a **pure, read-only HTTP proxy** to device_ai's `GET /system/blockchain/health` — it holds no Fabric identity, no chaincode knowledge, no gRPC client, and degrades to `"proxy_unreachable"` honestly if device_ai is unreachable. Mobile apps never touch Fabric directly either (`docs/mobile/README.md`).

```
Mobile / Frontend
   ↓ REST only
Node backend — blockchain.service.ts (health proxy only)
   ↓ REST only
intelligence/device_ai
   ↓
DevicePassportTrustService (devices/trust_anchor.py)
   ↓
ExternalTrustLedger protocol (devices/external_trust.py)
   ├─ InMemoryExternalTrustLedger   ← DEFAULT (provider: "memory")
   └─ FabricExternalTrustLedger     ← OPTIONAL (provider: "hyperledger_fabric")
         ↓
      FabricGatewayClient (devices/fabric_gateway_client.py)
         — real gRPC client, hand-built against vendored, unmodified
           Fabric Gateway .proto files (blockchain/fabric-protos/)
         ↓ TLS gRPC (Endorse / Submit / CommitStatus / Evaluate)
      Fabric peer's Gateway service
         ↓
      ecotrace-lifecycle chaincode (blockchain/chaincode/ecotrace-lifecycle)
         ↓
      Ledger (channel "ecotrace-channel")
```

**Two distinct anchor endpoints exist** — do not confuse them:

| Endpoint | Touches Fabric? | Backed by |
|---|---|---|
| `POST /devices/{id}/passport/anchor`, `GET /devices/{id}/trust` | **No** | `TrustAnchorRepository` (local operational trust) |
| `POST /devices/{id}/passport/external-anchor`, `GET /devices/{id}/trust/full` | **Yes, when Fabric mode is active** | `ExternalTrustLedger` (memory or Fabric) |

The provider switch is a single point: `intelligence/device_ai/api/dependencies.py::build_external_trust_ledger()`.

---

# Chaincode Design

- **Language:** TypeScript (`fabric-contract-api`), compiled via `tsc`, deployed as **Chaincode-as-a-Service (CCaaS)**.
- **One contract, small surface.** Chaincode validates and records; it does not compute business outcomes.

The real, shipped contract (`blockchain/chaincode/ecotrace-lifecycle/src/ecotrace-lifecycle.ts`, 47/47 unit tests passing, live-deployed and live-transacted against in P9.2/P9.6/P9.7):

| Function | Type | Purpose |
|---|---|---|
| `RegisterDevice` | submit | Create the on-chain device identity (PLATFORM role only) |
| `UpdateLifecycle` | submit | Advance/record a lifecycle state transition |
| `AnchorDevicePassport` | submit | Anchor (or re-anchor) a passport fingerprint — PLATFORM only |
| `GetDevice` | evaluate | Read a device's current on-chain record |
| `DeviceExists` | evaluate | Existence check |
| `GetDeviceHistory` | evaluate | Full chronological event history for a device |
| `VerifyPassportFingerprint` | evaluate | Fingerprint match/mismatch against the anchored record |
| `GetDeviceAnchor` | evaluate | Read the currently anchored fingerprint |
| `GetAllDeviceIds` | evaluate | List every registered device id |

Chaincode rules:

- Strict forward-only lifecycle progression (`DETECTED → CONFIRMED → REGISTERED → ENRICHED`), enforced per-transition role gates (`requireRole()`).
- Deterministic only: timestamps come from `ctx.stub.getTxTimestamp()` (never the system clock), event ids are a per-device monotonic sequence, no randomness, no external calls.
- `intelligence/device_ai/devices/external_trust.py::FabricExternalTrustLedger.anchor()` performs a best-effort, idempotent `RegisterDevice` on-chain pre-step before every `AnchorDevicePassport` call, since the chaincode correctly rejects anchoring a device it has never registered (a real integration gap found live in P9.6, fixed and live-re-verified in P9.7).

---

# Real Network Status (P9.2 / P9.6 / P9.7)

**This is not a plan — a real local Fabric network has been built, transacted against, and independently re-verified three times**, using this repository's own unmodified chaincode and gateway client:

| Phase | What was proven, live | Report |
|---|---|---|
| P9.2 | A real 2-org + orderer network, CA-issued identities, channel `ecotrace-channel`, chaincode deployed as CCaaS, real signed transactions (`RegisterDevice`, `GetDevice` cross-org), real rejected-transaction error paths, the real `FabricGatewayClient` connecting/submitting/evaluating over real TLS gRPC | `reports/P9_2_LIVE_FABRIC.md` |
| P9.6 | A full cross-role E2E (collector registers/enriches/anchors → consumer reads back) through the real `device_ai` HTTP API against the still-running P9.2 network; found and disclosed a real bug (external-anchor failed without a prior on-chain `RegisterDevice`) | `reports/P9_6_FABRIC_BACKEND_MOBILE_E2E.md` |
| P9.7 | Fixed the P9.6 bug (auto `RegisterDevice` pre-step) and the two minor findings (redundant re-anchor write, wrong HTTP status code); **re-verified live with a brand-new device that was never manually pre-registered** | `reports/P9_7_PERFORMANCE_SECURITY_HARDENING.md` |

**Current state (as of this document's last update): the network is not running.** It is rebuilt on demand (see [Bring-Up Procedure](#bring-up-procedure)) rather than kept always-on, and its generated crypto material is intentionally ephemeral and untracked (see [Security Precautions](#security-precautions)).

---

# Default Mode: In-Memory Provider

`docker compose up` (the root `docker-compose.yml`) **intentionally does not start any Fabric services** — no peer, orderer, CA, or CouchDB container is defined there. `device-ai`'s `FABRIC_ENABLED` and `EXTERNAL_TRUST_BACKEND` both default off (`false` / `"memory"`), so:

- `GET /devices/{id}/trust/full` reports `provider: "memory"`, `external_status` computed against `InMemoryExternalTrustLedger` — a real, deterministic, in-process reference ledger (not a stub that always says "VERIFIED"; it genuinely tracks anchored fingerprints and reports `MISMATCH`/`NOT_FOUND` correctly).
- `GET /system/blockchain/health` reports `{"status": "disabled", ...}`.

This is the correct default for anyone running the demo stack without the ~350MB of Fabric binaries/images and the local network — including a judge or reviewer who just runs `docker compose up --build`.

---

# Optional Mode: Live Fabric

For a live demo or development session on a machine that has already run `blockchain/fabric-network/bootstrap/bootstrap.sh` once (downloads Fabric v2.5.16 binaries/images and clones `fabric-samples`), the real network can be brought up and wired to `device-ai` without touching the default stack.

## Prerequisites

- Docker Desktop, with `docker compose` (v2 plugin).
- `blockchain/fabric-network/bootstrap/bootstrap.sh` has been run once (one-time, network-heavy; the bring-up script never runs this automatically).
- The chaincode has been built once: `cd blockchain/chaincode/ecotrace-lifecycle && npm ci && npm run build`.

## Windows Docker Desktop requirements

Three real, root-caused environment defects were found and fixed while first achieving this (P9.2 §4) — the bring-up script encodes all of them:

1. **MSYS/Git-Bash path mangling.** `MSYS_NO_PATHCONV=1` (sometimes set for unrelated `openssl -subj` fixes) breaks native Windows binaries like `configtxgen.exe` that expect a real Windows path from an env var. Fix: `unset MSYS_NO_PATHCONV`, scope `MSYS2_ARG_CONV_EXCL="/etc/hyperledger;/var/hyperledger"` so only the compose files' *container-internal* paths are protected from translation.
2. **Docker Desktop container-creation race.** Starting the orderer and both peers together (`docker compose up -d` for all three) intermittently fails one or more with `mkdir C:\Program Files\Git\var: Access is denied`. Fix: start them **one at a time**, waiting for each to become reachable before starting the next.
3. **No host Unix `docker.sock`.** The classic (Docker-in-Docker) chaincode packaging flow needs a peer container to bind-mount `/var/run/docker.sock`; Windows Docker Desktop has no such file on the host. This is a genuine, unfixable-from-here platform incompatibility — **Chaincode-as-a-Service (CCaaS)** is used instead, which needs no peer-side Docker access at all: the chaincode runs as an ordinary host process the peer dials over TCP (`host.docker.internal:9999`).
4. **`DOCKER_SOCK` must still be a syntactically valid string.** Even in CCaaS mode, the peer/orderer compose files reference `${DOCKER_SOCK}:/host/var/run/docker.sock` — an *unset* `DOCKER_SOCK` produces `docker compose config` error `invalid spec: :/host/var/run/docker.sock: empty section between colons` (confirmed directly while building the P10.2 bring-up script). It only needs to be a valid path string, not a working socket, since CCaaS never uses it.

---

# Bring-Up Procedure

```bash
./blockchain/fabric-network/bring-up.sh
```

This single, idempotent script (`blockchain/fabric-network/bring-up.sh`) reproduces the exact P9.2/P9.6/P9.7 sequence:

1. Verify Docker + `docker compose` are available.
2. Verify the Fabric binaries (`peer`, `orderer`, `configtxgen`, `fabric-ca-client`, `osnadmin`) and the built chaincode (`dist/index.js`) exist — never downloads or builds anything itself.
3. Apply the Windows/Git-Bash `MSYS_NO_PATHCONV` fix (no-op on non-Windows shells).
4. Verify working directories; set `DOCKER_SOCK`.
5. Bring up `ca_org1`/`ca_org2`/`ca_orderer` and enroll Org1/Org2/Orderer identities via `fabric-samples`' own `organizations/fabric-ca/registerEnroll.sh` — **skipped entirely if `organizations/peerOrganizations` already exists**, since `network.sh`'s own `createOrgs()` would otherwise delete it unconditionally.
6. Generate the channel genesis block via `configtxgen` — skipped if `channel-artifacts/ecotrace-channel.block` already exists.
7. Start `orderer.example.com`, then `peer0.org1.example.com`, then `peer0.org2.example.com`, **one at a time**, each preceded by a TCP-readiness wait — reusing an existing stopped container (`docker start`) rather than recreating it, and leaving an already-running one alone.
8. Create/join `ecotrace-channel` and set anchor peers — **skipped entirely if `peer0.org1` already lists the channel as joined**.
9. Install, approve, and commit the **existing, already-verified** `ecotrace-lifecycle` CCaaS package (`blockchain/fabric-network/bootstrap/ccaas-package/ecotrace-lifecycle-ccaas.tar.gz`) — never rebuilt; skipped entirely if the chaincode definition is already committed.
10. Start the CCaaS server process (`fabric-chaincode-node server`, against the existing `dist/`, no recompilation) if port 9999 isn't already listening.
11. Print the exact Fabric connection details and the environment variables needed to activate Fabric on `device-ai`.
12. **Only if `--with-device-ai` is passed**: apply the existing `blockchain/fabric-network/bootstrap/docker-compose.p96-fabric-override.yml` override to the running `device-ai` container and verify `GET /system/blockchain/health` reports `connected` — never fabricated, and never done by default (the script otherwise never touches `ecotrace-backend`, `ecotrace-device-ai`, `ecotrace-frontend`, or `ecotrace-postgres`).

```bash
./blockchain/fabric-network/bring-up.sh --with-device-ai
```

This script deliberately never runs `network.sh down`, `docker system prune`, `docker volume prune`, or `rm -rf organizations` — every stage detects existing state and reuses it rather than recreating it.

---

# Shutdown

**Non-destructive** (stops containers, keeps all crypto material/ledger state/volumes for a fast restart via `bring-up.sh` next time):

```bash
docker stop peer0.org1.example.com peer0.org2.example.com orderer.example.com ca_org1 ca_org2 ca_orderer
kill "$(cat blockchain/fabric-network/bootstrap/ccaas_server_current.pid)"   # stops the CCaaS server process
```

**Destructive** (wipes the network, its ledger, and all generated crypto material — only do this deliberately, never as a routine step):

```bash
cd blockchain/fabric-network/bootstrap/fabric-samples/test-network
./network.sh down
```

Restoring `device-ai` to the default (memory) provider after a Fabric demo session:

```bash
docker compose -f docker-compose.yml up -d device-ai
```

---

# Health Verification

Never conclude Fabric is "working" merely because containers are running. The real verification chain, in order:

1. `docker ps` — peer/orderer/CA containers are `Up`.
2. `peer channel list` (against `peer0.org1`) — includes `ecotrace-channel`.
3. `peer lifecycle chaincode querycommitted --channelID ecotrace-channel --name ecotrace-lifecycle` — succeeds.
4. The CCaaS server is listening on `localhost:9999`.
5. **`GET http://localhost:8100/system/blockchain/health` (only after activating the Fabric override on `device-ai`) reports `"status": "connected"`.** This is the one check that proves the real `FabricGatewayClient` can reach the real peer — everything before it is necessary but not sufficient.

`bring-up.sh --with-device-ai` performs all five automatically and prints the raw response rather than a summarized "success".

---

# Troubleshooting (Windows / Docker Desktop)

| Symptom | Cause | Fix |
|---|---|---|
| `mkdir C:\Program Files\Git\var: Access is denied` | Starting orderer + both peers in one batched `docker compose up -d` | Already handled by `bring-up.sh` (sequential starts); if seen outside the script, never call `network.sh up` directly on Windows |
| `Failed to read '...ca-cert.pem'` with a doubled/mangled path (e.g. `D:\d\Documents\...`) | `MSYS_NO_PATHCONV=1` set in the shell | `unset MSYS_NO_PATHCONV` before running any Fabric tooling (handled automatically by `bring-up.sh` on Git-Bash) |
| `invalid spec: :/host/var/run/docker.sock: empty section between colons` from `docker compose` | `DOCKER_SOCK` env var unset | Handled automatically by `bring-up.sh`; if invoking `docker compose` manually, `export DOCKER_SOCK="${DOCKER_HOST:-/var/run/docker.sock}"` first |
| `connection error ... connectex: No connection could be made` on `peer channel join` | Peer/orderer not actually ready yet | `bring-up.sh` waits for TCP readiness before proceeding; if running steps manually, wait longer between starting a container and using it |
| `contractClass is not a constructor` from `fabric-shim` | Chaincode's `main` module doesn't export a `contracts` array | Already fixed — `blockchain/chaincode/ecotrace-lifecycle/src/index.ts` provides this; do not remove it |
| `Error: Device <id> not found` on `AnchorDevicePassport` | The device was never registered on-chain first | Already fixed (P9.7) — `FabricExternalTrustLedger.anchor()` auto-registers; if seen, confirm you're running the current, unmodified `external_trust.py` |
| `GET /system/blockchain/health` reports `"disabled"` after applying the override | The override wasn't actually applied, or was applied to the wrong compose project | Re-run `docker compose -f docker-compose.yml -f blockchain/fabric-network/bootstrap/docker-compose.p96-fabric-override.yml up -d device-ai` and re-check |

---

# Generated Files

Everything under `blockchain/fabric-network/bootstrap/` is generated/vendored working state, **not source**:

- `fabric-samples/` — vendored clone of `hyperledger/fabric-samples` (~350MB with binaries/images cached).
- `fabric-samples/test-network/organizations/` — real CA-issued X.509 certificates and EC private keys for every peer/orderer/admin identity. **Regenerated fresh on a clean bring-up; never reused across machines.**
- `fabric-samples/test-network/channel-artifacts/` — the channel genesis block and related config transactions.
- `ccaas-package/`, `chaincode-package/` — the packaged chaincode artifact(s) installed on the peers.
- `*.log`, `*.pid` — bring-up/teardown session logs and the CCaaS server's process id.
- `docker-compose.p96-fabric-override.yml` — the reusable, already-proven override that points `device-ai` at the live network.

None of this is committed (see below), and `bring-up.sh` treats all of it as reusable state to detect and skip past, not as disposable scratch.

---

# Security Precautions

- **Never commit generated crypto material.** `.gitignore` line `blockchain/fabric-network/bootstrap/` excludes the entire directory — verified via `git log --all` / `git ls-files` that **zero files under this path have ever been tracked**, not just that a rule exists going forward.
- **No insecure fallback.** `FabricGatewayClient` refuses to connect without a configured `FABRIC_TLS_CERT_PATH` — there is no plaintext-channel code path.
- **No private key logging.** The gateway client logs file paths and connect/parse success or failure only, never certificate or key contents. `bring-up.sh` follows the same rule — it prints the *paths* to identity material, never the key bytes, and never `cat`s a keystore file.
- **`.env.example` ships only empty placeholders** for `FABRIC_TLS_CERT_PATH` / `FABRIC_IDENTITY_CERT_PATH` / `FABRIC_IDENTITY_KEY_PATH` — no real path or secret is ever tracked.
- If a future session hands Fabric bring-up to someone unfamiliar with this layout: the one rule that matters is **never `git add` anything under `blockchain/fabric-network/bootstrap/`**, even by accident via `git add -A`.

---

# Identity & Security (Production Direction)

The current local network uses one admin identity per org (`Admin@org1.example.com`, etc.) for both API-level chaincode invocation and CLI verification — appropriate for a local pilot, not a production deployment.

- Production direction: a dedicated, narrowly-scoped application identity per environment for `device_ai`'s own `FabricGatewayClient`, separate from the human admin identities used for operational CLI commands.
- Chaincode endorsement policy: currently the channel/chaincode-definition default (majority of the two orgs); explicit per-organization endorsement policies are a future multi-org topology concern (`12_ROADMAP.md`).
- TLS is enabled on all Fabric communications in every mode this project has ever run — there is no insecure-channel configuration.

---

# Failure Handling

| Failure | Behavior |
|---|---|
| Fabric disabled/unreachable at anchor time | `ExternalLedgerUnavailableError` → `UNAVAILABLE` status returned honestly; the local trust anchor (already established) is unaffected |
| Fabric peer unreachable mid-session | `FabricUnavailable` (a classified `ExternalLedgerError`) propagates distinctly from "device never anchored" (`NOT_ANCHORED`) — the two are never conflated |
| Transaction rejected by the chaincode (validation) | The real chaincode error string surfaces (e.g. `"Device X not found"`, `"already exists on-chain"`) — never swallowed into a generic failure |
| Fingerprint mismatch on external verification | `MISMATCH` status, both the stored and current fingerprints included in the response |

---

# Directory Layout

Real, as of P10.2:

```
blockchain/
├── chaincode/ecotrace-lifecycle/    # real, tested (47/47) — src/ + test/, compiled to dist/
├── fabric-protos/                   # real: vendored, unmodified upstream Fabric Gateway
│                                    # .proto definitions the Python gRPC client is built against
├── fabric-network/
│   ├── bring-up.sh                  # THE reproducible, idempotent bring-up script (P10.2)
│   └── bootstrap/                   # gitignored working directory — generated/vendored, not source
│       ├── fabric-samples/          # vendored hyperledger/fabric-samples clone + binaries
│       ├── ccaas-package/           # the existing, reusable CCaaS chaincode package
│       ├── docker-compose.p96-fabric-override.yml  # reusable device-ai Fabric activation
│       └── *.sh, *.log              # verification helper scripts and session logs
└── docs/                            # (this directory's own README, if any)
```

---

# Testing Expectations

Defined fully in `10_TESTING.md`. Blockchain-specific minimums:

- Chaincode unit tests with a mocked stub: happy paths, ordering violations, duplicates (47/47, `blockchain/chaincode/ecotrace-lifecycle/test/`).
- `FabricGatewayClient` unit tests against a fake Gateway server for wire-protocol correctness (`intelligence/device_ai/tests/test_p62_fabric_gateway.py`).
- Live-network verification (P9.2/P9.6/P9.7 reports) is the authoritative evidence that the real integration works end-to-end; it is reproduced on demand via `bring-up.sh`, not kept running permanently.
- Backend Fabric-adjacent tests cover only the read-only health proxy's degrade path (`proxy_unreachable`) — the backend never holds a Fabric identity to test against a real network.
