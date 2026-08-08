# Dataset v1.0 Freeze Policy

**Sprint:** P4.2.3 — Dataset v1.0 Freeze & Release
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.2 / M1.4)
**Status:** Active
**Audience:** dataset engineers, QA leads, release approvers
**Scope:** The governance contract for **freezing and releasing** Dataset v1.0.
It defines the readiness gates, the approval and versioning rules, what
immutability means, and the correction / changelog / rollback procedures. It
downloads nothing, trains nothing, and changes no code, schema, or API.

---

## 1. Purpose

The readiness checklist (`dataset_readiness_checklist.md`, P4.1.5) and the
Definition of Done (`dataset_v1_definition_of_done.md`, P4.1.6) say *what* must be
true before Dataset v1.0 is done. This policy says *how the freeze is enforced*:
the single automated gate that decides releasability, who signs off, how a
version is minted and frozen, and what happens when a frozen release must be
corrected or rolled back.

The gate is executed by `scripts/audit_dataset_readiness.py` (PART 1–6), which
composes the **frozen** P4.1.2 pipeline and the P4.2.1/P4.2.2 toolkit — it adds
no new metric and mutates no dataset artefact.

> **Thresholds are code-owned / frozen.** Every numeric limit mirrors
> `intelligence/device_ai/configs/settings.py` and the acquisition runbook. The
> taxonomy is the frozen 19 classes (version `1.0.0`) from `load_taxonomy()`,
> sourced from `components/data/components.yaml`. **If code and this document
> disagree, code wins.**

> **No fabrication.** A release is minted only from real, validated data. The
> audit never invents images, labels, counts, or quality metrics. When real data
> is absent it reports `BLOCKED` and refuses to emit a manifest.

---

## 2. Readiness states

The audit aggregates every gate into one overall state (most-severe wins):

| State | Meaning | Release allowed? | Route back to |
| --- | --- | --- | --- |
| `INVALID` | A hard defect makes the data unreleasable as-is (image/annotation validation failure, orphan labels, duplicates, split leakage). | No | Intake / annotation |
| `BLOCKED` | Real data (or a prerequisite directory) is absent; nothing to release. | No | Collection |
| `INCOMPLETE` | Data is present and internally valid, but coverage/completeness gates are unmet (missing class, annotation gap, class absent from a split). | No | Collection / annotation |
| `READY` | Every gate passes. | **Yes** | — |

Exit codes: `0` = `READY`, `1` = not ready (`INVALID`/`BLOCKED`/`INCOMPLETE`),
`2` = usage error.

---

## 3. Freeze gates

Every gate below must be `pass` for the dataset to be `READY`. Each maps to a
frozen component; none is re-implemented.

| # | Gate | Frozen source | Fail state |
| --- | --- | --- | --- |
| 1 | **Taxonomy** — version `1.0.0`, 19 classes, contiguous ids 0–18 | `taxonomy.load_taxonomy` | `INVALID` |
| 2 | **Data presence** — at least one real image discovered | `layout.list_image_paths` | `BLOCKED` |
| 3 | **Image validation** — Gate A structural checks clean | `image_validation.ImageValidator` | `INVALID` |
| 4 | **Annotation validation** — frozen validator + P4.2.2 layered checks clean | `validate_annotations.validate` | `INVALID` |
| 5 | **Coverage / completeness** — all classes present, `annotation_completeness == 1.0`, no gaps | `annotation_statistics` (frozen `AnnotationStatisticsCalculator`) | `INCOMPLETE` |
| 6 | **Duplicate limits** — no exact/near duplicate (Hamming `≤ duplicate_hamming_threshold`) | `duplicates.DuplicateDetector` | `INVALID` |
| 7 | **Split** — deterministic 70/20/10, seed 42; no cross-split leakage; every class present in train, val and test | `splitter.DatasetSplitter` | `INVALID` (leakage) / `INCOMPLETE` (class absent) |

**QA thresholds** (all code-owned; recorded here for reference, not redefined):

- Resolution: short side `≥ min_image_dimension` (32 px), long side
  `≤ max_image_dimension` (12000 px).
- File size: `≤ max_file_size` (10 MiB).
- Format: in `ALLOWED_IMAGE_EXTENSIONS` (`{jpg, jpeg, png, webp}`).
- Focus: variance-of-Laplacian `≥ blur_threshold` (100.0).
- Brightness: mean luminance in `[brightness_dark, brightness_bright]`
  (`[40, 220]`).
- Duplicates: perceptual-hash Hamming distance `≤ duplicate_hamming_threshold`
  (5) flags a near-duplicate.
- Split: `split_ratios` (0.7 / 0.2 / 0.1), `split_seed` (42).

The gate covers the automated, code-checkable subset of the P4.1.5 checklist and
P4.1.6 DoD. Human-owned items — second-review agreement, licence/privacy
clearance, negatives ratio, source-blend policy — remain **manual sign-off**
prerequisites (§4) and are *not* asserted by the tool.

---

## 4. Approval

Dataset v1.0 is frozen only when **both** conditions hold:

1. **Automated gate green** — `audit_dataset_readiness.py` reports `READY`
   (exit 0), with the JSON report archived as release evidence.
2. **Manual sign-off recorded** — the human-owned items in
   `dataset_readiness_checklist.md` §§2–7 and `dataset_v1_definition_of_done.md`
   §§2–6 are checked, and the **QA lead** (with the **dataset lead** for
   governance items) signs the checklist.

Neither substitutes for the other: a green audit with unmet manual items is
**not** a release, and a manual sign-off without a green audit is invalid.

---

## 5. Versioning & the freeze

- **Content-addressed identity.** A release is minted by
  `build_dataset_release.build_manifest` → frozen `build_release` /
  `release_to_dict`. The version carries a per-image SHA-256 manifest and an
  aggregate `content_hash` (`versioning.compute_content_hash`). Two snapshots are
  identical **iff** their image contents are identical.
- **Determinism.** Identical images + labels + `--version` + `--created-at`
  produce **byte-identical** output. The release timestamp is *injected*, never
  read from the wall clock; the content hash derives from image bytes and never
  depends on run time. (Verified on synthetic fixtures in P4.2.3.)
- **Label.** The public release label is `v1.0`. The frozen
  `DatasetVersionManager` assigns monotonic internal snapshot ids (`v1`, `v2`, …)
  when a version is persisted into the managed tree; the release builder computes
  its snapshot **in memory** and does not persist, so auditing never mutates
  pipeline state.
- **Freeze = immutability.** Once `v1.0` is approved and its `content_hash` is
  recorded, the underlying `datasets/raw` and `datasets/labels` for that hash are
  **immutable**. Any change to image bytes changes the hash and therefore
  constitutes a *new* version — never an edit of `v1.0`.

**CI freeze check:** `audit_dataset_readiness.py` must exit `0`, and re-running
`build_dataset_release.py` on the frozen inputs must reproduce the recorded
`content_hash`. A mismatch means the inputs changed and the freeze is broken.

---

## 6. Correction procedure (frozen release needs a change)

A frozen release is never edited in place. To correct it:

1. **Do not mutate `v1.0` inputs.** Apply the fix (re-annotation, image
   swap/removal, additional collection) to a working copy.
2. **Re-audit.** Run `audit_dataset_readiness.py` until `READY`.
3. **Mint the next version.** Build a new release with an incremented label
   (`v1.1` for additive/corrective, `v2.0` for a breaking change such as a
   taxonomy revision). The new `content_hash` is recorded.
4. **Record the reason** in the changelog (§7) and re-run manual sign-off (§4).
5. **Supersede, don't delete.** `v1.0` remains on record as superseded; consumers
   are pointed at the new version.

Severity guide for the label bump:

| Change | New label |
| --- | --- |
| Fix a few labels / drop a few images (no taxonomy change) | `v1.1` |
| Add images / classes coverage top-up (taxonomy unchanged) | `v1.x` minor |
| Taxonomy change, split-scheme change, or any breaking redefinition | `v2.0` |

---

## 7. Changelog

Every minted version appends one row here. Until real data exists there is no
released version, only the tooling.

| Version | Date (UTC) | content_hash | Change | Approved by |
| --- | --- | --- | --- | --- |
| _(none)_ | — | — | Dataset v1.0 **not released** — no real data present; release tooling verified against synthetic fixtures only (P4.2.3). | — |

---

## 8. Rollback

If a released version is later found defective (e.g. a leaked duplicate or a
licence problem surfaces post-release):

1. **Freeze consumption.** Notify downstream (training is deferred, so no live
   consumer today) and mark the version **withdrawn** in the changelog.
2. **Revert the pointer.** Point consumers back to the previous good version, or
   to *no* release if none exists.
3. **Correct forward.** Follow §6 to mint a fixed successor; do not resurrect the
   withdrawn hash.
4. **Root-cause.** Record which gate should have caught the defect; if the gate
   is automatable and was missed, file the gap against the audit tool. Because
   identity is content-addressed, a withdrawn version can always be
   distinguished from its replacement by `content_hash`.

---

## 9. Current status

As of this sprint (P4.2.3), the repository contains **zero** real dataset images
or labels (`datasets/raw` and `datasets/labels` hold only `.gitkeep`). The audit
therefore reports **`BLOCKED`** and **no Dataset v1.0 release exists**. The
freeze tooling and every gate are implemented and verified on synthetic fixtures;
they are ready to mint `v1.0` the moment real, validated data passes the gate.
See `docs/engineering/dataset_v1_release.md` for the release report.

---

## 10. Related documents

| Document | Role |
| --- | --- |
| `docs/engineering/dataset_v1_release.md` | The P4.2.3 release report (status, blockers, criteria) |
| `docs/ai/dataset_readiness_checklist.md` | Operational release gate (P4.1.5) |
| `docs/ai/dataset_v1_definition_of_done.md` | Completion contract (P4.1.6) |
| `docs/engineering/annotation_toolkit.md` | The P4.2.2 annotation scripts the audit composes |
| `scripts/audit_dataset_readiness.py` | The automated freeze gate (PART 1–6) |
| `intelligence/device_ai/configs/settings.py` | Source of every numeric threshold |

> **Out of scope for P4.2.3:** no training, YOLO execution, model export,
> OpenCLIP, OCR, or model/dataset downloads. This is the freeze-and-release
> contract for the dataset, not for a trained model.
