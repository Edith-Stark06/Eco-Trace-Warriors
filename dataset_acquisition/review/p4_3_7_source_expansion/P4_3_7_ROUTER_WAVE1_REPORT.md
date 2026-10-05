# P4.3.7 — Router Wave 1 Report (Pipeline Validation)

**Sprint:** P4.3.7 Wave 1 — Router (ID 11) controlled acquisition / pipeline validation
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (M1.4)
**Date:** 2026-08-15
**Protected HEAD:** `b4604f9`
**Outcome:** **BLOCKED — awaiting human self-collection.** The approved source
(self-collection) requires a person with a camera / physical access to real
routers. The automated agent cannot photograph physical devices, has no web
access this session, and **must not fabricate** images, provenance, annotations,
counts, or QA results. **No router data was collected, staged, annotated,
de-duplicated, or split.** Pipeline tooling is verified present and runnable; the
staging/provenance scaffolding and runbook are prepared for turnkey execution.

> **Honesty contract.** Per the task ("say UNVERIFIED rather than guessing") and
> the repo "No fabrication" policy (`dataset_v1_freeze_policy.md §1`: *the audit
> never invents images, labels, counts, or quality metrics; when real data is
> absent it reports BLOCKED*), every data-dependent field below is `BLOCKED` /
> `UNVERIFIED` — **not** a placeholder number.

---

## Why this is blocked (not a failure to be worked around)

The Wave 1 approval directs the **SAFE self-collection path** (family E in
`docs/ai/device_detection_sources.md`; `P4_3_7_ACQUISITION_PLAN.md §6`). Self-
collection is defined as **team photographs / partner e-waste yards** — real
images captured by a human. The three ways this environment could otherwise
obtain router images are all unavailable or forbidden:

1. **Self-collection** — requires a physical camera and real routers; the agent
   has neither. ❌
2. **External dataset import** — forbidden unless license + bbox + provenance +
   semantic mapping are independently verified (Wave 1 rules; `sources §6`), **and**
   web search/fetch are unavailable this session. ❌
3. **Fabrication / synthetic-as-collected** — prohibited by the "No fabrication"
   policy; synthetic is a ≤20% *balancing* aid, never the primary batch, and
   would misrepresent provenance. ❌

There is therefore **no honest way for the agent to produce the router batch.**
Collection is a human step. Everything that does **not** require the agent to
invent data has been done or verified.

---

## Pipeline readiness (verified this session, read-only)

| Stage | Tool (frozen) | Present & located | Behaviour on empty router batch |
| --- | --- | --- | --- |
| Provenance | `ProvenanceCollector` / `ProvenanceRecord` — `intelligence/device_ai/dataset/provenance.py` | ✅ | n/a until images exist |
| Gate A | `ImageValidator` — `intelligence/device_ai/dataset/image_validation.py` | ✅ | no images → nothing to validate |
| Gate B (structural) | `validate_annotations` / `AnnotationValidator` — `intelligence/device_ai/preprocessing/validator.py` | ✅ | no labels → nothing to validate |
| Gate B (completeness) | `AnnotationStatisticsCalculator` — `intelligence/device_ai/dataset/annotation_statistics.py` | ✅ | n/a |
| Dedup | `DuplicateDetector` (Hamming ≤ 5, **unchanged**) — `intelligence/device_ai/dataset/duplicates.py` | ✅ | n/a |
| Split | `DatasetSplitter.from_settings` (0.7/0.2/0.1, seed 42) — `intelligence/device_ai/dataset/splitter.py` | ✅ | empty input → raises `EmptyDatasetError` (by design) |
| Audit | `scripts/audit_dataset_readiness.py` | ✅ | no real images → `BLOCKED` (freeze policy §2/§9) |

No tool thresholds were read-modified; the duplicate Hamming threshold (5), split
ratios (0.7/0.2/0.1) and seed (42) are unchanged.

---

## The 14-point report

**1. Acquisition source** — Approved **self-collection** (SAFE path, family E).
No external dataset used (none verified; web unavailable). **Status: source
approved; execution pending human collection.**

**2. Number collected** — **0** (collection is a pending human step; the agent
cannot photograph physical routers). `UNVERIFIED` beyond 0-because-not-started.

**3. Number retained** — **0** (nothing collected to retain).

**4. Provenance status** — **BLOCKED / not started.** Schema and a header-only
`collection_log.template.csv` are prepared, mirroring the code-owned
`ProvenanceRecord` (`relative_path, source, license, contributor, collection_date,
checksum`). **Zero provenance rows exist** (none fabricated).

**5. License / permission status** — For the self-collection path the intended
basis is **team-owned (`CC-BY-4.0` / `proprietary`)**, which is license-clean by
construction — **but no images exist yet, so no license is recorded.** `UNVERIFIED`
until real images + basis are logged.

**6. Annotation count** — **0** (no images to annotate).

**7. Annotation validation** — **BLOCKED** (no labels). `AnnotationValidator` /
`AnnotationStatisticsCalculator` verified present; not run (nothing to validate).

**8. Manual QA result** — **BLOCKED** (no images/crops to review).

**9. Duplicate results** — **BLOCKED** (no images). Frozen `DuplicateDetector`
present; threshold **unchanged (Hamming ≤ 5)**; not run. When run, new router
images must be de-duplicated against the protected P4.3.5 candidate **and** within
the batch, with the threshold **untouched**.

**10. Split result** — **BLOCKED.** `DatasetSplitter` present and correct
(verified byte-identical last session); on an empty router set it raises
`EmptyDatasetError` by design. `split_ratios=(0.7,0.2,0.1)`, `split_seed=42`
unchanged. No split performed.

**11. Router train / val / test presence** — **Train: UNVERIFIED · Val:
UNVERIFIED · Test: UNVERIFIED** (no data to place). Per-split presence cannot be
asserted without a real batch.

**12. Readiness result** — Not re-run for a router batch (none exists). The
protected candidate's audit remains **INCOMPLETE** (coverage: 15/19 missing,
including router). Adding router alone would still be `INCOMPLETE` (14 classes
would remain missing). **Overall for this wave: BLOCKED.**

**13. Any failures** — **One hard blocker:** the agent cannot self-collect real
router images and will not fabricate them. No tool failed; no threshold was
altered; no protected artefact was touched. This is a capability/authorization
boundary, **not** a pipeline defect.

**14. Recommended next step** — A **human collector** captures a controlled router
batch (see `router/README.md` runbook), fills `collection_log.csv`, and imports
via `ProvenanceCollector` into the git-ignored staging path
`dataset_acquisition/staging/p4_3_7_expansion_v1/selfcollect_router_v1/`. Then run
Gate A → annotate → Gate B → **frozen** dedup → manual QA → split (0.7/0.2/0.1,
seed 42) → readiness audit, dropping evidence into `router/`. **Determine the next
router increment from the ACTUAL split result** — if any of train/val/test is
empty, collect more router images and re-run; do **not** invent a minimum count,
reseed, or change ratios. (Engineering guidance only, not a gate: the ~20-sample
`laptop` batch in P4.3.6 got 0 in the seed-42 test slice, so aim for a margin —
order of a few tens — then verify empirically.)

> Alternatively, if you can **supply** router images (drop real, license-clean
> photos into the staging path, or authorize a specific external dataset **after**
> its license/bbox/provenance/semantics are verified), the agent can then run the
> full pipeline and complete this report with real numbers.

---

## Git safety

**Before start:** HEAD `b4604f9`; `git status --short` = the 10 pre-existing
untracked entries + the untracked `p4_3_7_source_expansion/` docs dir. No tracked
modifications.

**After this report** (see the report's closing section / final response for the
captured output):
- P4.3.5 candidate — **unchanged** (not touched).
- P4.3.6 expansion — **unchanged / not merged**.
- Taxonomy — **unchanged**.
- Frozen duplicate threshold / split ratios / seed — **unchanged** (never edited).
- Release — **none**.
- Tracked modifications — **none** (only new *untracked* files under the
  authorized `router/` evidence dir + this report).
- **Not committed.**

---

## Summary line

**ROUTER WAVE 1 = BLOCKED (awaiting human self-collection).** Pipeline verified
runnable; scaffolding + runbook prepared; protected state intact; nothing
fabricated, merged, released, or committed.
