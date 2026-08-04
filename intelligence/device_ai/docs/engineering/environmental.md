# Environmental Intelligence Engine (M1.11)

> The fourth **downstream consumer** of the Device Intelligence Engine: an
> internal-only, **deterministic inference engine** that turns the immutable
> `DeviceContext` produced by the **fusion engine** (M1.7), the
> `RecoverabilityReport` produced by the **recoverability engine** (M1.8), the
> `ComponentReport` produced by the **component engine** (M1.9) and the
> `MaterialReport` produced by the **material engine** (M1.10) into an
> explainable **`EnvironmentalImpactReport`** — the **avoided environmental
> burden** of recovering the device rather than sending it to landfill: **carbon
> saved**, **energy saved**, **water saved**, **landfill diversion**, **critical
> material recovery**, a **circularity index** and a **hazard-reduction score**,
> with **confidence kept on a wholly separate axis** and ordered human-readable
> reasoning and warnings. Like the material engine, its knowledge — the
> per-material-category conversion factors — lives in an **external, versioned
> YAML/JSON catalogue** so the factor library is data, not logic. It ships **no
> new endpoint** and leaves the `/predict` API contract **unchanged and
> backward-compatible**.

**Module:** `intelligence/device_ai`
**Milestone:** M1.11 — Environmental Intelligence Engine
**Status:** implemented; internal-only (no router, no HTTP surface)

---

## Table of contents

1. [Scope](#scope)
2. [Architecture](#architecture)
3. [Domain models](#domain-models)
4. [The external factor catalogue](#the-external-factor-catalogue)
5. [Factor library & loader](#factor-library--loader)
6. [Inference engine](#inference-engine)
7. [The seven metrics](#the-seven-metrics)
8. [Confidence — a separate axis](#confidence--a-separate-axis)
9. [Configuration](#configuration)
10. [Testing](#testing)
11. [Integration guide](#integration-guide)
12. [Worked examples](#worked-examples)
13. [Backward compatibility](#backward-compatibility)
14. [Design rationale](#design-rationale)

---

## Scope

M1.11 is the **fourth** engine to consume the fusion engine's output, and the
first to consume the material engine's. Fusion (M1.7) produces an immutable
`DeviceContext`; recoverability (M1.8) turns that into a `RecoverabilityReport`;
the component engine (M1.9) infers a `ComponentReport`; the material engine
(M1.10) estimates a `MaterialReport`; the environmental engine answers the next
question: *"given the materials this device is likely to yield and how
recoverable it is, how much environmental burden do we avoid by recovering it
rather than landfilling it — and how circular and how much less hazardous does
that make the outcome?"* Every metric the engine reports is derived from
**deterministic arithmetic** over the upstream reports and an external factor
catalogue, never from learned models:

| # | Signal | Source | Effect on the report |
|---|---|---|---|
| 1 | **Recovered material masses** | `materials.materials` (the M1.10 `MaterialReport`) | Each recoverable material's **nominal mass** (grams), grouped by `MaterialCategory`, is the base quantity every resource-savings metric is computed from. |
| 2 | **Conversion factors** | external `factors.yaml` catalogue | Per-kilogram **carbon/energy/water** factors turn recovered mass into an avoided burden; the `critical` flag marks the categories that count toward critical-material recovery. |
| 3 | **Recoverability recyclability & hazard** | `recoverability.recyclability` / `.hazard_level` | The recyclability score shapes the **circularity index**; the hazard severity shapes the **hazard-reduction score**. |
| 4 | **Upstream confidences** | `materials.overall_confidence` / `recoverability.confidence` | Blended into a single **separate** confidence axis that **never scales a metric**. |

**Explicitly in scope**

- `EnvironmentalImpactReport` — the normalized, immutable estimate with the seven
  headline metrics, a per-material-category contribution breakdown, a separate
  confidence and ordered reasoning/warnings.
- An **external, versioned** conversion-factor catalogue (YAML/JSON) with a strict
  loader that validates aggressively and fails with a typed error.
- A pure `EnvironmentalInferenceEngine` fold (recovered mass → per-category
  aggregation → per-kilogram conversion → landfill/critical quantities →
  circularity and hazard-reduction indices → a separately-blended confidence).
- An injected `EnvironmentalService` orchestration facade.

**Explicitly out of scope** (do **not** implement in M1.11): blockchain
anchoring, the Digital Device Passport, the Decision/Recommendation engine,
carbon-credit issuance and any external sustainability API. The engine is
**internal only** — no router is mounted, `application.py` is untouched, and the
`/predict` response schema is **unchanged**.

**Key input constraint.** The environmental engine consumes only the **public,
aggregate surfaces** of the four upstream reports: `context.eco_id`,
`recoverability.recyclability` / `.hazard_level` / `.confidence`, the
`components` report (for provenance) and the `materials` report's recoverable
materials and mass totals. It never re-derives a material breakdown from raw
images, models or identity fields — the upstream reports and the factor
catalogue **only**.

## Architecture

The engine is a **pure domain layer** with the same shape as `fusion/`,
`recoverability/`, `components/` and `materials/`: frozen slotted dataclasses,
stateless engines, and an injected service. It imports the fusion
`DeviceContext`, the recoverability `RecoverabilityReport`, the component
`ComponentReport`, the material `MaterialReport` and the settings `Settings`
**only under `TYPE_CHECKING`**, so there is no runtime coupling and no import
cycle — all four upstream reports are passed in, never reached into past their
public surface. The two runtime dependencies it does take are the `HazardLevel`
enum (to weight and phrase the hazard signal) and the `MaterialCategory` enum
(the vocabulary the catalogue's factors are keyed and validated against — the
cross-engine link).

```
       fusion engine (M1.7) ─► DeviceContext ────────────────┐
                                                             │
   recoverability engine (M1.8) ─► RecoverabilityReport ─────┤
                                                             │
        component engine (M1.9) ─► ComponentReport ──────────┤
                                                             │
         material engine (M1.10) ─► MaterialReport ──────────┤
                                                             │
        ┌──────────── environmental/ (internal) ─────────────▼─────────────┐
        │  service.py  EnvironmentalService.analyze(ctx, recov, comps, mat) │
        │        │            │              │                              │
        │        ▼            ▼              ▼                              │
        │  factors.py     inference.py   config.py                        │
        │  load_library   Environmental  EnvironmentalConfig              │
        │  factor_for     InferenceEngine (weights + locator)             │
        │  (external      (mass × per-kg factors,                         │
        │   YAML/JSON,    per-category aggregation,                       │
        │   validated)    landfill/critical quantities,                   │
        │                 circularity + hazard indices,                   │
        │                 separately-blended confidence)                  │
        │        └────────────┬─────────────┘                             │
        │                     ▼                                           │
        │   models.py  EnvironmentalImpactReport (frozen)                 │
        │   MaterialContribution                                          │
        └──────────────────────────────────────────────────────────────────┘
                                ▼
       downstream (M1.12+ passport/decision/reporting) — never /predict
```

Layering (dependencies point downward, never upward):

```
fusion/ · recoverability/ · components/ · materials/   (M1.7–M1.10 — produce the immutable inputs)
   ↓  (TYPE_CHECKING only; all four reports are passed in)
environmental/  (models.py + factors.py + config.py + inference.py + service.py)
   ↓
exceptions · configs   (cross-cutting foundations)
```

The package contains **no HTTP imports, no FastAPI, and its only I/O is reading
the catalogue file once at service construction.** After that, `analyze()` is a
pure function of its inputs except for the injected clock (which defaults to UTC
`now` and can be replaced or disabled for determinism).

## Domain models

`environmental/models.py` defines the vocabulary that makes an impact estimate
auditable.

### `MaterialContribution`

One material category's contribution to the resource-savings metrics — a frozen
slotted dataclass:

| Field | Type | Meaning |
|---|---|---|
| `category` | `MaterialCategory` | The category this contribution aggregates. |
| `recovered_mass_g` | `float` | Recovered mass (grams) of this category. |
| `carbon_saved_kg` | `float` | Carbon avoided (kg CO₂e) by recovering this mass. |
| `energy_saved_mj` | `float` | Primary energy avoided (MJ). |
| `water_saved_l` | `float` | Freshwater avoided (litres). |
| `critical` | `bool` | Whether this category counts as critical-material recovery. |
| `reason` | `str` | How the contribution was derived (mass × factors). |

The report's carbon/energy/water totals are **exactly the sum** of the
contributions' fields, which is what makes those headline numbers explainable
rather than a black box.

### `EnvironmentalImpactReport`

The normalized, immutable outcome — a frozen slotted dataclass. Its seven
headline metrics fall on **two axes the engine keeps strictly apart** (plus
confidence as a third):

| Field | Axis | Meaning |
|---|---|---|
| `carbon_saved_kg` | physical (never clamped) | Total carbon avoided (kg CO₂e). |
| `energy_saved_mj` | physical | Total primary energy avoided (MJ). |
| `water_saved_l` | physical | Total freshwater avoided (litres). |
| `landfill_diversion_kg` | physical | Recoverable mass (kg) diverted from landfill. |
| `critical_material_recovery_kg` | physical | Recovered mass (kg) of the critical categories. |
| `circularity_index` | unit `[0, 1]` | How circular the recovery is (mass fraction × recyclability). |
| `hazard_reduction_score` | unit `[0, 1]` | How much hazard correct handling removes. |
| `confidence` | **separate** `[0, 1]` | Aggregate confidence; **never scales a metric**. |

Plus `contributions` (the ordered breakdown), `reasoning`/`warnings`, and
provenance (`device_type`, `eco_id`, `engine_version`, `factors_version`,
`created_at`). Convenience properties: `contribution_count`,
`total_recovered_mass_g`, `critical_contributions`. `to_dict()` renders a fully
JSON-serializable payload (enum → wire value, timestamp → ISO-8601 or `None`).

## The external factor catalogue

The engine's knowledge lives **outside the code** in
`environmental/data/factors.yaml` — a versioned catalogue that is **data, not
logic**, so it can be reviewed, extended or corrected as life-cycle-assessment
(LCA) sources improve, without touching or redeploying the engine.

Top-level keys:

| Key | Meaning |
|---|---|
| `version` | Semantic version string, stamped onto every produced report. |
| `default` | **Required** conservative fallback factor for any category the catalogue does not name (so a newly added `MaterialCategory` never crashes the engine). |
| `factors` | `MaterialCategory` wire value → conversion factor (≥ 1 entry). |

Each factor entry:

| Field | Required | Meaning |
|---|---|---|
| `carbon_kg_per_kg` | ✔ | Kilograms of CO₂e avoided per kilogram recovered (≥ 0). |
| `energy_mj_per_kg` | ✔ | Megajoules of primary energy avoided per kilogram (≥ 0). |
| `water_l_per_kg` | ✔ | Litres of freshwater avoided per kilogram (≥ 0). |
| `critical` | — | Whether the category counts toward critical-material recovery (default `false`). |
| `notes` | — | Optional rationale/source (provenance; not scored). |

The shipped catalogue defines a factor for **every** `MaterialCategory` and
flags `precious_metal`, `critical_material` and `rare_earth` as `critical`. Its
figures are **order-of-magnitude aggregates** drawn from published
secondary-vs-primary-production LCA literature and are intentionally
conservative — they are meant to be refined against a citable source before any
external reporting.

## Factor library & loader

`environmental/factors.py` turns the catalogue file into validated, immutable
value objects:

- **`MaterialFactor`** — the per-kilogram avoided burden of one category
  (carbon/energy/water) plus its `critical` flag.
- **`FactorLibrary`** — the whole loaded catalogue: `version`, the per-category
  `factors` dict and the `default` fallback. `factor_for(category)` resolves a
  category to a factor, **never failing**: an unnamed category resolves to the
  `default`, re-stamped with the requested category.

`load_library(path)` reads YAML (or JSON, by suffix), then **validates
aggressively**, raising a typed `EnvironmentalFactorError` on any structural
problem:

- file missing / unparseable / not a mapping / empty;
- missing or empty `version`;
- no `factors`, or an unknown `MaterialCategory` key;
- any of the three numeric factors missing, non-numeric, boolean, or negative;
- missing `default` fallback.

Because the loader fails loudly on a bad catalogue, a malformed factor file
**never silently degrades** the engine.

## Inference engine

`environmental/inference.py` holds the deterministic fold. `infer(...)` performs
the following, in order:

1. **Aggregate by category.** Walk the material report's materials; keep only
   those flagged `recoverable` whose own `confidence` clears the configured
   floor (`min_material_confidence`); group them by `MaterialCategory`, summing
   nominal masses. Ordering follows first appearance, so the breakdown is stable.
2. **Convert mass → savings.** For each category, `factor_for(category)` supplies
   the per-kilogram factors; `carbon = mass_kg × carbon_kg_per_kg` (and likewise
   energy, water). Sum the contributions into the headline totals.
3. **Landfill diversion.** `materials.recoverable_mass_g / 1000` — the recoverable
   mass, in kilograms, diverted from landfill.
4. **Critical-material recovery.** Sum the recovered mass (kg) of the
   contributions whose factor is flagged `critical`.
5. **Circularity index.** Blend the recoverable **mass fraction**
   (`recoverable_mass_g / total_mass_g`) with `recoverability.recyclability`,
   weighted by `circularity_recyclability_weight`; clamp to `[0, 1]`.
6. **Hazard-reduction score.** Map `recoverability.hazard_level` to a severity in
   `[0, 1]`, then scale it by how much hazardous mass is present to divert
   (weighted by `hazard_diversion_weight`); clamp to `[0, 1]`. A device with no
   assessed hazard yields **0** — there is nothing to reduce.
7. **Confidence.** Blend `materials.overall_confidence` with
   `recoverability.confidence` (see below); clamp to `[0, 1]`.
8. **Explain.** Assemble ordered reasoning and operator warnings (empty
   breakdown, all-below-floor, assessed hazard, unresolved device type).

There is **no model and no I/O** here — given the same inputs the engine always
produces the same `EnvironmentalImpactReport`.

## The seven metrics

The engine keeps three axes strictly separate, which is the core design
invariant:

- **Physical quantities** — `carbon_saved_kg`, `energy_saved_mj`, `water_saved_l`,
  `landfill_diversion_kg`, `critical_material_recovery_kg` are **real amounts**.
  They are rounded to 3 decimals but **never clamped** to a unit interval: a
  precious-metal recovery legitimately yields a carbon figure far above 1.0, and
  clamping it like a probability would be a category error.
- **Unit indices** — `circularity_index` and `hazard_reduction_score` are
  composite `[0, 1]` measures of *how circular* / *how much hazard was removed*,
  independent of the absolute masses. They are clamped and rounded to 6 decimals.
- **Confidence** — a single separate `[0, 1]` axis (below).

Rounding precisions (`_METRIC_PRECISION = 3`, `_SCORE_PRECISION = 6`) match the
fusion, recoverability, component and material engines so every engine's numbers
compare cleanly.

## Confidence — a separate axis

`confidence` blends the two upstream report confidences:

```
confidence = materials.overall_confidence × (1 − w)
           + recoverability.confidence     × w        (w = recoverability_confidence_weight)
```

Crucially, the engine applies **no separate unknown-type or conflict damping** of
its own. The consumed `materials.overall_confidence` **already folds in**
device-type familiarity and fusion conflicts (the material engine damped for
both), so re-damping here would **double-count** the same signals. This keeps the
"how much was saved" and "how sure are we" questions fully separable — halving
both upstream confidences leaves every physical metric byte-for-byte unchanged
while lowering only `confidence`.

## Configuration

`EnvironmentalConfig` (frozen slotted) holds the catalogue locator and the
tunable weights, so every number that shapes a report is named in one immutable
object:

| Field | Default | Meaning |
|---|---|---|
| `factors_path` | `environmental/data/factors.yaml` | Catalogue locator, resolved against the package root when relative. |
| `min_material_confidence` | `0.05` | Confidence at or below which a recovered material is ignored. |
| `recoverability_confidence_weight` | `0.50` | Weight of the recoverability confidence in the blend. |
| `circularity_recyclability_weight` | `0.50` | Weight of recyclability in the circularity index. |
| `hazard_diversion_weight` | `0.50` | Weight of the hazardous-mass fraction in the hazard-reduction score. |

Two knobs are **env-driven** via `EnvironmentalConfig.from_settings(settings)`:

| Env var | Field |
|---|---|
| `ENVIRONMENTAL_FACTORS_PATH` | `factors_path` |
| `ENVIRONMENTAL_MIN_CONFIDENCE` | `min_material_confidence` |

The rest keep code-level defaults, still overridable directly in a constructed
config. The typed exceptions added for this engine are `EnvironmentalError`
(`ENVIRONMENTAL_ERROR`, 500) and its loader subclass `EnvironmentalFactorError`
(`ENVIRONMENTAL_FACTOR_ERROR`, 422).

## Testing

Three test modules under `tests/`, all offline (no images, no models; only the
external catalogues are read from disk):

- **`test_environmental_factors.py`** — the shipped catalogue's structure and
  invariants (non-negative factors, every category covered, critical categories
  flagged, precious metal the largest carbon factor), `factor_for` fallback, and
  the loader's validation on hand-written good/bad catalogues in `tmp_path`
  (missing file, malformed YAML, missing version, unknown category, negative /
  non-numeric / boolean / missing factor, empty factors, missing default), JSON
  parity, and `from_settings` mapping.
- **`test_environmental_inference.py`** — the deterministic fold against a small
  hand-built factor library and hand-built reports: mass→savings conversion,
  linear scaling, no-clamping of physical metrics, per-category aggregation,
  default-factor fallback, recoverable/floor filtering, landfill and critical
  quantities, the circularity and hazard-reduction indices, the separate
  confidence blend (and that it never scales a metric), reasoning/warnings,
  determinism, and every `HazardLevel`.
- **`test_environmental_service.py`** — end-to-end `analyze(...)` against the
  **shipped** catalogue, with upstream inputs built by actually running the
  recoverability, component and material engines over a hand-built
  `DeviceContext`: an identifiable laptop, a hazardous CRT, an unknown device and
  a conflicted context, plus determinism, provenance/version stamping, the
  injected clock, the JSON shape and report immutability.

The full suite (**716 tests**, of which **59** are new here) passes; the module
is `ruff`-, `black`- and `isort`-clean and adds **zero** `mypy` errors.

## Integration guide

The engine is consumed **directly** (no HTTP). Orchestrating code runs the four
upstream engines and hands their reports to `EnvironmentalService.analyze`:

```python
from device_ai.fusion import FusionService
from device_ai.recoverability import RecoverabilityService
from device_ai.components import ComponentService
from device_ai.materials import MaterialService
from device_ai.environmental import EnvironmentalService

# 1. Fuse the perception engines into an immutable context (M1.7).
context = FusionService().fuse(evidence)

# 2. Assess recoverability (M1.8), infer components (M1.9), estimate materials (M1.10).
recoverability = RecoverabilityService().assess(context)
components = ComponentService().analyze(context, recoverability)
materials = MaterialService().analyze(context, recoverability, components)

# 3. Estimate the avoided environmental burden (M1.11). Every collaborator is
#    injected, so the service is constructible as-is or with a fixed clock /
#    custom config / pre-loaded library. The external catalogue is loaded once at
#    construction.
impact = EnvironmentalService().analyze(context, recoverability, components, materials)

payload = impact.to_dict()   # JSON-serializable; feed passport/reporting (M1.12+)
```

For **deterministic** use (tests, reproducible pipelines) construct the service
with `clock=None` (drops the timestamp) and/or inject a hand-built
`FactorLibrary` or a custom `EnvironmentalConfig`.

## Worked examples

### Identifiable laptop — full savings, critical recovery

A confident laptop yields recoverable ferrous/non-ferrous metals, board
materials (precious/critical metals) and battery material. The engine reports
positive `carbon_saved_kg` / `energy_saved_mj` / `water_saved_l`, a positive
`landfill_diversion_kg`, a **positive `critical_material_recovery_kg`** (the
boards' precious metals), a healthy `circularity_index`, and a confidence
blended from the high material and recoverability confidences.

### CRT monitor — hazard reduction surfaced

A CRT's leaded glass and phosphors drive a `HIGH` hazard upstream, so the
engine's `hazard_reduction_score` is well above zero and a warning notes the
score is only realized if the hazardous stream is handled correctly.

### Unknown device — generic estimate, damped confidence

An unrecognized type falls back upstream to a generic material breakdown at
damped confidence; the environmental engine still produces resource savings from
the generic structural materials, but its **confidence is lower** than a known
device's — inherited from the upstream damping, not re-applied here.

## Backward compatibility

M1.11 is **purely additive** and **internal-only**:

- **No endpoint, no router, no schema change.** `application.py` and the
  `/predict` request/response contract are untouched; the only new symbols are
  the `environmental/` package, two `Settings` fields and two typed exceptions.
- **No change to any upstream engine.** The engine consumes the existing public
  surfaces of the M1.7–M1.10 reports and adds nothing to them.
- **External catalogue.** All environmental knowledge is data in
  `environmental/data/factors.yaml`, versioned independently of the code.

## Design rationale

- **Data, not logic.** Conversion factors are LCA data that improve over time;
  keeping them in an external, versioned, strictly-validated catalogue lets them
  be corrected without redeploying — and a malformed catalogue fails loudly
  rather than silently degrading the estimate.
- **Three axes, kept apart.** Physical quantities are never clamped, indices are
  normalized `[0, 1]`, and confidence is a third, independent axis that never
  scales a metric. This is what lets an operator trust "how much was saved" and
  "how sure are we" as separate answers.
- **No double-counting.** Because the material report's confidence already
  encodes device-type familiarity and fusion conflicts, the environmental engine
  blends rather than re-damps — the same signal is applied exactly once.
- **Deterministic and injectable.** Like every engine before it, the fold is a
  pure function and every collaborator is constructor-injected with a sensible
  default, so production wires nothing while tests inject a library, clock or
  config at will.
