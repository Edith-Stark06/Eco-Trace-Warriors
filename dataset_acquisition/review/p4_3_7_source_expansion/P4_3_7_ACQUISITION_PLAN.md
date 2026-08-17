# P4.3.7 — Acquisition Plan (Coverage-First, 9 Missing Classes)

**Sprint:** P4.3.7 — Coverage-First Source Expansion (research/planning only)
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (M1.4)
**Date:** 2026-08-15
**Protected HEAD:** `b4604f9`
**Status:** **PLAN ONLY — nothing is acquired, annotated, merged, released, or
committed by this document.** Execution happens in a later, separately-approved
sprint against `docs/ai/device_collection_checklist.md`.

> **Binding constraints (carried from the task):** No "150 images/class" target.
> No "29-image gap". No fabricated counts. No invented class mappings. No
> acquisition yet. No candidate modification. No merge of P4.3.6. No release. No
> commit. External-source licenses/bboxes/counts were **not verifiable this
> session** and remain `VERIFY` (see Matrix §0).

---

## 1. Objective

Move the dataset from **4/19** covered classes (smartphone·1, tablet·2,
monitor·5, printer·8) toward the **19/19** coverage gate by planning the
acquisition of the **9 zero-image classes**: desktop·3, server·4, crt_monitor·6,
router·11, power_supply·12, cable·13, game_console·15, smartwatch·16, battery·18.

The authoritative blocker is **coverage** (all 19 classes present), not depth to
any fixed number — established in `P4_3_7_SPLIT_GATE_RECOVERY.md`. Each added
class contributes **+1** toward the coverage gate; the only per-class depth
requirement is emergent **per-split presence** (§5).

---

## 2. Prioritisation criteria

Each class is scored on five factors (no factor is a numeric gate):

1. **License-safety / reproducibility** — is a license-clean path available now
   without an external-license gamble? (Self-collection = highest.)
2. **Semantic cleanliness** — is the class well-defined and low-confusion with
   neighbours, or does its only external option collapse into a `REJECT` trap?
3. **Split-presence risk** — how easily can we gather enough clean, deduped
   samples that the 70/20/10 seed-42 split lands ≥1 in train **and** val **and**
   test (§5)?
4. **Physical access / effort / hazard** — availability of real objects to
   photograph; annotation difficulty; safety.
5. **Coverage impact** — identical (+1) for all 9, so it is a tie-breaker only.

> Coverage impact is equal across all nine because the coverage gate requires
> **all** 19 — the nine are ultimately *all* required. Ordering therefore
> optimises **certainty and license-cleanliness first**, so the team stands up
> the new-source QA loop on the safest class before the scarce/hazardous ones.

---

## 3. Prioritised waves

| Wave | Classes (ID) | Rationale | Lead source (SAFE) | Scale-up (CONDITIONAL, verify) |
| --- | --- | --- | --- | --- |
| **1 — Easy, license-clean, low-confusion** | **router·11**, smartwatch·16 | Ubiquitous consumer items, trivial license-clean self-collection, distinct silhouettes; only external trap is a `REJECT` label so self-collection leads cleanly | Self-collection | Roboflow networking / smartwatch sets *(verify license+bbox)* |
| **2 — Common but confusion-prone** | desktop·3, power_supply·12 | Common and self-collectable, but each has a `REJECT` trap (generic "Computer"; "plugs & sockets") and neighbour confusion (monitor; cable/battery) — needs firm annotation guidelines | Self-collection | Objects365/LVIS *(verify category exists + license)*, Roboflow |
| **3 — Abundant but hard to annotate** | cable·13, battery·18 | Objects are everywhere but boxing is hard (thin/curved cables) or hazardous + polysemous (battery); synthetic can balance | Self-collection (+ synthetic ≤20% for battery) | Roboflow cable/battery sets, Wikimedia + manual boxing |
| **4 — Scarce / access-limited** | server·4, crt_monitor·6, game_console·15 | Real units are access-limited (ITAD partners, retro/e-waste, consoles); lead with self-collection where reachable, community + synthetic to fill | Self-collection (partner ITAD / e-waste yards) | Roboflow datacenter/retro/console *(verify)*, Wikimedia + manual, synthetic |

**First class to acquire:** **`router` (ID 11)** — see `P4_3_7_COVERAGE_RESEARCH.md §11`
for the full justification. It maximises certainty (self-collection needs no
external-license verification to start), semantic cleanliness, and low hazard,
letting the team validate the entire new-source → QA → split-presence loop on an
easy class before the scarce tier.

---

## 4. Per-source verification gate (every CONDITIONAL row must pass **before** import)

No external dataset may be imported until **all** of the following are recorded in
`collection_log.csv` (checklist §2–3). Failing any single item → **exclude**.

- [ ] **License** permits **ML training AND redistribution** (CC-BY, CC0,
      CC-BY-SA w/ attribution, Apache-2.0, public domain, or team-owned). Read the
      *underlying* image license, **not** the hosting page's banner. Unclear →
      exclude. *(sources §6)*
- [ ] **Bounding boxes** actually ship for the target class (not classification
      labels, not masks-only unless convertible). If image-only (Wikimedia/Openverse)
      → route through **manual annotation**, do not treat as detection-ready.
- [ ] **Semantic tightness** — a sample inspection confirms boxes are the target
      object, not a `REJECT` neighbour (e.g. console body, not controller).
- [ ] **Count** confirmed by actual inspection (public counts drift) — recorded as
      an observed number, never estimated or copied from a catalogue.
- [ ] **Provenance** capturable per image (source, license, contributor, date,
      SHA-256) via `ProvenanceCollector`. *(checklist §3)*
- [ ] **Attribution** (author + source URL) captured for CC-BY/CC-BY-SA.

Manufacturer/product imagery (family D) remains **excluded** without a signed
license.

---

## 5. Split-gate constraint (binding for every added class)

The deterministic gate (`scripts/audit_dataset_readiness.py`, `_split_gate`) —
70/20/10, seed 42, **global non-stratified shuffle** — requires, for **every
annotated class**:

1. **No cross-split leakage** — no identifier in more than one split; and, before
   splitting, **no near-duplicate** (perceptual-hash Hamming ≤ 5) of the same
   physical item across splits. New samples must be de-duplicated **against the
   protected P4.3.5 candidate and within themselves** (as P4.3.6 did — it dropped
   2 genuine cross-class near-dupes rather than weaken the threshold).
2. **Per-split presence** — the class appears in train **and** val **and** test.

**Depth guidance (engineering, NOT a gate, NOT the phantom 150):** because the
split is a *global* shuffle, per-split presence is emergent and depends on the
class's sample count and its position in the shuffle. Evidence from this repo:

- A class with **~20** samples **can still receive 0 in the test slice**
  (P4.3.6: `laptop` at ~20 landed 0 in the seed-42 test split).
- A class with very few samples landing in all three splits (e.g. 5) is a
  **seed-specific accident, not a floor** — do **not** treat any small number as
  "the minimum".

To make per-split presence **reliable rather than seed-lucky**, target enough
**accepted, deduped** samples per new class that even the ~10% test slice expects
≥1 with margin — i.e. comfortably **above the ~20 that demonstrably failed**
(order of a few tens). Validate each newly added class **empirically against
`_split_gate`** after collection; if a class misses a slice, collect more of that
class — never lower the ratios or reseed.

---

## 6. Reproducible acquisition method (per source family)

| Family | Method | Notes |
| --- | --- | --- |
| **Open Images V7** | Existing wired pipeline: `scripts/acquire_openimages_multiclass.py` (plan-driven) / `acquire_openimages_lowmem.py` (chunked) → `scripts/convert_openimages_to_yolo.py`. | **Not applicable to the 9** — all are `UNMAPPED` in the plan CSV. Listed only for completeness. |
| **Community sets** (Roboflow/Kaggle) | Manual download of a **verified** dataset → convert to YOLO with the taxonomy class-id map → import via `ProvenanceCollector`. | Gated by §4 per dataset. No new mapping invented — map only to the exact canonical class. |
| **Open media** (Wikimedia/Openverse) | Download license-clean images → **manual annotation** (checklist §5, exact taxonomy order) → import with per-image provenance. | Image source only; boxes created in-house. |
| **Self-collection** | Photograph real units (Indian e-waste context) → annotate → import with `proprietary`/`CC-BY-4.0` provenance. | `SAFE`; consent/PII per checklist §2. |
| **Synthetic** | Composite/render → mark `synthetic`, keep ≤ ~20% of the class. | Balancing only; records derivation source. |

All paths converge on the **frozen QA pipeline** (Gate A `ImageValidator` → Gate
B `AnnotationValidator` + `AnnotationStatisticsCalculator` → dedup → split →
audit). No pipeline code changes are proposed.

---

## 7. Staging & isolation (protect the frozen candidate)

- New per-class work stages under a **git-ignored** path, e.g.
  `dataset_acquisition/staging/p4_3_7_expansion_v1/<source>_<class>_v1/`, mirroring
  the P4.3.6 layout — **never** written into
  `candidate/p4_3_5_dataset_v1_candidate/`.
- The P4.3.5 candidate (252 img / 358 box / INCOMPLETE) stays **byte-unchanged**.
- QA deliverables (preview JPGs, `signoff_template.json` as `QA_PENDING`) follow
  the P4.3.4/P4.3.6 review-package convention.

---

## 8. Explicit non-actions (this sprint)

- **No** merge of the P4.3.6 expansion (119 QA_PENDING) — it stays unmerged; a
  merge/release is a separate gated decision.
- **No** dataset acquisition, download, annotation, or candidate mutation.
- **No** release, **no** version mint, **no** commit.
- **No** revival of "150/class" or "29-image gap".
- **No** weakening of the duplicate threshold, split ratios, or seed.

> Next: `P4_3_7_COVERAGE_RESEARCH.md` (12-section research + first-class
> recommendation). Execution, when approved, follows
> `docs/ai/device_collection_checklist.md` top-to-bottom.
