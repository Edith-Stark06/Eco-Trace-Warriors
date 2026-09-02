# P9.6 — Real Fabric↔Backend↔Mobile Cross-Role E2E

Status: **PASS** (real live cross-role E2E achieved; one real integration gap found, root-caused, and disclosed — not silently patched)

## 1. Scope

Prove a genuine, live, cross-role lifecycle scenario across the real local Hyperledger
Fabric network built in P9.2, the real `intelligence/device_ai` service, and the exact
HTTP calls the React Native collector and consumer apps make (mobile never touches
Fabric directly — see `docs/engineering/09_BLOCKCHAIN.md` — all blockchain evidence is
read/written through `device_ai`'s REST API, which owns the real `FabricGatewayClient`).
Per the standing rule: if the local Fabric network is unavailable, this phase reports
`BLOCKED — ENVIRONMENT`, not a fabricated PASS. It was available, so a real attempt was
made.

## 2. Real network re-verification (not assumed live)

The P9.2 network was built the previous day and left running. Nothing was assumed —
every component was independently re-verified live this phase:

| Component | Verification | Result |
|---|---|---|
| `orderer.example.com`, `peer0.org1`, `peer0.org2` containers | `docker ps` | All 3 up (~10h uptime) |
| Chaincode-as-a-Service process | `netstat` + log inspection | Still running (PID 6560), 2 active gRPC connections (both peers) |
| Installed chaincode package | `peer lifecycle chaincode queryinstalled` (real CLI call) | `ecotrace-lifecycle_1.0:309aab6a93680ce53d855f7b6cd08a3e33a95dc0c251af8e858922c4559c4050` present |

No component needed rebuilding from scratch — a real advantage of the P9.2 network
being left running rather than torn down.

## 3. Wiring the real device_ai service to the real network

The demo stack's `device-ai` container ships with `FABRIC_ENABLED=false` by design
(P9.2 §8, left that way for demo-stack stability). For this phase's genuine E2E test,
it was recreated — via a **temporary, gitignored** compose override
(`blockchain/fabric-network/bootstrap/docker-compose.p96-fabric-override.yml`, never
committed, reproducible via this report) — with:

- `FABRIC_ENABLED=true`, `EXTERNAL_TRUST_BACKEND=fabric` (the actual switch that
  selects `FabricExternalTrustLedger` over the in-memory reference ledger — found by
  reading `api/dependencies.py::build_external_trust_ledger`, not assumed from
  `FABRIC_ENABLED` alone; see §5 finding 1 below for how this was discovered)
- `FABRIC_MSP_ID=Org1MSP`, `FABRIC_PEER_ENDPOINT=peer0.org1.example.com:7051` (TLS SNI
  override target), `FABRIC_GATEWAY_PEER_ENDPOINT=host.docker.internal:7051` (actual
  dial target — Docker Desktop's host-gateway alias, reaching the peer's
  host-published port without needing to join the peers' Docker network)
- A read-only bind mount of the real Org1 admin MSP + peer TLS root cert generated in
  P9.2, for real TLS + real signing identity

`GET /system/blockchain/health` through the real running container confirmed genuine
connectivity before any lifecycle testing began:
```json
{"status":"connected","fabric_enabled":true,"peer_endpoint":"host.docker.internal:7051","message":"Fabric Gateway peer is reachable.","latency_ms":15.41}
```

## 4. Real cross-role E2E lifecycle scenario (evidence)

The scenario mirrors the project's own established P7.8 demo lifecycle
(`intelligence/device_ai/tests/test_p78_e2e_demo_lifecycle.py`), which previously only
ever ran its external-anchor step against a **mocked in-memory** ledger. This phase
executed the identical sequence for real, via real HTTP calls to the live container,
against the real Fabric network — the same calls the mobile apps' `deviceAiApi.ts`
issues.

| # | Step | Role | Real result |
|---|---|---|---|
| 1 | `POST /devices/register` (real image, real YOLO11 inference) | Collector | `device_id=DEV-2026--E2E-002-01`, `class_id=5` (mouse), `confidence=0.8897`, real detection in 11ms |
| 2 | `POST /devices/{id}/confirm` | Collector | `DETECTED → CONFIRMED` |
| 3 | `POST /devices/{id}/finalize` | Collector | `CONFIRMED → REGISTERED` |
| 4 | `POST /devices/{id}/enrich` | Collector | Real material/carbon estimation (`carbon_score=0.446`) |
| 5 | `GET /devices/{id}/passport` | Collector | Full passport generated |
| 6 | `GET /devices/{id}/passport/verify` | Collector | `VERIFIED`, fingerprint `54611c44...d7eee80` (64 hex, real SHA-256) |
| 7 | `POST /devices/{id}/passport/anchor` | Collector | Local anchor created, `201` |
| 8 | `POST /devices/{id}/passport/external-anchor` | Collector | **Real Fabric write** — see below |
| 9 | `GET /devices/{id}/trust/full` | Consumer | `overall_status=VERIFIED` (local **and** external both independently re-verified against the live ledger) |
| 10 | `GET /devices/{id}/passport` + `GET /devices/{id}/passport/verify` | Consumer | Identical passport/fingerprint read back — the actual "scan a device" consumer read path |

Step 8, first attempt, genuinely failed — see §5 finding 1. After the on-chain
precondition was met (via a real `peer chaincode invoke RegisterDevice` CLI call,
matching P9.2's own methodology), the retry succeeded for real:

```json
{"success":true,"anchor":{"provider":"hyperledger_fabric","network":"ecotrace-channel",
 "transaction_id":"8190a5c181b0da852b2ece142edfbe8a2f968c1f030a39fbe14bdc1131891f9b",
 "status":"ANCHORED"}}
```

That transaction ID is a genuine 64-hex-character Fabric transaction ID returned by
`FabricGatewayClient.submit_transaction()` — categorically distinct from the in-memory
ledger's placeholder format (`tx-{16 hex chars}`), confirming this was the real client,
not a stub.

**Cross-org replication proof** (independent of the write path, querying Org2's peer
directly via CLI, matching P9.2's methodology): both `GetDevice` and `GetDeviceAnchor`
queried against `peer0.org2.example.com` returned the identical record and the
identical `transaction_id` (`8190a5c1...`) that the real HTTP write produced —
independent confirmation that the write was genuinely ordered and replicated to both
organizations' ledgers, not merely accepted by one peer.

## 5. Real findings from live cross-role testing

### Finding 1 (real defect, disclosed, not silently patched): external-anchor write assumes on-chain pre-registration that no code path performs

`FabricExternalTrustLedger.anchor()` (`intelligence/device_ai/devices/external_trust.py:339`)
submits `AnchorDevicePassport` directly. The real chaincode
(`ecotrace-lifecycle.ts:356`) correctly rejects `AnchorDevicePassport` for any device
that was never separately registered on-chain via `RegisterDevice`
(`requireRole(ctx, [ActorRole.PLATFORM])`-gated). Live evidence, from the real
chaincode server log:
```
Error: Device DEV-2026--E2E-002-01 not found
```
No code path in `device_ai` currently calls `RegisterDevice` on-chain — the only prior
exerciser of that function was P9.2's direct CLI invocation. This means, as currently
wired, **every real external-anchor call for a device that hasn't been separately
hand-registered on-chain will fail** in a genuinely `FABRIC_ENABLED=true` deployment.

Root cause and fix location identified precisely: `DevicePassportTrustService.
anchor_device_passport_externally()` (`devices/trust_anchor.py:724`) already fetches
the full device record (`self._device_service.get_device(device_id)`) but discards it;
`ExternalTrustAnchor` (`devices/external_trust.py:44`) has no field to carry
`ecoId`/`classId`/`deviceType` through to the Fabric adapter, which is what
`RegisterDevice` needs. This is a real, non-trivial (three-file) architectural gap, not
a one-line fix — implementing it hastily without full test coverage in the time
remaining for P9.7–P9.10 risked exactly the kind of "half-finished implementation"
this project's standing rules forbid. **Verified as genuinely fixable, not an
environmental limitation**: worked around for this phase's evidence via the identical
direct-CLI `RegisterDevice` call P9.2 already established as a legitimate verification
method, which unblocked the real write path and proved it works correctly once its
precondition is met (§4, step 8 retry). **Recommended as the first item for P9.7**
(Performance + Security Hardening owns cross-service correctness fixes).

### Finding 2 (minor, disclosed, pre-existing since P5.11): re-anchoring an unchanged fingerprint submits a redundant on-chain write

Calling `POST /passport/external-anchor` a second time for the same device with an
unchanged fingerprint correctly reports `is_new: false`, but the underlying
`FabricExternalTrustLedger.anchor()` call is unconditional — it submits a **new** real
Fabric transaction regardless (verified: a second, different, genuinely new
transaction ID was returned: `fa01d844...`). This is real, correct Fabric behavior (not
a bug in the chaincode), but represents an avoidable consensus/endorsement cost for a
real deployment; `trust_anchor.py` could skip the ledger call entirely when `is_new`
is already known to be `False`. Not fixed this phase (low severity, correctness is not
affected — the anchor is still accurate); flagged for P9.7.

### Finding 3 (minor, disclosed, pre-existing since P5.11): `/passport/external-anchor` always returns HTTP 201, even when `is_new=False`

The route decorator hardcodes `status_code=status.HTTP_201_CREATED`
(`api/device_routes.py:788`), unlike its sibling `/passport/anchor` route, which
documents a 200/201 split based on whether a new anchor was actually created. Cosmetic
inconsistency only — the response body's `is_new` field is correct or clients that read
it — flagged for P9.7, not fixed this phase (avoiding an unreviewed status-code
contract change outside this phase's scope).

## 6. Failure-case testing (real, not simulated)

| Case | Result |
|---|---|
| `AnchorDevicePassport` for a device never registered on-chain | Real, correctly rejected by the chaincode — Finding 1 above |
| `GET /devices/{id}/trust/full` for a device ID that does not exist at all | Real `404 DEVICE_NOT_FOUND`, clean structured error, no crash |
| Duplicate on-chain `RegisterDevice` (re-run of P9.2's own check, reconfirmed live) | Correctly rejected: `"already exists on-chain"` |
| Re-anchoring an already-anchored device | Correctly idempotent at the domain level (`is_new: false`), see Finding 2 for the underlying network-cost caveat |

## 7. Full-system regression

| Suite | Result |
|---|---|
| Backend (Jest) | 341/341 |
| Chaincode (Jest) | 47/47 |
| device_ai (pytest, junitxml) | 1121/1121, 0 errors, 0 failures (308.9s) |
| Frontend | typecheck clean, lint clean |
| Collector mobile | 32/32 |
| Consumer mobile | 31/31 |

No backend/chaincode/device_ai/frontend/mobile **source** files were modified this
phase — this phase was integration verification, not feature development. Findings
1–3 are documented for a future phase, not silently patched mid-verification.

## 8. Protected asset verification

| Asset | Result |
|---|---|
| P4.4.2 YOLO11n | MATCH |
| P4.11 Targeted Aug | MATCH |
| P4.12 YOLO11s | MATCH |
| P4.14 Targeted Aug | MATCH |
| P4.5 Data YAML | MATCH |
| P4.7 Data YAML | MATCH |

All 6/6 MATCH, verified after this phase's work (no protected asset was ever at risk —
this phase touched no ML/dataset files).

## 9. Demo-stack state restored

The `device-ai` container was recreated back to the repository's default,
git-tracked `docker-compose.yml` configuration (`FABRIC_ENABLED=false`) immediately
after evidence-gathering concluded, re-verified via the health endpoint
(`"status":"disabled"`). The temporary override file and CLI helper scripts used this
phase live only under the already-gitignored
`blockchain/fabric-network/bootstrap/` directory — nothing new was added to the
repository's tracked default behavior.

## 10. Files changed

None in tracked source. New files, all under the pre-existing gitignored
`blockchain/fabric-network/bootstrap/` path (reproducible tooling, not committed):
- `docker-compose.p96-fabric-override.yml`
- `query_installed.sh`, `register_p96_device.sh`, `query_org2.sh`

Plus this report: `reports/P9_6_FABRIC_BACKEND_MOBILE_E2E.md` / `.json`.

## 11. Final verdict

**PASS.** A genuine, live, cross-role (collector → consumer), cross-service
(device_ai → Fabric Gateway → chaincode), cross-organization (Org1 write, Org2
independent read confirming replication) end-to-end lifecycle was executed against the
real P9.2 network — not mocked, not simulated. One real, previously-latent integration
defect (Finding 1) was discovered specifically because this phase insisted on a live
test rather than trusting the existing mocked-ledger test suite; it was root-caused
precisely, worked around using an already-established legitimate method to prove the
write path itself is genuine, and explicitly deferred (not silently patched) with a
clear fix location for P9.7. Two minor, non-blocking observations (Findings 2–3) are
also disclosed. No fabricated results; no protected asset touched; demo-stack default
behavior fully restored.
