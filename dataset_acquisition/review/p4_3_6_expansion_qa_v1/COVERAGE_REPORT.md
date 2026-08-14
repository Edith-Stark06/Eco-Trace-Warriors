# P4.3.6 — Coverage & Readiness Report

**Sprint:** P4.3.6 multi-class expansion (6 verified Open Images source classes)
**Status of this document:** Phase 8–9 (full audit + coverage analysis)
**Merge status:** DEFERRED — human QA decision is "Leave QA_PENDING". No merge performed
this sprint. The existing clean candidate remains at 252 images.

---

## 1. Integrity check — existing 252 candidate is UNCHANGED

Re-audited `dataset_acquisition/candidate/p4_3_5_dataset_v1_candidate/` after all
expansion work. Result is identical to its pre-sprint state:

| Field | Value |
|---|---|
| overall | INCOMPLETE |
| images | 252 |
| boxes | 358 |
| missing classes | 15 |
| taxonomy / data_presence / image_validation / annotation_validation / duplicates / split | READY |
| coverage | INCOMPLETE |

The clean candidate was never modified in-place while building expansion data
(integrity rule #1 upheld). Evidence: `_recheck_252_readiness.json` / `.md`.

---

## 2. Expansion set (verified sources only)

Six Open Images classes were converted with the canonical converter into a
git-ignored staging workspace, duplicate-checked, visually QA'd, and
annotation-validated. **119 samples** survived the duplicate cross-check
(2 genuine cross-class near-duplicates against the protected candidate were
excluded — see `duplicate_evidence.json`). All 119 are currently **QA_PENDING**
awaiting a human sign-off decision (`signoff_template.json`).

| ecotrace class | class_id | source class (Open Images) | kept images | boxes |
|---|---|---|---|---|
| laptop | 0 | Laptop | 20 | 34 |
| television | 7 | Television | 19 | 44 |
| keyboard | 9 | Computer keyboard | 20 | 24 |
| mouse | 10 | Computer mouse | 20 | 25 |
| camera | 14 | Camera | 20 | 21 |
| headphones | 17 | Headphones | 20 | 26 |
| **total** | | | **119** | **174** |

Annotation validation: `is_valid = true`, 0 issues (`annotation_validation.json`).

---

## 3. Merged preview — the end-state IF all 119 are accepted

To show exactly what merging would produce (without creating a committed
candidate while QA is pending), a temporary merged view (252 + 119 = 371) was
assembled under git-ignored `staging/p4_3_6_merged_preview/` and audited.
Evidence: `readiness_merged_preview.json` / `.md`.

| Field | Value |
|---|---|
| overall | **INCOMPLETE** |
| images | 371 |
| boxes | 532 |
| **coverage** | 10 / 19 classes represented |
| duplicates | **0** @ hamming threshold **5** (threshold NOT weakened) |
| taxonomy / data_presence / image_validation / annotation_validation / duplicates | READY |
| coverage | INCOMPLETE (9 missing) |
| **split** | **INCOMPLETE** (see §5) |

### Coverage would rise from 4/19 → 10/19

- **Already represented (4):** smartphone, tablet, monitor, printer
- **Would be added (6):** laptop, television, keyboard, mouse, camera, headphones
- **Still missing (9):** desktop, server, crt_monitor, router, power_supply,
  cable, game_console, smartwatch, battery

---

## 4. Why the sprint stops at 10/19 (highest defensible coverage)

Per the absolute rule, we do **not** fabricate data to force the coverage gate to
READY. The 9 remaining classes have **no verified Open Images source class** that
can be honestly mapped to the EcoTrace taxonomy. Inventing a mapping (e.g. Open
Images "Computer monitor" → crt_monitor, or a generic "Box" → server) would
violate integrity rules #4, #5, and #12. Therefore 10/19 is the highest
defensible coverage achievable from verified sources this sprint.

---

## 5. New finding — verified sources are too THIN for the split gate

The merged preview also fails the **split** gate, independently of coverage:

- `classes_absent_from_split: { "test": [0] }` — laptop (class 0) has only
  **20 samples**; a 70/20/10 split at seed 42 places **0** in the test split.
- No leakage, no uncovered classes; this is purely a small-sample effect.

**Implication for the next sprint:** reaching READY requires not only *breadth*
(the 9 missing classes) but also *depth*. Classes acquired at ~20 samples are too
thin to guarantee representation in all three splits. The next acquisition sprint
should target a minimum per-class sample floor (enough that 10% test share is
≥ a few images) for every class, including the 6 added here.

---

## 6. What the next acquisition sprint needs

To legitimately reach READY (19/19, all gates green):

1. **Acquire verified sources for the 9 missing classes** — none are currently
   mappable from Open Images V7. Requires a new verified data source or a
   documented, reviewed mapping. Do NOT invent mappings.
2. **Increase depth for thin classes** — raise every class (especially the 6 added
   here at ~20 each) above the split floor so 70/20/10 places ≥1 sample per split.
3. **Then** run the readiness audit; only build an official v1 release when
   `overall == READY`.

No official release was built (readiness is INCOMPLETE — integrity rules #15, #16).
