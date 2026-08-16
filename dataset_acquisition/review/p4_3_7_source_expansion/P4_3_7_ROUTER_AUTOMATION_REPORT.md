# P4.3.7 — Router Automation Report

**Sprint:** P4.3.7 — automated single-class acquisition (router, taxonomy id 11)
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (M1.4)
**Run started:** 2026-08-16T06:49:16.483333+00:00
**Wave id:** `p4_3_7_expansion_v1`
**Overall status:** **BLOCKED_NO_SOURCE**

> **Honesty contract.** Every number below is measured by a frozen component or is reported as `NOT RUN` / `BLOCKED` / `UNVERIFIED`. No image, count, license, provenance value or QA verdict is inferred, and no dataset was released or committed by this run.

---

## 1. Execution mode

- Mode requested: `offline`
- Mode effective: `offline`
- Dry run: `False`

## 2. Network status

- Status: **SKIPPED_OFFLINE**
- Probe attempted: `False`
- Target: `-`
- Detail: offline mode requested; no network probe attempted
- Retry policy: a single probe, never retried.

## 3. Credentials status (names only, no secrets)

| Adapter | Required | Present | Missing | Satisfied |
| --- | --- | --- | --- | --- |
| huggingface | - | - | - | True |
| kaggle | KAGGLE_KEY, KAGGLE_USERNAME | - | KAGGLE_KEY, KAGGLE_USERNAME | False |
| roboflow | ROBOFLOW_API_KEY | - | ROBOFLOW_API_KEY | False |

No credential *value* is read out, logged or written anywhere by this pipeline; only the presence of a variable name is recorded.

## 4. Sources discovered / verified / rejected

- Discovered: 0
- Verified (accepted): NOT RUN
- Rejected: NOT RUN
- Unverified: NOT RUN

### Adapter availability

| Adapter | Available | Candidates | Reason |
| --- | --- | --- | --- |
| huggingface | False | 0 | huggingface unavailable: missing network; fail closed (no guessing, no fabrication) |
| kaggle | False | 0 | kaggle unavailable: missing network, KAGGLE_USERNAME, KAGGLE_KEY; fail closed (no guessing, no fabrication) |
| roboflow | False | 0 | roboflow unavailable: missing network, ROBOFLOW_API_KEY; fail closed (no guessing, no fabrication) |

## 5. License decisions

Licenses are **never inferred**: an absent or unrecognised license is `UNVERIFIED`, and a non-commercial / no-derivatives / proprietary license is `REJECTED`.

| Source | Verdict | Raw license | Normalised | Reason |
| --- | --- | --- | --- | --- |
| - | NOT RUN | - | - | no source verified |

## 6. Semantic decisions

A source label clears the gate only when it **explicitly** denotes `router`. Ambiguous labels (`modem/router`, `gateway`, `switch`, `access point`, `set-top box`, `networking device`, generic electronics) are rejected, and classification-only labels are never promoted to bbox labels.

| Source | Verdict | Accepted labels | Rejected labels |
| --- | --- | --- | --- |
| - | NOT RUN | - | - |

## 7. Images discovered / retained / rejected

- Source images discovered: NOT RUN
- Images retained (staged): NOT RUN
- Images rejected: NOT RUN
- Boxes discovered: NOT RUN
- Boxes dropped by the per-box semantic gate: NOT RUN
- Boxes dropped by geometry validation: NOT RUN
- Boxes staged: NOT RUN

### Rejection reasons

- NOT RUN (no ingestion performed)

## 8. Provenance completeness

- Records: NOT RUN
- Complete: NOT RUN
- Incomplete: NOT RUN
- Manifest written: NOT RUN
- Manifest path: `-`

Mandatory per-image fields: SHA-256, original filename, source dataset, source identifier, source class, taxonomy class + id, license evidence, import timestamp.

## 9. Annotation counts and validation

- Validation status: **NOT RUN**
- Frozen Gate A (ImageValidator) valid: NOT RUN
- Frozen Gate B (AnnotationValidator) valid: NOT RUN
- Total boxes in staged labels: NOT RUN
- Class histogram: NOT RUN
- Gate B detail: NOT RUN

## 10. Duplicate results (frozen detector, unmodified)

- Status: **NOT RUN**
- Hamming threshold: NOT RUN (read from settings; never changed by this pipeline)
- Protected images scanned (read-only): NOT RUN
- New images scanned: NOT RUN
- New images flagged as duplicates: NOT RUN
- Ordering: -
- Detail: -

## 11. Automated QA results

- Status: **NOT RUN**
- AUTO_ACCEPT: NOT RUN
- AUTO_REJECT: NOT RUN
- UNVERIFIED: NOT RUN
- Visual verification: **NOT RUN**
- Human QA: **NOT RUN**
- Basis: -

Uncertainty is never converted to acceptance: an image automation cannot adjudicate is held `UNVERIFIED` and is **excluded** from the accepted set that is split and audited.

## 12. Train / validation / test split

- Status: **NOT RUN**
- Splitter: -
- Ratios: NOT RUN (frozen)
- Seed: NOT RUN (frozen)
- Counts: NOT RUN
- Deterministic: NOT RUN
- Disjoint: NOT RUN
- Complete: NOT RUN

### Split gate — target class presence

- Present per split: NOT RUN
- Target-class boxes per split: NOT RUN
- Minimum per class: -
- Detail: -

## 13. Coverage and readiness

- Scope: **ROUTER_WAVE_VALIDATION**
- Explicitly *not*: -
- Readiness stage status: **NOT RUN**
- Audit overall: **NOT RUN**
- Gate states: NOT RUN



## 14. Exact blockers

- no local source supplied (--source); offline acquisition needs a local dataset directory or archive
- network: SKIPPED_OFFLINE - offline mode requested; no network probe attempted
- huggingface: huggingface unavailable: missing network; fail closed (no guessing, no fabrication)
- kaggle: kaggle unavailable: missing network, KAGGLE_USERNAME, KAGGLE_KEY; fail closed (no guessing, no fabrication)
- roboflow: roboflow unavailable: missing network, ROBOFLOW_API_KEY; fail closed (no guessing, no fabrication)

## 15. Protected-state verification (measured)

P4.3.5 (`candidate/p4_3_5_dataset_v1_candidate`) and P4.3.6 (`staging/p4_3_6_expansion_v1`) are opened **read-only** and fingerprinted before and after the run.

- All protected trees unchanged: **True**

| Tree | Exists | Files | Images | Labels | Hash before | Hash after | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| p4_3_5_candidate | True | 505 | 252 | 252 | 567cdd455fcd | 567cdd455fcd | UNCHANGED |
| p4_3_6_expansion | True | 736 | 359 | 359 | e12ab28e63d2 | e12ab28e63d2 | UNCHANGED |

## 16. Frozen configuration actually observed

| Value | Observed |
| --- | --- |
| taxonomy version | 1.0.0 |
| taxonomy classes | 19 |
| `router` class id | 11 |
| split ratios | [0.7, 0.2, 0.1] |
| split seed | 42 |
| duplicate Hamming threshold | 5 |

None of these were written by this pipeline; they are read from the frozen taxonomy and settings and asserted before any data is touched.

## 17. Stage ledger

| # | Stage | Status | Summary |
| --- | --- | --- | --- |
| 1 | preflight | OK | frozen taxonomy, split ratios/seed, duplicate threshold and every frozen component verified |
| 2 | network | SKIPPED | network status: SKIPPED_OFFLINE (single probe, never retried) |
| 3 | credentials | OK | credential presence recorded by name only (no secret is ever read out) |
| 4 | discover | BLOCKED | 0 candidate source(s) discovered across 3 adapter(s) |
| 5 | protected_state | OK | protected P4.3.5 / P4.3.6 trees byte-identical before and after |

## 18. Git status

```
?? dataset_acquisition/review/p4_3_4_multiclass_qa_v1/automated_acceptance_log.json
?? dataset_acquisition/review/p4_3_4_multiclass_qa_v1/human_review_log.jsonl
?? dataset_acquisition/review/p4_3_4_multiclass_qa_v1/signoff_template.backup_20260811_225544.json
?? dataset_acquisition/review/p4_3_4_multiclass_qa_v1/signoff_template.before_auto_accept.json
?? dataset_acquisition/review/p4_3_6_expansion_qa_v1/P4_3_6_COUNT_RECONCILIATION.md
?? dataset_acquisition/review/p4_3_7_source_expansion/
?? dataset_acquisition/review/tmp_duplicate_review_p435/
?? intelligence/device_ai/acquisition/
?? intelligence/device_ai/tests/test_acquisition_p437.py
?? scripts/_build_p435_labels.py
?? scripts/acquire_router_p437.py
?? scripts/auto_accept_multiclass_qa_p434.py
?? scripts/review_multiclass_qa_p434.py
?? tmp_run_router_p437_offline.py
?? tmp_settings.py
?? tmp_splitter.py
```

- Committed: **no** (this pipeline never commits)
- Released: **no** (this pipeline never releases)
- P4.3.5 modified: **no** (measured by content-hash comparison)
- P4.3.6 modified: **no** (measured by content-hash comparison)
- Taxonomy / split ratios / split seed / duplicate threshold observed to match the frozen contract: **yes** (asserted by preflight; never written by this pipeline)
