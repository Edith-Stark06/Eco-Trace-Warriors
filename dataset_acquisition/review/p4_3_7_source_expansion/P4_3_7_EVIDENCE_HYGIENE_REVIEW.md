# P4.3.7 — Evidence & Hygiene Review

**Sprint:** P4.3.7 — Router (ID 11) source expansion · final evidence/hygiene pass
**Date:** 2026-08-16
**Branch:** `feat/p4-3-multiclass-acquisition` · **Protected HEAD:** `b4604f9`
**Scope:** Classify every untracked file; verify frozen/protected invariants; recommend commit disposition.

> **Read-only contract.** This review **modified nothing, deleted nothing, staged nothing, and committed nothing.** No file was touched; classifications are recommendations for a human to action. No further acquisition was attempted. Router acquisition remains **BLOCKED_NO_SOURCE**.

---

## 1. Invariant verification (measured now, read-only)

| Check | Result | Verdict |
|---|---|---|
| `git diff --stat` | *(empty)* | ✅ no tracked file modified |
| `git diff --cached --stat` | *(empty)* | ✅ nothing staged |
| P4.3.5 protected fingerprint | `567cdd455fcd…` — 505 files / 252 img / 252 lbl | ✅ UNCHANGED |
| P4.3.6 protected fingerprint | `e12ab28e63d2…` — 736 files / 359 img / 359 lbl | ✅ UNCHANGED |
| Taxonomy | version **1.0.0**, **19** classes, `router` == id **11** | ✅ frozen |
| Split ratios / seed | **(0.7, 0.2, 0.1)** / **42** | ✅ frozen |
| Duplicate Hamming threshold | **5** | ✅ frozen |
| Router coverage | candidate labels = {monitor, printer, smartphone, tablet}; **no router** | ✅ router uncovered |
| Production router data | router staging tree = **0 files**; no `router` under `candidate/` | ✅ none exists |

Fingerprints recomputed live with the frozen `preflight.fingerprint_tree`; frozen values read live from `load_taxonomy()` and `Settings()`. Both match this session's `run_report.json`.

> **Protected-data note:** `dataset_acquisition/candidate/` (root `.gitignore`) and `dataset_acquisition/staging/` (`dataset_acquisition/.gitignore`) are **already git-ignored** — the protected P4.3.5 candidate and all staging (incl. the empty router wave) cannot be accidentally committed. Every untracked file below lives outside those trees.

---

## 2. Classification of all untracked files (73 total)

**Legend:** `KEEP-tool` = reusable production tooling · `KEEP-evi` = required project evidence · `ARCHIVE` = historical evidence · `DELETE` = temp/debug/generated · ⚠️ = human sign-off before commit/delete.

### 2.1 Production tooling — **KEEP-tool** (commit)

| Artifact | Class | Why retain |
|---|---|---|
| `intelligence/device_ai/acquisition/**` (25 files: pkg + `adapters/`) | KEEP-tool | The frozen, tested acquisition pipeline — the sprint deliverable. Correct package location; imports the frozen taxonomy/settings/dedup/splitter rather than re-implementing them. |
| `intelligence/device_ai/tests/test_acquisition_p437.py` | KEEP-tool | 74 tests covering the package (gates, ingest, dedup, split, QA, CLI, provenance). Required to keep the pipeline honest. |
| `scripts/acquire_router_p437.py` | KEEP-tool | Thin repo-root CLI shim (no domain logic; only the `sys.path` bootstrap) over `device_ai.acquisition.cli`. Matches the flat `scripts/` convention. |
| `scripts/auto_accept_multiclass_qa_p434.py` | KEEP-tool | QA auto-acceptance workflow (reads `signoff_template.json`, applies conservative acceptance, writes a log + pre-mutation backup). Reusable dataset-QA tooling. |
| `scripts/review_multiclass_qa_p434.py` | KEEP-tool | Human-QA review CLI (A/R/X decisions, field validation). Reusable review tooling. |
| `dataset_acquisition/review/p4_3_7_source_expansion/router/README.md` | KEEP-tool | Turnkey self-collection runbook for the SAFE router path. |
| `dataset_acquisition/review/p4_3_7_source_expansion/router/collection_log.template.csv` | KEEP-tool | Provenance template (fields mirror `ProvenanceRecord`) for human router collection. |

### 2.2 Project evidence — **KEEP-evi** (commit)

| Artifact | Class | Why retain |
|---|---|---|
| `…/p4_3_7_source_expansion/P4_3_7_ROUTER_AUTOMATION_REPORT.md` | KEEP-evi | Authoritative current run: automated pipeline → `BLOCKED_NO_SOURCE`, protected trees byte-identical. ⚠️ its §18 git snapshot lists a since-removed temp driver (`tmp_run_router_p437_offline.py`) — cosmetic only. |
| `…/p4_3_7_source_expansion/router_automation/run_report.json` | KEEP-evi | Machine-readable evidence backing the report (stage ledger, fingerprints, frozen values). |
| `…/p4_3_7_source_expansion/P4_3_7_ACQUISITION_PLAN.md` | KEEP-evi | Coverage-first plan for the 9 zero-image classes (plan only; nothing acquired). |
| `…/p4_3_7_source_expansion/P4_3_7_COVERAGE_RESEARCH.md` | KEEP-evi | Research: 9 classes UNMAPPED by design; self-collection = only SAFE path; router first. |
| `…/p4_3_7_source_expansion/P4_3_7_SOURCE_MAPPING_MATRIX.md` | KEEP-evi | Per-source risk matrix; all external sources `VERIFY` (unconfirmed this session). |
| `…/p4_3_7_source_expansion/P4_3_7_SPLIT_GATE_RECOVERY.md` | KEEP-evi | Forensic: `DatasetSplitter` never missing; **no** min-depth gate; "150/class" & "29-gap" unsupported. |
| `dataset_acquisition/review/p4_3_6_expansion_qa_v1/P4_3_6_COUNT_RECONCILIATION.md` | KEEP-evi | Prior audit: authoritative P4.3.6 count = **119/174/6** (359 = 121+119+119 triple-materialised copies). |
| `…/p4_3_7_source_expansion/P4_3_7_EVIDENCE_HYGIENE_REVIEW.md` | KEEP-evi | *This document.* |

### 2.3 Historical evidence — **ARCHIVE** (commit as history, or retain)

| Artifact | Class | Why / caveat |
|---|---|---|
| `…/p4_3_7_source_expansion/P4_3_7_ROUTER_WAVE1_REPORT.md` | ARCHIVE | Earlier (2026-08-15) Wave-1 pipeline-validation report — same honest BLOCKED outcome, self-collection framing. Superseded operationally by the automation report; valid history. |
| `…/p4_3_4_multiclass_qa_v1/automated_acceptance_log.json` | ARCHIVE | Log of the P4.3.4 automated-acceptance run. Audit trail. |
| `…/p4_3_4_multiclass_qa_v1/human_review_log.jsonl` | ARCHIVE | P4.3.4 human-review decision log. Audit trail. |
| `…/p4_3_4_multiclass_qa_v1/signoff_template.before_auto_accept.json` | ARCHIVE | Pre-auto-accept snapshot of the signoff — the only record of that state distinct from the committed canonical. |
| `scripts/_build_p435_labels.py` | ARCHIVE ⚠️ | One-shot guarded builder of the P4.3.5 candidate **labels**. Documents build provenance, but **writes into `dataset_acquisition/candidate/` (protected)** and refuses to re-run once labels exist. Commit **as history only**, never re-run; needs maintainer sign-off. |

### 2.4 Temporary / generated — **DELETE** (do not commit)

| Artifact | Class | Why remove |
|---|---|---|
| `tmp_settings.py` | DELETE | UTF-16 stray **duplicate** of the tracked `intelligence/device_ai/configs/settings.py`, dumped at repo root during frozen-value inspection. Wrong location, redundant. |
| `tmp_splitter.py` | DELETE | UTF-16 stray **duplicate** of the tracked `intelligence/device_ai/dataset/splitter.py`. Redundant. |
| `…/p4_3_4_multiclass_qa_v1/signoff_template.backup_20260811_225544.json` | DELETE | Timestamped safety backup of a file that is **tracked** (canonical committed in `8f6574c`). Git history is the durable trail. |
| `dataset_acquisition/review/tmp_duplicate_review_p435/**` (26 files: 8 img + 8 lbl + 10 QA) | DELETE ⚠️ | `tmp_`-prefixed scratch for the P4.3.5 near-duplicate **manual** review; hash-named working copies. The review conclusion is preserved in P4.3.6 `duplicate_evidence.json` + the reconciliation. Confirm the 8 images are copies of staging/candidate data (not a sole source) before removal. |

### 2.5 REQUIRES REVIEW — do not touch

No untracked file is un-classifiable. Two carry a human sign-off flag (⚠️ above): `scripts/_build_p435_labels.py` (mutates protected candidate data) and `…/tmp_duplicate_review_p435/**` (image blobs — confirm they are copies). Neither should be actioned automatically.

---

## 3. Explicit recommendation

### ✅ Safe to commit later (production code, tests, tooling, evidence)
```
intelligence/device_ai/acquisition/**            (25 files — the pipeline)
intelligence/device_ai/tests/test_acquisition_p437.py
scripts/acquire_router_p437.py
scripts/auto_accept_multiclass_qa_p434.py
scripts/review_multiclass_qa_p434.py
dataset_acquisition/review/p4_3_7_source_expansion/
    P4_3_7_ACQUISITION_PLAN.md
    P4_3_7_COVERAGE_RESEARCH.md
    P4_3_7_SOURCE_MAPPING_MATRIX.md
    P4_3_7_SPLIT_GATE_RECOVERY.md
    P4_3_7_ROUTER_AUTOMATION_REPORT.md
    P4_3_7_ROUTER_WAVE1_REPORT.md          (archive/history)
    P4_3_7_EVIDENCE_HYGIENE_REVIEW.md      (this file)
    router/README.md
    router/collection_log.template.csv
    router_automation/run_report.json
dataset_acquisition/review/p4_3_6_expansion_qa_v1/P4_3_6_COUNT_RECONCILIATION.md
```
Optional (commit only if the team wants the P4.3.4 audit trail in git):
```
dataset_acquisition/review/p4_3_4_multiclass_qa_v1/automated_acceptance_log.json
dataset_acquisition/review/p4_3_4_multiclass_qa_v1/human_review_log.jsonl
dataset_acquisition/review/p4_3_4_multiclass_qa_v1/signoff_template.before_auto_accept.json
```
Commit **as history only, with maintainer sign-off** (writes into protected candidate):
```
scripts/_build_p435_labels.py
```

### 🚫 Must NOT be committed — delete (after the ⚠️ confirmations)
```
tmp_settings.py                                                  (dup of tracked module)
tmp_splitter.py                                                  (dup of tracked module)
dataset_acquisition/review/p4_3_4_multiclass_qa_v1/signoff_template.backup_20260811_225544.json
dataset_acquisition/review/tmp_duplicate_review_p435/**          (confirm copies first)
```

### 🔒 Already ignored — keep ignored (no action)
```
dataset_acquisition/candidate/     (P4.3.5 protected — root .gitignore)
dataset_acquisition/staging/       (P4.3.6 + router wave — dataset_acquisition/.gitignore)
```

### Suggested `.gitignore` hardening (optional, prevents recurrence)
- Root: `/tmp_*.py`
- `dataset_acquisition/`: `review/tmp_*/` and `review/**/*.backup_*.json`

---

## 4. Bottom line

- **Nothing was modified, deleted, staged, or committed by this review.**
- Both protected trees are byte-identical to record; taxonomy, split (0.7/0.2/0.1, seed 42) and duplicate threshold (5) are frozen and unchanged.
- **Router (ID 11) remains uncovered and no production router data exists.**
- Commit the acquisition package, its tests, the CLI shim, the QA tools, and the P4.3.6/P4.3.7 evidence docs. Delete the two root `tmp_*.py` duplicates, the timestamped signoff backup, and the `tmp_duplicate_review_p435/` scratch. Treat `_build_p435_labels.py` as sign-off-gated history.
