# Trust & Provenance Engine (M2.5)

> The **ninth downstream consumer** of the Device Intelligence Engine and the
> fifth component of milestone **M2** — an internal-only, **deterministic trust
> evaluator** that consumes the four upstream artefacts the pipeline already
> produced (the immutable **`DevicePassport`** from M2.3, its
> **`PassportIntegrityReport`** from M2.4, the normalized
> **`DecisionKnowledgeReport`** from M2.1 and the actionable **`DecisionReport`**
> from M2.2) and emits a single, immutable **`PassportTrustReport`**. It answers
> one question about the passport: *how much can this document be trusted as a
> faithful representation of the device?* — expressed as a normalized **trust
> score**, a mapped **trust level** (`high` / `medium` / `low` / `untrusted`) and
> four transparent sub-axes (**identity confidence**, **evidence consistency**,
> **decision confidence** and **integrity confidence**), with **ordered
> reasoning** and **ordered warnings**. Unlike M2.3 (which *assembles* the
> passport) and M2.4 (which *checks* it), the trust engine carries **no inference
> and no evidence collection of its own**: it reads the existing confidence and
> consistency signals its four inputs already carry, blends them into a
> weighted-average score via an **external, versioned catalogue**, and maps that
> score to a level. It ships **no new endpoint** and leaves the `/predict` API
> contract **unchanged and backward-compatible**.

**Module:** `intelligence/device_ai`
**Milestone:** M2.5 — Trust & Provenance Engine
**Status:** implemented; internal-only (no router, no HTTP surface)

---

## Table of contents

1. [Scope](#scope)
2. [Architecture](#architecture)
3. [Domain models](#domain-models)
4. [The external trust catalogue](#the-external-trust-catalogue)
5. [Catalogue loader](#catalogue-loader)
6. [The deterministic engine](#the-deterministic-engine)
7. [The four trust sub-axes](#the-four-trust-sub-axes)
8. [Trust score and level — a transparent verdict](#trust-score-and-level--a-transparent-verdict)
9. [Deterministic serialization](#deterministic-serialization)
10. [Configuration](#configuration)
11. [Testing](#testing)
12. [Integration guide](#integration-guide)
13. [Worked examples](#worked-examples)
14. [Backward compatibility](#backward-compatibility)
15. [Design rationale](#design-rationale)

---

## Scope

M2.5 is the **ninth** component to consume the fusion engine's output
(transitively, via the passport and its reports), and the first that **grades the
trustworthiness** of an existing verdict rather than producing a new analysis,
composition or structural check. The passport core (M2.3) assembles the upstream
reports into an immutable `DevicePassport`; the integrity engine (M2.4) confirms
it is structurally sound and hashes it; the trust engine answers the next
question: *"given all of that, how much confidence should a consumer place in
this passport's claim about the device?"* It consumes **four** inputs and reads
only their existing aggregate signals — never any raw image or model:

| # | Input | Source (M) | What the engine reads from it |
|---|---|---|---|
| 1 | **Device passport** | M2.3 | identity completeness (strong fields present) + classification confidence + device type + carried warnings |
| 2 | **Integrity report** | M2.4 | validation status (`valid`/`valid_with_warnings`/`invalid`) + warning count |
| 3 | **Decision-knowledge report** | M2.1 | overall confidence + device type |
| 4 | **Circular decision report** | M2.2 | recommendation confidence + device type |

**The report includes exactly the eight required fields** (plus provenance):

| Requirement | Report field |
|---|---|
| Trust Score | `trust_score` (normalized `[0, 1]` weighted average) |
| Trust Level | `trust_level` (`high` / `medium` / `low` / `untrusted`) |
| Identity Confidence | `identity_confidence` (axis value) |
| Evidence Consistency | `evidence_consistency` (axis value) |
| Decision Confidence | `decision_confidence` (axis value) |
| Integrity Confidence | `integrity_confidence` (axis value) |
| Ordered Reasoning | `reasoning` (ordered, human-readable) |
| Ordered Warnings | `warnings` (ordered operator cautions) |

The four axis values are also retained as ordered `TrustAxis` records (`axes`),
each carrying its value, its catalogue **weight** and a human-readable **reason**,
so the score is explainable end to end.

**Explicitly in scope**

- `PassportTrustReport` — the immutable trust verdict with the eight required
  fields, the four-axis breakdown, provenance and an optional timestamp.
- An **external, versioned** trust catalogue (YAML/JSON) with a strict loader
  that validates aggressively and fails with a typed error.
- A pure `TrustEngine` (project four upstream reports → four axes → weighted score
  → mapped level).
- An injected `TrustService` orchestration façade.

**Explicitly out of scope** (do **not** implement in M2.5): **blockchain**,
**smart contracts**, **digital signatures**, **QR codes**, **wallets**,
**ownership history**, **database persistence**, **REST endpoints**,
**marketplace** and **carbon credits**. The engine is a **scorer**, not a new
inference — no axis is evidence it invented, and no field is a currency amount.
The engine is **internal only** — no router is mounted, `application.py` is
untouched, and the `/predict` response schema is **unchanged**.

**Key asymmetry.** A malformed **catalogue** *raises* (a `PassportTrustRuleError`
at load time — it is an engine fault); inputs that merely **score low** are
*reported* as a low `trust_level` and ordered warnings on the produced report
(they are the very data the engine was asked to grade, never a reason to crash).
This mirrors M2.4's checker asymmetry: only the engine's own policy file can crash
the engine.

## Architecture

The engine is a **pure domain layer** with the same shape as `integrity/`,
`circular/` and `passport/`: frozen slotted dataclasses, a stateless engine, and
an injected service. It imports its four input types **only under
`TYPE_CHECKING`** (except the small `ValidationStatus` enum, which it compares
against at runtime), so there is no heavyweight runtime coupling and no import
cycle — the four reports are passed in, never reached into past their public
surface.

```
   passport core (M2.3) ─► DevicePassport ───────────────┐
   integrity engine (M2.4) ─► PassportIntegrityReport ───┤
   decision engine (M2.1) ─► DecisionKnowledgeReport ────┤
   circular engine (M2.2) ─► DecisionReport ─────────────┤
                                                         │
   ┌──────────────── trust/ (internal) ───────────────────▼──────────┐
   │  service.py   TrustService.assess(passport, integrity,          │
   │        │              knowledge, decision)                      │
   │        ▼             ▼              ▼                            │
   │   rules.py       engine.py     config.py                        │
   │  load_rules      TrustEngine   TrustConfig                      │
   │  TrustRuleSet    (project →     (catalogue locator +            │
   │  (external        score →       projection knobs)               │
   │   YAML/JSON,      level)                                        │
   │   validated)         │                                          │
   │   models.py  PassportTrustReport (frozen) · TrustAxis ·         │
   │              TrustLevel                                         │
   └───────────────────────────────────────────────────────────────────┘
                                ▼
       downstream (M2.6+ blockchain / anchor) — never /predict
```

Layering (dependencies point downward, never upward):

```
passport/ · integrity/ · decision/ · circular/   (produce the four inputs)
   ↓  (TYPE_CHECKING only; the four reports are passed in)
trust/  (models.py + rules.py + config.py + engine.py + service.py)
   ↓
exceptions · configs   (cross-cutting foundations)
```

The package contains **no HTTP imports, no FastAPI, and its only I/O is reading
the catalogue file once at service construction.** After that, `assess()` is a
pure function of its inputs except for the injected clock (which defaults to UTC
`now` and can be replaced or disabled for determinism).

## Domain models

`trust/models.py` defines the vocabulary of the verdict. Each is a small, frozen,
slotted dataclass with its own `to_dict()` so the report serializes
deterministically.

### `TrustLevel`

A `str` enum with four states ordered by descending trust:

| Value | Meaning |
|---|---|
| `high` | Most trustworthy — the passport is a faithful, well-evidenced representation. |
| `medium` | Trustworthy with minor gaps. |
| `low` | Flags caution — weak identity, disagreement or soft integrity cautions. |
| `untrusted` | Should not be relied upon without manual verification (e.g. integrity failed). |

`TrustLevel.values()` returns the wire values in declaration order. This enum is
the **single source of truth** the external catalogue's level names are validated
against on load.

### `TrustAxis`

One normalized sub-axis's weighted contribution — what makes the score
explainable:

| Field | Meaning |
|---|---|
| `name` | Machine-readable axis name (one of the canonical four). |
| `value` | The normalized `[0, 1]` axis value projected from upstream. |
| `weight` | The non-negative catalogue weight this axis carries in the score. |
| `reason` | Human-readable explanation of how the value was derived. |

### `PassportTrustReport`

The immutable trust verdict — a frozen slotted dataclass:

| Field | Meaning |
|---|---|
| `passport_id` | The id of the passport that was assessed (provenance). |
| `trust_score` | Normalized `[0, 1]` weighted average of the four axes. |
| `trust_level` | The `TrustLevel` mapped from the score via catalogue thresholds. |
| `identity_confidence` | Identity-completeness + classification-confidence axis value. |
| `evidence_consistency` | Cross-report device-type agreement axis value. |
| `decision_confidence` | Mean of the two decision confidences axis value. |
| `integrity_confidence` | Integrity-status axis value (damped by warnings). |
| `axes` | The four `TrustAxis` records, in canonical order. |
| `reasoning` | Ordered, human-readable reasons behind the verdict. |
| `warnings` | Ordered operator-facing cautions (may be empty). |
| `engine_version` | Version of the trust engine that produced this. |
| `rules_version` | Version of the external trust catalogue used. |
| `created_at` | UTC timestamp (or `None` when constructed without a clock). |

Convenience API: `axis_count` (always four). `to_dict()` renders a fully
JSON-serializable payload in a **fixed** key order (plus `axis_count`);
`to_json()` renders a **canonical** serialization (see
[Deterministic serialization](#deterministic-serialization)).

## The external trust catalogue

The engine's scoring policy lives **outside the code** in `trust/data/rules.yaml`
— a versioned catalogue that is **policy, not logic**, so *how much each sub-axis
weighs and the score thresholds that map onto each trust level* can be reviewed,
tuned or corrected without touching or redeploying the engine.

Top-level keys:

| Key | Meaning |
|---|---|
| `version` | Semantic version string, stamped onto every produced report as its `rules_version`. |
| `weights` | Mapping of canonical axis name → non-negative blend weight. All four axes must be weighted exactly once. |
| `levels` | List of `{ level, min_score }` — each trust level's inclusive score floor. |

The shipped catalogue weights the four axes `identity_confidence: 0.30`,
`evidence_consistency: 0.25`, `decision_confidence: 0.20`,
`integrity_confidence: 0.25` (sum `1.0`), and declares the four levels with
floors `high ≥ 0.75`, `medium ≥ 0.50`, `low ≥ 0.25`, `untrusted ≥ 0.0`. It holds
**no projection logic** — only the blend weights and the thresholds.

## Catalogue loader

`trust/rules.py` turns the catalogue file into validated, immutable value objects,
and owns the **fixed vocabulary** the catalogue is validated against:

- **`CANONICAL_AXES`** — the four legal axis names (a `frozenset`), the single
  source of truth shared by the loader and the engine.
- **`AxisWeight`** — one axis's non-negative blend weight.
- **`TrustLevelRule`** — one level's inclusive `[0, 1]` score floor.
- **`TrustRuleSet`** — the whole loaded catalogue: its `version`, the per-axis
  weights (in canonical order) and the levels (sorted by descending floor).
  Convenience API: `axis_names`, `total_weight`, `level_count`,
  `weight_for(axis)` and `level_for(score)`.

`load_rules(path)` reads YAML (or JSON, by suffix), then **validates
aggressively**, raising a typed `PassportTrustRuleError` on any structural
problem:

- file missing / unparseable / not a mapping / empty;
- missing or empty `version`;
- no `weights`, `weights` not a mapping, or an empty `weights` mapping;
- an unknown axis name, an omitted canonical axis, a non-numeric/boolean weight,
  an out-of-range weight, or an all-zero weight total;
- no `levels`, `levels` not a list, or an empty `levels` list;
- an unknown level name, a duplicate level, an omitted level, a
  non-numeric/out-of-range floor, or **no level with a `0.0` floor** (so the
  levels must cover the bottom of the range and every score resolves).

`level_for(score)` returns the first level (levels are sorted by descending floor)
whose floor the score meets or exceeds; the guaranteed `0.0` floor means every
`[0, 1]` score maps to exactly one level.

## The deterministic engine

`trust/engine.py` holds the deterministic evaluation. `evaluate(...)` has three
clean stages, and there is **no model and no new inference** — given the same four
reports and catalogue it always produces the same report (modulo the optional
timestamp):

1. **Project** each of the four upstream reports onto its normalized `[0, 1]`
   trust sub-axis (see [The four trust sub-axes](#the-four-trust-sub-axes)),
   producing a value and a human-readable reason per axis.
2. **Score** the weighted average of the four axes using the catalogue's per-axis
   blend weights: `Σ(valueᵢ × weightᵢ) / Σweightᵢ`, then clamp to `[0, 1]` and
   round to six decimal places. Because the loader guarantees a positive total
   weight, the average is always well-defined.
3. **Level** the score by mapping it through `TrustRuleSet.level_for(score)`.

The engine then composes ordered reasoning (the level/score summary, the
weighted-average note and one line per axis) and ordered warnings (a low-trust
warning when the score is at or below the configured floor, an integrity-failure
warning, an integrity-warnings note, and a note when the passport itself carried
warnings). The axes are always emitted in fixed canonical order (identity,
evidence, decision, integrity) so the report is byte-for-byte reproducible.

## The four trust sub-axes

Each axis is a transparent projection from the existing signals its input already
carries — **never a new inference**:

| Axis | Projected from | How |
|---|---|---|
| **Identity confidence** | passport identity + classification | mean of *identity completeness* (fraction of the strong fields `model`/`serial`/`imei`/`mac` present, divisor = `identity_field_count`) and *classification confidence*. |
| **Evidence consistency** | passport + knowledge + decision device types, passport conflict flag | `1.0` when all present device types agree and no conflict is flagged; `0.8` when they agree but a conflict is flagged; `0.4`/`0.2` when they disagree (no-conflict/conflict); `0.5` when no report resolved a type. |
| **Decision confidence** | knowledge + circular decision | arithmetic mean of the decision-knowledge overall confidence and the circular-decision confidence. |
| **Integrity confidence** | integrity report | `1.0` when `valid`; `1.0 − penalty×warnings` when `valid_with_warnings` (penalty = `integrity_warning_penalty`, clamped ≥ 0); `0.0` when `invalid`. |

Every projected value is clamped to `[0, 1]` and rounded to six decimal places,
matching every upstream engine's numeric convention so all engines' numbers
compare cleanly.

## Trust score and level — a transparent verdict

The engine derives **no score outside the weighted average**. The `trust_score`
is a transparent function of the four axis values and the catalogue weights, and
the `trust_level` is a transparent function of the score and the catalogue
thresholds:

```
trust_score = Σ(axisᵢ.value × axisᵢ.weight) / Σ(axisᵢ.weight)   # clamped, rounded
trust_level = first level (by descending floor) with score ≥ floor
```

An operator can re-derive both by hand from the `axes` (each carrying its value
and weight) and the catalogue thresholds. The score's separation from the level
means re-tuning the thresholds in the catalogue re-buckets devices **without**
recomputing any axis.

## Deterministic serialization

`PassportTrustReport.to_json()` renders a **canonical** JSON serialization: keys
are sorted (`sort_keys=True`), non-ASCII is preserved (`ensure_ascii=False`) and
separators are fixed, so the same report always serializes to the exact same
bytes. Because `to_dict()` is itself a pure function of the inputs, the **only**
source of variation is the optional `created_at` timestamp. Passing `indent=`
pretty-prints while staying canonical; the default emits the most compact
canonical form.

## Configuration

`TrustConfig` (frozen slotted) holds the catalogue locator, the low-trust
reporting floor and the two projection knobs the engine folds in — everything
that shapes a *trust verdict* (the axis weights and level thresholds) lives in the
external catalogue:

| Field | Default | Meaning |
|---|---|---|
| `rules_path` | `trust/data/rules.yaml` | Catalogue locator, resolved against the package root when relative. |
| `min_trust_score` | `0.4` | Score at or below which a low-trust **warning** is flagged (never changes the level). |
| `identity_field_count` | `4` | Number of strong identity fields the identity axis normalizes presence against. |
| `integrity_warning_penalty` | `0.1` | Per-warning penalty subtracted from the integrity axis (clamped ≥ 0). |

The two env-driven knobs are mapped via `TrustConfig.from_settings(settings)`:

| Env var | Field |
|---|---|
| `TRUST_RULES_PATH` | `rules_path` |
| `TRUST_MIN_SCORE` | `min_trust_score` |

The typed exceptions added for this engine are `PassportTrustError`
(`PASSPORT_TRUST_ERROR`, 500) and its loader subclass `PassportTrustRuleError`
(`PASSPORT_TRUST_RULE_ERROR`, 422).

## Testing

Three test modules under `tests/`, all offline (no images, no models; only the
external catalogue/schema/rule-sets are read from disk):

- **`test_trust_rules.py`** — the shipped catalogue's structure and invariants
  (version, all four axes weighted in canonical order with a positive total, the
  four levels sorted by descending floor with a `0.0` floor), the `level_for`
  mapping and inclusive floors, and the loader's validation on hand-written
  good/bad catalogues in `tmp_path` (missing file, empty, non-mapping root,
  missing version, missing/empty weights, unknown/missing axis, negative/all-zero
  weight, boolean weight, missing/empty levels, unknown/duplicate/missing level,
  no-`0.0`-floor, out-of-range floor, JSON parsing, unparseable YAML), plus the
  `AxisWeight`/`TrustLevelRule` value objects.
- **`test_trust_engine.py`** — the deterministic evaluation against hand-built
  reports and a hand-built catalogue, isolating each axis (identity completeness
  full/half/empty, evidence agreement/conflict/disagreement/undefined, decision
  mean, integrity valid/invalid/warnings-damped), the weighted-average score, how
  weights bias it, the level mapping, clamping/rounding, the ordered
  reasoning/warnings (low-trust, invalid-integrity, integrity-warnings,
  passport-warnings) and determinism.
- **`test_trust_service.py`** — end-to-end `assess(...)` against the **shipped**
  catalogue, with the four inputs built by actually running the recoverability,
  component, material, environmental, decision-knowledge, circular, passport and
  integrity engines over a hand-built `DeviceContext` plus a real
  `DeviceFingerprint`: a well-formed passport (a valid, normalized report with
  four ordered axes), the default catalogue load, provenance/version stamping, the
  injected clock, determinism, score stability across service instances, injected
  config / `from_settings` mapping, a raised floor flagging a low-trust warning,
  the no-monetary-field invariant, immutability and JSON round-tripping.

The three modules add **73** new tests, all passing; the module is `ruff`-,
`black`- and `isort`-clean and adds **zero** `mypy` errors.

## Integration guide

The engine is consumed **directly** (no HTTP). Orchestrating code assembles the
passport (M2.3), validates it (M2.4), and hands the four artefacts to
`TrustService.assess`:

```python
from device_ai.passport import PassportService
from device_ai.integrity import IntegrityService
from device_ai.trust import TrustService, TrustLevel

# 1. Compose & validate the passport (M2.3 + M2.4).
passport = PassportService().build(context, decision, materials, environmental, fingerprint)
integrity = IntegrityService().validate(passport)

# 2. Score its trustworthiness (M2.5). Every collaborator is injected, so the
#    service is constructible as-is or with a fixed clock / custom config /
#    pre-loaded catalogue. The external catalogue is loaded once at construction.
report = TrustService().assess(passport, integrity, knowledge, decision)

if report.trust_level is TrustLevel.UNTRUSTED:
    for warning in report.warnings:          # ordered operator cautions
        log.warning("passport %s: %s", report.passport_id, warning)

score = report.trust_score                   # normalized [0, 1] weighted average
for axis in report.axes:                     # explainable per-axis breakdown
    log.info("%s = %.3f (weight %.2f): %s", axis.name, axis.value, axis.weight, axis.reason)

payload = report.to_dict()                    # JSON-serializable verdict
canonical = report.to_json()                  # deterministic bytes
```

For **deterministic** use (tests, reproducible pipelines) construct the service
with `clock=None` (drops the timestamp, making the report a pure function of its
inputs) and/or inject a hand-built `TrustRuleSet` or a custom `TrustConfig`.

## Worked examples

### A well-identified, valid, agreeing device — high trust

A passport with all four strong identity fields, a high classification
confidence, a valid integrity report, agreeing device types across all reports
and healthy decision confidences scores every axis near `1.0`, so the weighted
average lands above `0.75` and the `trust_level` is `high`. The `warnings` list is
empty and each `TrustAxis` records its value, weight and a reason.

### An integrity-failed passport — untrusted

If the integrity report's status is `invalid`, the integrity axis is `0.0`; with a
catalogue that weights integrity meaningfully the score falls and — when integrity
dominates — the `trust_level` becomes `untrusted`. The engine does **not** raise;
it reports the low level, adds an integrity-failure warning and (below the floor)
a low-trust warning, so the caution is explicit and re-derivable.

### Disagreeing device types — evidence consistency drops

If the passport, knowledge and decision reports name **different** device types,
the evidence-consistency axis drops to `0.4` (or `0.2` when fusion also flagged a
conflict), pulling the score down proportionally to that axis's weight. The
axis's `reason` names the disagreeing types, so an operator sees exactly why the
score moved.

## Backward compatibility

M2.5 is **purely additive** and **internal-only**:

- **No endpoint, no router, no schema change.** `application.py` and the
  `/predict` request/response contract are untouched; the only new symbols are the
  `trust/` package, two `Settings` fields and two typed exceptions.
- **No change to any upstream engine.** The engine consumes the existing public
  surface of the four M2.1–M2.4 reports and adds nothing to them.
- **External catalogue.** The scoring policy is data in `trust/data/rules.yaml`,
  versioned independently of the code.

## Design rationale

- **A scorer, not an inference.** The engine's job is to grade the
  trustworthiness of a verdict the pipeline already produced. Making it a **pure
  scorer** — projecting existing signals, blending them by catalogue weight and
  thresholding — keeps the verdict faithful and lets an operator re-derive it by
  hand from the axes and thresholds.
- **Report, don't raise, on low trust.** A low-trust set of inputs is the
  engine's *input*, so it is reported as a low level and ordered warnings — never a
  crash. Only a malformed *catalogue* (an engine fault) raises. This asymmetry is
  deliberate and mirrors the M2.4 checker.
- **Policy is data, not logic.** *How much each axis weighs and where the level
  thresholds sit* is policy that gets tuned; keeping it in an external, versioned,
  strictly-validated catalogue lets the policy evolve independently and fail
  loudly on a malformed file.
- **Explainable by construction.** Retaining the four axes — each with its value,
  weight and reason — plus ordered reasoning means the score is never a black box;
  the same report shows both *what* the verdict is and *why*.
- **Deterministic and injectable.** Like every engine before it, the evaluation
  is a pure function and every collaborator is constructor-injected with a
  sensible default, so production wires nothing while tests inject a catalogue,
  clock or config at will.
