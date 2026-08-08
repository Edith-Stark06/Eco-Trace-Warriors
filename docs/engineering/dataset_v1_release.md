# Dataset v1.0 — Release Report

**Sprint:** P4.2.3 — Dataset v1.0 Freeze & Release
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.2 / M1.4)
**Report date (UTC):** 2026-08-08
**Verdict:** **Dataset v1.0 is NOT RELEASED.**

---

## Current status

Dataset v1.0 is **NOT RELEASED**. The automated freeze gate
(`scripts/audit_dataset_readiness.py`) reports an overall state of **`BLOCKED`**
(exit code 1) when run against the repository, because there is **no real
production dataset** to release: `intelligence/device_ai/datasets/raw` and
`intelligence/device_ai/datasets/labels` contain only `.gitkeep` placeholders,
and no `data.yaml` exists.

The release **tooling** is complete and verified. What is missing is **real,
validated data** — not code. The moment real images and YOLO labels are present
and pass every gate, the same tool mints `v1.0` with no further engineering.

Milestone outcome: **release tooling complete / Dataset v1.0 blocked pending real
data.**

---

## Verified facts

These are asserted by executed tooling, not by hand:

1. **Taxonomy is correct and frozen.** `load_taxonomy()` returns version
   `1.0.0`, exactly **19 classes** with contiguous ids **0–18**, no unknown or
   missing classes. The taxonomy gate reports `pass` even while overall status is
   `BLOCKED`. Single source of truth: `components/data/components.yaml`.
2. **No real dataset content exists.** Every image/label directory under
   `intelligence/device_ai/datasets/` is empty except for `.gitkeep`. No
   `data.yaml`, no split files, no release manifest.
3. **The audit reaches `BLOCKED` correctly.** With the taxonomy gate `pass` and
   the data-presence gate `block`, content gates (image validation, annotation
   validation, coverage, duplicates, split) are short-circuited — there is
   nothing to validate — and the overall state is `BLOCKED`.
4. **The release builder refuses to fabricate.** Because the report is not
   `READY`, `main()` does **not** call the manifest builder; it records
   `release = {"written": false, "reason": ...}`. No manifest, no metrics, no
   counts are invented.
5. **The tooling works — proven on synthetic fixtures only.** Temporary,
   throwaway fixtures (created outside the repo, then deleted) exercised all
   states end-to-end:
   - `READY` → manifest written, exit 0.
   - `INVALID` → orphan label; exact-duplicate image; out-of-range class id
     (three independent cases), manifest refused, exit 1.
   - `INCOMPLETE` → a class missing, manifest refused, exit 1.
   - `BLOCKED` → empty inputs, manifest refused, exit 1.
6. **Output is deterministic.** Identical inputs + `--version` + `--created-at`
   produce byte-identical manifests (compared via canonical `json.dumps`,
   `sort_keys=True`). Timestamps are injected, never read from the wall clock;
   the content hash derives from image bytes only.
7. **The frozen pipeline is untouched.** The audit only *composes* the P4.1.2
   pipeline and P4.2.1/P4.2.2 scripts. No dataset module, API, interface, schema,
   or threshold was modified. New Python passes ruff and mypy.

---

## Blockers

| # | Blocker | Gate | Owner | Resolves state |
| --- | --- | --- | --- | --- |
| B1 | No real images collected (`datasets/raw` empty) | Data presence → `block` | Data collection | `BLOCKED` → onward |
| B2 | No YOLO labels (`datasets/labels` empty) | Annotation validation / coverage | Annotation | needed for `READY` |
| B3 | No `data.yaml` / split artefacts | Split | Dataset eng. | needed for `READY` |
| B4 | Manual sign-off items (licence/privacy, second review, negatives ratio) unrecorded | Manual (checklist §§2–7) | QA + dataset lead | approval prerequisite |

**B1 is the root blocker.** B2–B4 cannot even be evaluated until real images
exist. No blocker is a tooling or code defect.

---

## Release criteria

Dataset v1.0 is released only when **all** of the following hold (see
`dataset_v1_freeze_policy.md`):

1. `audit_dataset_readiness.py` → overall **`READY`**, exit 0, with:
   - taxonomy `1.0.0`, 19 classes, ids 0–18;
   - ≥ 1 real image present;
   - image validation clean (Gate A);
   - annotation validation clean (frozen + P4.2.2 layered checks);
   - coverage: all 19 classes present, `annotation_completeness == 1.0`, no gaps;
   - no exact/near duplicates (Hamming `≤ 5`);
   - deterministic 70/20/10 split (seed 42), no cross-split leakage, every class
     present in train/val/test.
2. Content-addressed manifest built by `build_dataset_release.build_manifest`,
   with a recorded aggregate `content_hash`.
3. Manual sign-off recorded (QA lead + dataset lead) per the readiness checklist
   and DoD.
4. Changelog row appended in `dataset_v1_freeze_policy.md` §7.

All thresholds are code-owned in
`intelligence/device_ai/configs/settings.py`; this report does not redefine them.

---

## Next actions

1. **Collect real images** per the acquisition runbook until per-class coverage
   targets are met (unblocks B1).
2. **Annotate** to YOLO format; run `scripts/validate_annotations.py` until
   clean (unblocks B2).
3. **Generate `data.yaml` / splits** via the frozen splitter (unblocks B3).
4. **Run the audit:**
   ```
   python scripts/audit_dataset_readiness.py \
     --images-root intelligence/device_ai/datasets/raw \
     --labels-root intelligence/device_ai/datasets/labels \
     --json-out build/readiness.json --md-out build/readiness.md
   ```
   Iterate until overall `READY`.
5. **Record manual sign-off** (B4): licence/privacy clearance, second-review
   agreement, negatives ratio, source blend.
6. **Mint `v1.0`:** re-run the audit with `--release-out build/dataset_v1.0.json`;
   the manifest is written only on `READY`. Record its `content_hash` and append
   the changelog row.
7. **Only then** advance to P4.3 (training). **STOP** here until real data exists
   (P4.2.3 stop condition).

---

## Related documents

| Document | Role |
| --- | --- |
| `docs/ai/dataset_v1_freeze_policy.md` | Freeze governance: gates, approval, versioning, rollback |
| `docs/ai/dataset_readiness_checklist.md` | Operational release gate (P4.1.5) |
| `docs/ai/dataset_v1_definition_of_done.md` | Completion contract (P4.1.6) |
| `docs/engineering/annotation_toolkit.md` | Annotation scripts the audit composes (P4.2.2) |
| `scripts/audit_dataset_readiness.py` | The automated freeze gate (PART 1–6) |
