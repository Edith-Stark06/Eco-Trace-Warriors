# P8.2 — Live Blockchain Environment

## 1. Scope

Move from abstract/mock Fabric validation toward actual Hyperledger Fabric
execution wherever the environment genuinely permits it — first
determining, fresh this phase, whether it does.

---

## 2. Environment determination (this phase, not assumed)

```
$ which peer orderer configtxgen cryptogen
(none found — not in PATH)

$ docker images | grep -i fabric
(no output — no Fabric images pulled/built)

$ find / -iname "fabric-samples"
(not found anywhere on the machine)

$ find <repo> -iname "crypto-config" -o -iname "*.block" -o -iname "configtx.yaml"
(not found anywhere in the repository)
```

**No Hyperledger Fabric peer, orderer, CA binaries, channel artifacts, or
crypto material exist anywhere in this repository or execution
environment.** This is the identical conclusion reached independently in
P6.2, P6.7, P7.1, P7.5, P7.9, and P7.10 — re-verified here by the same
absence checks, not inherited as an assumption.

**LIVE FABRIC = BLOCKED BY ENVIRONMENT.** No live transaction was
submitted to a real Fabric network. None is claimed.

---

## 3. Strongest available validation — MOCK PASS

Ran fresh this phase, not cited from a prior report:

| Suite | Result |
|---|---|
| Chaincode (real Hyperledger Fabric contract code, Jest) | **47/47** (45 baseline + 2 new, §4) |
| Chaincode ESLint / `tsc --noEmit` | 0 errors |
| `test_p62_fabric_gateway.py` (real gRPC client against a TLS fake-server speaking the authentic, vendored Fabric protocol) | **46/46** |
| `test_p79_failure_injection.py` (includes the P7.9 genuine RPC-timeout test) | **5/5** |
| Backend `blockchain.service.test.ts` + `blockchain.test.ts` (integration, including the real unmocked "nothing listening" degradation path) | **12/12** — re-run twice: once collided with this session's own live Docker stack occupying `:8100` (a real environmental artifact, not a code defect — see §6), then re-run clean after stopping it |

---

## 4. Scenario coverage — every one in the P8.2 checklist, with real evidence

| Scenario | Test | Result |
|---|---|---|
| Successful anchor | `AnchorDevicePassport` round-trip (chaincode, pre-existing) | PASS |
| **Duplicate anchor** | **NEW**: `is idempotent when re-anchored with the identical fingerprint` | PASS |
| **Conflicting anchor** | **NEW**: `replaces the anchor on a conflicting re-anchor with a different fingerprint, fully audited` | PASS |
| Invalid device | `rejects anchoring a non-existent device` (chaincode, pre-existing) | PASS |
| Network timeout | `test_evaluate_transaction_times_out_against_a_slow_but_reachable_peer` (P7.9) | PASS |
| Unavailable peer | `test_evaluate_transaction_unavailable_when_peer_down` (P6.2) | PASS |
| Malformed transaction | `rejects an unsupported algorithm and a malformed fingerprint` (chaincode, pre-existing) | PASS |

**Two of these seven scenarios had no explicit test before this phase**
(duplicate anchor, conflicting anchor) — found while reading the actual
`AnchorDevicePassport` chaincode implementation to answer P8.2's question
directly, not assumed from its name.

---

## 5. A real design question, resolved by reading the actual contract

`AnchorDevicePassport` (`blockchain/chaincode/ecotrace-lifecycle/src/
ecotrace-lifecycle.ts`) **always overwrites** the stored anchor with
whatever fingerprint is submitted — it does not reject a second call for
an already-anchored device, regardless of whether the fingerprint matches.
This raised a real question worth resolving explicitly rather than
assuming either "this is a bug" or "this is fine": **is silent
overwrite-on-conflict a trust-integrity gap?**

Resolved by reading the surrounding system, not by inspection of this one
function alone:
- `POST /devices/{id}/passport/reanchor` (Python, P5.11/P6.2) is an
  **intentional, documented** re-anchor endpoint — the product legitimately
  needs to support re-anchoring (e.g. after additional enrichment changes
  the passport).
- Every re-anchor is gated to the `PLATFORM` role only (`requireRole`,
  unchanged) and **fully audited** — a `DEVICE_EXTERNALLY_ANCHORED` event
  is recorded on every call, never silently absorbed (verified by the new
  test's explicit event-count assertion, §4).
- `VerifyPassportFingerprint` against the *old* fingerprint correctly
  reports `MISMATCH` after a conflicting re-anchor — a stale local passport
  cannot silently pass verification against a superseded anchor.

**Conclusion: this is correct, intentional, already-audited behavior, not
a defect.** No chaincode change was made. The two new tests close the
actual gap, which was in test coverage proving this explicitly, not in the
contract's logic.

---

## 6. A real environmental artifact, disclosed

The first run of `backend`'s blockchain integration test suite this phase
failed one assertion (`expected "proxy_unreachable", received "disabled"`)
— not a code defect. This session's own live `docker-compose` stack
(P7.5/P7.8/P8.1) was still running and had a real `device-ai` container
listening on `:8100`, the exact port the test's own comment says "nothing
is listening there." Stopped the stack, re-ran the suite: **12/12 clean**.
Documented here rather than silently re-run without explanation — the
identical class of artifact already disclosed once in P7.10.

---

## 7. Tests — consolidated, fresh this phase

| Suite | Result |
|---|---|
| Chaincode Jest | 47/47 (45 baseline + 2 new) |
| Python `device_ai` full suite | 1110/1110 this run |
| Backend Jest (full suite) | 339/339 |

No regression. **Total automated tests across the system: 1110 + 339 + 47
+ 22 (collector, unchanged) + 13 (consumer, unchanged) = 1531.**

---

## 8. Security considerations

- `AnchorDevicePassport` remains gated to `PLATFORM` role only — re-checked
  this phase, unchanged.
- The new conflicting-anchor test explicitly proves stale-fingerprint
  verification correctly fails closed (`MISMATCH`), not open — directly
  relevant to this session's standing "never silently downgrade a failed
  trust verification into success" principle.
- No private key or wallet material is touched by anything in this phase;
  the Fabric Gateway client's existing no-insecure-fallback behavior
  (P6.2/P6.8/P7.4) was re-exercised via the RPC-timeout test, not
  re-audited from scratch (no new code there this phase).

---

## 9. Protected asset verification

Verified via `sha256sum` before and after this phase's changes — **6/6
MATCH**. No ML asset touched.

---

## 10. Git state

Diff scoped to exactly one file:
`blockchain/chaincode/ecotrace-lifecycle/test/ecotrace-lifecycle.test.ts`
(+2 test cases). Verified via `git status`/`git diff --stat` before
commit.

---

## 11. Environmental limitations

- **No Hyperledger Fabric network** (peer/orderer/CA) exists anywhere in
  this repository or environment — re-confirmed this phase by direct
  evidence (§2), not carried forward as an assumption.
- Everything else in the P8.2 task list that requires a live network
  (real transaction submission, real ledger query, real endorsement
  policy enforcement, real event delivery from an actual peer) is
  correspondingly **BLOCKED BY ENVIRONMENT** — not attempted, not
  fabricated.

---

## 12. Definition of Done

- [x] Environment determination performed fresh this phase, with direct
      evidence, not inherited (§2).
- [x] Live Fabric honestly reported as blocked; never conflated with the
      mocked results.
- [x] The strongest available validation re-run fresh this phase (§3).
- [x] Every scenario in the P8.2 checklist mapped to a real, passing test
      — including two genuinely new ones for gaps found by reading the
      actual chaincode (§4).
- [x] A real architectural question (silent-overwrite re-anchor) resolved
      by reading the surrounding system, not assumed either way (§5).
- [x] A real environmental test artifact disclosed and corrected (§6).
- [x] Protected assets verified before and after.
- [x] No chaincode logic changed; no unrelated files touched.

## 13. Final status: **MOCK PASS. LIVE FABRIC = BLOCKED BY ENVIRONMENT.**
