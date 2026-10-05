# P4.3.7 — Split Gate Recovery & Validation (Forensic Report)

**Sprint:** P4.3.7 — Source Expansion (split-gate recovery)
**Author:** Automated forensic recovery
**Date:** 2026-08-15
**Protected HEAD:** `b4604f9` (`dataset: add P4.3.6 multiclass expansion QA`)
**Branch:** `feat/p4-3-multiclass-acquisition`
**Verdict:** **No recovery was necessary.** The `DatasetSplitter` and its split
configuration were never missing — both are present at HEAD, byte-identical to
their historical versions. The authoritative gate contains **no minimum class
depth**, and the "150 images/class" and "29-image gap" figures are **unsupported
by any authoritative code or test.**

> **Headline finding:** The task's blocking premise — *"the historical
> DatasetSplitter implementation is missing from the current working tree"* — is
> **contradicted by the evidence.** `intelligence/device_ai/dataset/splitter.py`
> is tracked at HEAD, unmodified in the working tree, and identical to the commit
> that introduced it (`33cb380`). No restoration was performed because none was
> required.

---

## 0. Method & guardrails

- All investigation was **read-only**: `git show`, `git log`, `git grep`,
  `git diff`, file reads, `pytest`, and an in-memory splitter run fed from the
  candidate's identifiers.
- **No dataset files were modified.** No images acquired. No candidate mutated.
  No merge. No release. No commit.
- The "150 images/class" and "29-image gap" claims were treated as **UNVERIFIED**
  and tested against authoritative code and tests only.

---

## 1. Historical evidence

### 1.1 The splitter (`git show 33cb380:intelligence/device_ai/dataset/splitter.py`)

- File: `intelligence/device_ai/dataset/splitter.py`
- Introduced by commit **`33cb380`** — *"feat(ai): implement Device Intelligence
  Engine Phase 2 (M1.1-M1.11)"*.
- History (`git log --follow --oneline -- …/splitter.py`): **one commit only**,
  `33cb380`. `git log --all --diff-filter=D -- …/splitter.py` returns **nothing**
  → the file was **never deleted** in any commit on any branch.

Public surface (verbatim from history):

- `class DatasetSplitter`
  - `__init__(self, ratios: tuple[float, float, float], *, seed: int)` — validates
    ratios, stores `_ratios`, `_seed`.
  - `@classmethod from_settings(cls, settings, *, ratios=None, seed=None)` — reads
    `settings.split_ratios` and `settings.split_seed`, allowing per-call overrides.
  - `@staticmethod _validate_ratios(...)` — raises `InvalidSplitError` unless there
    are exactly 3 parts, all non-negative, summing to `1.0 ± 1e-6`.
  - `split_identifiers(identifiers: list[str]) -> SplitAssignment` — raises
    `EmptyDatasetError` if empty; **sort → seeded shuffle → slice**.
  - `split_records(records: list[ImageRecord]) -> SplitAssignment` — maps records to
    `record.relative_path` then delegates to `split_identifiers`.
- Module fn `split_to_dict(assignment) -> dict` — JSON serialisation.
- Imports: `numpy as np`; `..configs.settings.Settings`;
  `..exceptions.{EmptyDatasetError, InvalidSplitError}`;
  `.records.{ImageRecord, SplitAssignment}`.
- **No I/O**, **no per-class logic**, **no count threshold** of any kind.

### 1.2 The configuration (`git show 79cf6ba:…/configs/settings.py`)

- Commit **`79cf6ba`** — *"feat(dataset): add v1.0 freeze and release gate
  (P4.2.3)"* (ancestor of HEAD).
- `split_ratios` and `split_seed` are **Pydantic `BaseSettings` instance fields**
  on `class Settings(BaseSettings)`, env-backed via `pydantic-settings`, with a
  `@field_validator("split_ratios") _ratios_sum_to_one`.

---

## 2. Current-state evidence

| Check | Result |
| --- | --- |
| `git ls-tree HEAD …/dataset/splitter.py` | **present** |
| `git grep DatasetSplitter` (working tree) | present in `splitter.py`, `service.py`, 3 tests, `scripts/audit_dataset_readiness.py`, docs |
| `git grep split_ratios` / `split_seed` | present in `configs/settings.py` (L218 / L222) and `splitter.py` |
| `git diff 33cb380 HEAD -- …/splitter.py` | **empty** (byte-identical) |
| `git diff 79cf6ba HEAD -- …/configs/settings.py` | **empty** (byte-identical) |
| `git status --short -- splitter.py settings.py` | **empty** (no working-tree edits) |
| Deps present | `EmptyDatasetError` (`exceptions.py:123`), `InvalidSplitError` (`exceptions.py:144`), `ImageRecord` (`records.py:86`), `SplitAssignment` (`records.py:204`) |
| Call sites | `dataset/service.py:199` (`DatasetSplitter.from_settings(...)`); `scripts/audit_dataset_readiness.py:415` (split gate) |

**Conclusion:** the splitter and its configuration are fully intact at HEAD; all
dependencies and call sites resolve.

---

## 3. Exact historical split configuration

From `intelligence/device_ai/configs/settings.py` (identical at `79cf6ba` and HEAD):

```python
split_ratios: tuple[float, float, float] = Field(
    default=(0.7, 0.2, 0.1),
    description="Default train/validation/test split proportions.",
)
split_seed: int = Field(
    default=42,
    ge=0,
    description="Seed for deterministic, reproducible dataset splitting.",
)

@field_validator("split_ratios")
@classmethod
def _ratios_sum_to_one(cls, value):
    if any(part < 0.0 for part in value):
        raise ValueError("split_ratios must be non-negative")
    if abs(sum(value) - 1.0) > 1e-6:
        raise ValueError("split_ratios must sum to 1.0")
    return value
```

**Representation:** Pydantic `BaseSettings` **instance fields** (env-backed,
case-insensitive, defaulted). **Not** class constants, **not** nested config,
**not** hardcoded in the splitter. Verified values: `(0.7, 0.2, 0.1)` and `42`.

---

## 4. Exact splitter algorithm behaviour

```
split_identifiers(identifiers):
    if not identifiers: raise EmptyDatasetError
    ordered   = sorted(identifiers)                 # order-independent
    rng       = np.random.default_rng(seed)         # seeded → deterministic
    shuffled  = ordered[rng.permutation(len(ordered))]
    train_end = int(total * ratios[0])
    val_end   = train_end + int(total * ratios[1])
    train, val, test = shuffled[:train_end], shuffled[train_end:val_end], shuffled[val_end:]
    return SplitAssignment(sorted(train), sorted(val), sorted(test), ratios, seed)
```

Properties (each proven by test and/or the live run in §8):

- **Deterministic** — same inputs + seed ⇒ identical partition.
- **Order-independent** — inputs are sorted before shuffling.
- **Disjoint & complete** — every identifier lands in exactly one split; no leakage.
- **Ratio slicing** — floor on train/val, remainder to test.
- **No minimum depth** — operates on a flat identifier list; imposes **no per-class
  count and no total-count floor**. The only rejection is the empty-set guard.

---

## 5. Current compatibility assessment

**Fully compatible — identical, in fact.** The working-tree splitter equals the
`33cb380` original (empty diff); the working-tree settings equal the `79cf6ba`
version (empty diff). Every dependency (`exceptions`, `records`, `Settings`) and
consumer (`service.py`, `audit_dataset_readiness.py`, tests) is present and
resolves. **No adaptation is required or justified.**

---

## 6. Restoration changes

**None. STEP 5 was a verified no-op.**

- `intelligence/device_ai/dataset/splitter.py` — **not touched** (already present & identical).
- `intelligence/device_ai/configs/settings.py` — **not touched** (already present & identical).
- No settings were appended; the current architecture was preserved exactly.

Restoring anything would have introduced spurious changes to protected,
already-correct code. It was deliberately avoided.

---

## 7. Tests executed & results

Runner: `pytest 9.1.1`, Python `3.14.6`, numpy `2.5.1`, pydantic `2.13.4`
(config: `intelligence/device_ai/pyproject.toml`, `pythonpath=[".."]`).
**No test files were modified.**

```
python -m pytest \
  intelligence/device_ai/tests/test_dataset_splitter.py \
  intelligence/device_ai/tests/test_dataset_release.py \
  intelligence/device_ai/tests/test_detector_data_manifest.py \
  intelligence/device_ai/tests/test_training_config.py -v
→ 33 passed, 1 warning in 2.55s
```

| Test file | Count | Covers |
| --- | --- | --- |
| `test_dataset_splitter.py` | 8 | ratios (100→70/20/10), determinism, order-independence, disjoint+complete, empty→`EmptyDatasetError`, invalid/negative ratios→`InvalidSplitError`, `split_to_dict` shape |
| `test_dataset_release.py` | 4 | release assembly, `split` embedded (seed 42, counts sum), **split optional (null allowed)** |
| `test_detector_data_manifest.py` | 5 | split-aware `data.yaml`, counts match split, canonical taxonomy names, **flat fallback without split** |
| `test_training_config.py` | 16 | training/config settings |

No dedicated automated test exists for `scripts/audit_dataset_readiness.py`
itself; its gates were validated directly against the candidate (§8). None of the
tests assert or reference a minimum class depth.

---

## 8. Actual split results (live, read-only)

Input: the **P4.3.5 candidate** at
`dataset_acquisition/candidate/p4_3_5_dataset_v1_candidate/` (**252 images, 252
label files, 358 boxes** — matches protected state). The splitter was run
in-memory over identifiers built exactly as the audit builds them
(`relative_path` of each discovered image). **Nothing was written to disk.**

```
split_ratios = (0.7, 0.2, 0.1)   split_seed = 42
total identifiers : 252
counts            : train=176, val=50, test=26   (sum 252)
leakage           : 0
uncovered         : 0
deterministic (fresh instance a==b)          : True
order-independent (a == reversed-input)      : True
ratio math        : int(252*0.7)=176, int(252*0.2)=50, remainder=26
```

Class-level distribution (4 of 19 classes annotated):

| id | class | images | boxes |
| --- | --- | --- | --- |
| 1 | smartphone | 5 | 11 |
| 2 | tablet | 74 | 97 |
| 5 | monitor | 94 | 147 |
| 8 | printer | 79 | 103 |
| | **total** | **252** | **358** |

Per-split class presence: **all four present classes appear in train, val AND
test** → `classes_absent_from_split: none` → **split gate = READY**.

Recorded prior evidence (`…/p4_3_5_dataset_v1_candidate/readiness.json`, read-only):

```
overall: INCOMPLETE
gate_states: taxonomy=READY, data_presence=READY, image_validation=READY,
             annotation_validation=READY, coverage=INCOMPLETE, duplicates=READY,
             split=READY
[split]    READY — "70/20/10 seed-42 split verified: no leakage, all classes per split"
           counts {train:176, val:50, test:26}, leakage 0, uncovered 0, absent {}
[coverage] INCOMPLETE — "15 class(es) missing"; completeness 1.0; images_without_labels 0
           missing: laptop, desktop, server, crt_monitor, television, keyboard,
                    mouse, router, power_supply, cable, camera, game_console,
                    smartwatch, headphones, battery
```

**Interpretation:** The candidate is `INCOMPLETE` **only because of coverage** —
15 of 19 classes have **zero** images. The **split gate already passes**.
Empirically, `smartphone` with just **5 images** was placed into all three splits
under seed 42 — direct evidence that the split gate has **no high per-class
floor**.

---

## 9. Authoritative minimum class depth

**The authoritative gate is `scripts/audit_dataset_readiness.py`** (the freeze
gate named by `docs/ai/dataset_v1_freeze_policy.md §3`). Its two relevant gates:

- **`_coverage_gate`** (L304–359): passes iff `not missing_classes and
  annotation_completeness == 1.0 and not images_without_labels`. → grades
  `INCOMPLETE` when any class is **absent (count 0)**.
- **`_split_gate`** (L398–490): passes iff **no leakage**, **no uncovered id**,
  and **every annotated class present in each of train/val/test** (else
  `INVALID`/`INCOMPLETE`).

Searches for any encoded floor returned nothing gate-side:

- `git grep -nE "\b150\b" intelligence/ scripts/` → every hit is a **collection
  target** (`docs/ai/templates/*.csv`, `dataset_metadata.json` `min_target: 150`,
  acquisition-planner `planned_min=150` in tests) or unrelated (material mass,
  pixel dims). **Zero** occurrences in any release/split/coverage gate.
- `git grep` for `min_*per*class` / `class_depth` / minimum-count concepts →
  nothing in the gate path.
- `docs/ai/dataset_v1_freeze_policy.md §3` QA-threshold table lists, for Split,
  only `split_ratios (0.7/0.2/0.1)` and `split_seed (42)` — **no count**. It
  states: *"If code and this document disagree, code wins,"* and thresholds
  *"mirror settings.py"*, which has **no** minimum-depth field.

> **Authoritative minimum class depth: NONE is encoded.** The only depth
> constraint is **structural and emergent** — a class must have enough samples
> that the seeded 70/20/10 slice places ≥1 in each split. That is a *presence*
> requirement, not a fixed number; on this candidate, 5 images sufficed for
> `smartphone`.

---

## 10. On the "150 images/class" requirement

**UNSUPPORTED by any authoritative gate.** `150` exists **only** as a *collection
aspiration* (`min_target` in `dataset_metadata.json`, `target 150+` in source
docs, `planned_min` acquisition-planner parameter). It is **never** asserted by
`audit_dataset_readiness.py`, the splitter, the coverage gate, the release
builder, the freeze policy's gate table, or any test. Unless and until concrete
gate code or a test encodes it, **the 150-image requirement must not be treated
as a release/split gate.**

---

## 11. On the "29-image gap"

**MUST NOT be used.** The "29-image gap" is derivable only from the unproven
150-image premise (and would additionally require a specific current per-class
depth). Since 150 is **not** an authoritative gate (§10), any "29 gap" computed
from it is **invalid**. Do not calculate against it or acquire to close it unless
150 is first independently proven from authoritative code/tests. No such proof
exists in this repository.

---

## 12. Protected dataset state verification

| Protected item | Expected | Verified |
| --- | --- | --- |
| HEAD commit | `b4604f9` | ✅ `b4604f9` |
| P4.3.5 candidate | 252 images / 358 boxes / INCOMPLETE | ✅ 252 imgs, 252 labels, 358 boxes; `readiness.json` overall = INCOMPLETE |
| P4.3.6 expansion | 119 samples / 174 boxes / QA_PENDING | ✅ untouched (not read-modified; staging intact) |
| Merge | none | ✅ none performed |
| Release | none | ✅ none built (audit not re-run with `--release-out`) |
| Candidate files | unchanged | ✅ no writes; split computed in-memory only |
| P4.3.6 QA package | unchanged | ✅ not modified |

---

## 13. Git diff / status

```
$ git rev-parse --short HEAD
b4604f9

$ git diff --stat
(empty — no tracked modifications)

$ git diff -- intelligence/device_ai/dataset/splitter.py
(empty — unchanged)

$ git diff -- intelligence/device_ai/configs/settings.py
(empty — unchanged)

$ git status --short
?? dataset_acquisition/review/p4_3_4_multiclass_qa_v1/automated_acceptance_log.json
?? dataset_acquisition/review/p4_3_4_multiclass_qa_v1/human_review_log.jsonl
?? dataset_acquisition/review/p4_3_4_multiclass_qa_v1/signoff_template.backup_20260811_225544.json
?? dataset_acquisition/review/p4_3_4_multiclass_qa_v1/signoff_template.before_auto_accept.json
?? dataset_acquisition/review/tmp_duplicate_review_p435/
?? scripts/_build_p435_labels.py
?? scripts/auto_accept_multiclass_qa_p434.py
?? scripts/review_multiclass_qa_p434.py
?? tmp_settings.py
?? tmp_splitter.py
```

All 10 untracked entries **pre-existed** this task (identical to the session-start
status). This report adds one new untracked file:
`dataset_acquisition/review/p4_3_7_source_expansion/P4_3_7_SPLIT_GATE_RECOVERY.md`.
No tracked file was modified; no test was changed; no candidate/QA artefact was
touched. **Nothing was committed.**

> Note: `tmp_settings.py` and `tmp_splitter.py` are **pre-existing untracked
> scratch files** (present at session start). They are **not** the canonical
> implementation (which lives at `intelligence/device_ai/…` and is intact) and
> were **not** created or modified here.

---

## 14. Recommendation for next P4.3.7 action

1. **Discard the 150/29 framing** for the split gate. The split gate is **already
   `READY`** on the P4.3.5 candidate; it is **not** the blocker.
2. **The real, code-enforced blocker is COVERAGE**: 15 of 19 classes have **zero**
   images. To move `overall` from `INCOMPLETE` toward `READY`, acquisition must
   **add the missing classes** (breadth), not top up the 4 existing classes to an
   invented depth.
3. **Per-split presence is the true depth guardrail**: each class needs enough
   samples that the 70/20/10 seed-42 slice puts ≥1 into train, val AND test
   (empirically ~5+ sufficed here). Validate each newly added class against
   `_split_gate`, not against a fixed 150.
4. **P4.3.6 expansion (~6 classes, QA_PENDING, unmerged)** would raise coverage
   toward ~10/19 — still short of the 19-class coverage gate. Any merge/release
   remains a separate, gated decision and is **out of scope** here (no merge, no
   release performed).
5. If a per-class **minimum depth** is genuinely desired as policy, it must be
   **encoded** (a settings field + a gate check + a test) and documented in the
   freeze policy **before** it can be treated as authoritative. Today it is not.

**Do not proceed to dataset acquisition on the basis of "150/class" or a "29
gap."** Proceed (if at all) on the basis of the coverage gate (all 19 classes
present) and per-split class presence.
