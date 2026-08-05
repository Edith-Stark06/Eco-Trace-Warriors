# Decision Knowledge Engine (M2.1)

> The fifth **downstream consumer** of the Device Intelligence Engine and the
> first engine of milestone **M2** — an internal-only, **deterministic inference
> engine** that turns the immutable `DeviceContext` produced by the **fusion
> engine** (M1.7), the `RecoverabilityReport` produced by the **recoverability
> engine** (M1.8), the `ComponentReport` produced by the **component engine**
> (M1.9), the `MaterialReport` produced by the **material engine** (M1.10) and
> the `EnvironmentalImpactReport` produced by the **environmental engine** (M1.11)
> into a single, normalized **`DecisionKnowledgeReport`** — six comparable
> `[0, 1]` **decision dimensions** (repairability, reusability, recycling,
> hazard, environmental priority and material value), each a **transparent
> weighted mean** of upstream signals, plus a **separate overall-confidence
> axis**, an auditable **per-dimension evidence breakdown** and ordered
> human-readable reasoning and warnings. Like the material and environmental
> engines, its knowledge — the per-dimension **signal weights** and the
> normalization constants — lives in an **external, versioned YAML/JSON
> catalogue** so the weighting is data, not logic. It ships **no new endpoint**
> and leaves the `/predict` API contract **unchanged and backward-compatible**.

**Module:** `intelligence/device_ai`
**Milestone:** M2.1 — Decision Knowledge Engine
**Status:** implemented; internal-only (no router, no HTTP surface)

---

## Table of contents

1. [Scope](#scope)
2. [Architecture](#architecture)
3. [Domain models](#domain-models)
4. [The external knowledge catalogue](#the-external-knowledge-catalogue)
5. [Knowledge base & loader](#knowledge-base--loader)
6. [Inference engine](#inference-engine)
7. [The six dimensions & eleven signals](#the-six-dimensions--eleven-signals)
8. [Confidence — a separate axis](#confidence--a-separate-axis)
9. [Configuration](#configuration)
10. [Testing](#testing)
11. [Integration guide](#integration-guide)
12. [Worked examples](#worked-examples)
13. [Backward compatibility](#backward-compatibility)
14. [Design rationale](#design-rationale)

---

## Scope

M2.1 is the **fifth** engine to consume the fusion engine's output, and the
first to consume all four downstream reports at once. Fusion (M1.7) produces an
immutable `DeviceContext`; recoverability (M1.8) turns that into a
`RecoverabilityReport`; the component engine (M1.9) infers a `ComponentReport`;
the material engine (M1.10) estimates a `MaterialReport`; the environmental
engine (M1.11) computes an `EnvironmentalImpactReport`; the decision knowledge
engine answers the next question: *"taken together, how strongly does each
decision dimension weigh for this device, on one comparable scale?"* It
consolidates what the upstream engines already found into a single, explainable
surface so that a **later** decision layer (out of scope here) has one clean
input. Every number the engine reports is derived from **deterministic
arithmetic** over the upstream reports and an external catalogue, never from
learned models:

| # | Signal source | Source report | Effect on the report |
|---|---|---|---|
| 1 | **Recoverability scores** | `recoverability.repairability` / `.reusability` / `.recyclability` / `.hazard_level` / `.confidence` | Pass-through `[0, 1]` scores dominate the repairability, reusability, recycling and hazard dimensions; hazard severity is mapped from the level. |
| 2 | **Material masses** | `materials.total_mass_g` / `.recoverable_mass_g` / `.hazardous_mass_g` / `.overall_confidence` | Recoverable and hazardous **mass fractions** feed the recycling, hazard and material-value dimensions. |
| 3 | **Environmental amounts** | `environmental.carbon_saved_kg` / `.energy_saved_mj` / `.water_saved_l` / `.critical_material_recovery_kg` / `.circularity_index` / `.hazard_reduction_score` / `.confidence` | Unbounded physical amounts are **saturated** to `[0, 1]`; the two indices pass through. They feed the recycling, hazard, environmental-priority and material-value dimensions. |
| 4 | **Fusion identity & confidence** | `context.model` / `.serial` / `.imei` / `.mac` / `.confidence` | Strong-identity presence gives an **identity-completeness** signal; the fusion confidence joins the separate confidence blend. |

**Explicitly in scope**

- `DecisionKnowledgeReport` — the normalized, immutable evidence with the six
  dimension scores, a per-dimension evidence breakdown, a **separate** overall
  confidence and ordered reasoning/warnings.
- An **external, versioned** knowledge catalogue (YAML/JSON) with a strict loader
  that validates aggressively and fails with a typed error.
- A pure `DecisionInferenceEngine` fold (upstream reports → eleven normalized
  signals → per-dimension weighted means → a separately-blended confidence).
- An injected `DecisionService` orchestration facade.

**Explicitly out of scope** (do **not** implement in M2.1): the **final decision
recommendation** (which action to take), **economic/monetary valuation**,
**optimization**, blockchain anchoring, the Digital Device Passport, the
marketplace and carbon-credit issuance. The report is **normalized evidence
only** — the "material value" dimension is a unit index, **not** a currency
amount, and no dimension is a recommended action. The engine is **internal
only** — no router is mounted, `application.py` is untouched, and the `/predict`
response schema is **unchanged**.

**Key input constraint.** The decision engine consumes only the **public,
aggregate surfaces** of the five upstream reports: the scores, hazard level,
mass totals, environmental amounts, identity attributes and confidences. It
never re-derives anything from raw images, models or per-material rows — the
upstream reports and the knowledge catalogue **only**.

## Architecture

The engine is a **pure domain layer** with the same shape as `fusion/`,
`recoverability/`, `components/`, `materials/` and `environmental/`: frozen
slotted dataclasses, stateless engines, and an injected service. It imports the
five upstream report types and the settings `Settings` **only under
`TYPE_CHECKING`**, so there is no runtime coupling and no import cycle — all five
reports are passed in, never reached into past their public surface. The two
runtime dependencies it does take are the `HazardLevel` enum (to map the hazard
signal) and the `FusionAttribute` enum (to read identity attributes) — enums
only, matching the environmental engine's runtime import of `HazardLevel`.

```
       fusion engine (M1.7) ─► DeviceContext ─────────────────────┐
                                                                  │
   recoverability engine (M1.8) ─► RecoverabilityReport ──────────┤
                                                                  │
        component engine (M1.9) ─► ComponentReport ───────────────┤
                                                                  │
         material engine (M1.10) ─► MaterialReport ───────────────┤
                                                                  │
    environmental engine (M1.11) ─► EnvironmentalImpactReport ────┤
                                                                  │
        ┌──────────────── decision/ (internal) ───────────────────▼─────────────┐
        │  service.py  DecisionService.analyze(ctx, recov, comps, mat, env)      │
        │        │            │              │                                   │
        │        ▼            ▼              ▼                                   │
        │  knowledge.py   inference.py   config.py                             │
        │  load_knowledge Decision       DecisionConfig                        │
        │  weights_for    InferenceEngine (locator + min_confidence)           │
        │  (external      (project → 11 signals,                               │
        │   YAML/JSON,    per-dimension weighted means,                        │
        │   validated)    environmental saturation,                           │
        │                 separately-blended confidence)                       │
        │        └────────────┬─────────────┘                                  │
        │                     ▼                                                │
        │   models.py  DecisionKnowledgeReport (frozen)                        │
        │   DimensionEvidence · EvidenceSignal                                 │
        └────────────────────────────────────────────────────────────────────────┘
                                ▼
       downstream (M2.2+ decision/recommendation/passport) — never /predict
```

Layering (dependencies point downward, never upward):

```
fusion/ · recoverability/ · components/ · materials/ · environmental/   (M1.7–M1.11 — produce the immutable inputs)
   ↓  (TYPE_CHECKING only; all five reports are passed in)
decision/  (models.py + knowledge.py + config.py + inference.py + service.py)
   ↓
exceptions · configs   (cross-cutting foundations)
```

The package contains **no HTTP imports, no FastAPI, and its only I/O is reading
the catalogue file once at service construction.** After that, `analyze()` is a
pure function of its inputs except for the injected clock (which defaults to UTC
`now` and can be replaced or disabled for determinism).

## Domain models

`decision/models.py` defines the vocabulary that makes the consolidated evidence
auditable.

### `DecisionDimension`

A `str` enum of the six normalized dimensions the engine scores —
`REPAIRABILITY`, `REUSABILITY`, `RECYCLING`, `HAZARD`, `ENVIRONMENTAL_PRIORITY`,
`MATERIAL_VALUE`. Because it is a `str` enum, members serialize to their wire
value directly and can be constructed from a catalogue string; it is the
**single source of truth** the catalogue's `dimensions` block is validated
against on load. Every dimension is normalized evidence in `[0, 1]`; **none is a
recommended action** — `HAZARD` is the *amount of hazard evidence* (higher = more
hazardous), not a disposal instruction.

### `EvidenceSignal`

One normalized input signal's weighted contribution to a dimension — a frozen
slotted dataclass:

| Field | Type | Meaning |
|---|---|---|
| `name` | `str` | Canonical signal name (e.g. `"recyclability"`). |
| `value` | `float` | The normalized `[0, 1]` signal value projected from upstream. |
| `weight` | `float` | The non-negative weight this signal carries within its dimension. |

Retaining both `value` and `weight` on the report is what makes a score
explainable: an operator can see exactly which upstream evidence moved it and by
how much.

### `DimensionEvidence`

One decision dimension's normalized score together with the ordered signals it
blended and a human-readable `reason` — a frozen slotted dataclass. `score` is
the weighted average of `signals` (each `value` weighted by its `weight`).

### `DecisionKnowledgeReport`

The normalized, immutable outcome — a frozen slotted dataclass. Its six
dimension scores are all normalized `[0, 1]` measures; `overall_confidence` is a
**separate** axis and never scales a score:

| Field | Axis | Meaning |
|---|---|---|
| `repairability_score` | unit `[0, 1]` | Ease of putting the device back into service. |
| `reusability_score` | unit `[0, 1]` | Fitness for a second life as-is. |
| `recycling_score` | unit `[0, 1]` | Fitness for the material-recovery stream. |
| `hazard_score` | unit `[0, 1]` | How much hazardous handling the device demands (higher = more hazardous). |
| `environmental_priority` | unit `[0, 1]` | How much avoided burden rides on handling this device well. |
| `material_value_score` | unit `[0, 1]` | Normalized worth of the recoverable materials — a **unit index, not a monetary value**. |
| `overall_confidence` | **separate** `[0, 1]` | Aggregate confidence; **never scales a score**. |

Plus `dimensions` (the ordered per-dimension breakdown), `reasoning`/`warnings`,
and provenance (`device_type`, `eco_id`, `engine_version`, `knowledge_version`,
`created_at`). Convenience API: `dimension_count`, `score_for(dimension)`.
`to_dict()` renders a fully JSON-serializable payload (enum → wire value,
timestamp → ISO-8601 or `None`).

## The external knowledge catalogue

The engine's knowledge lives **outside the code** in
`decision/data/knowledge.yaml` — a versioned catalogue that is **data, not
logic**, so *how much each piece of upstream evidence weighs* toward each
dimension can be reviewed, tuned or corrected against real triage data without
touching or redeploying the engine.

Top-level keys:

| Key | Meaning |
|---|---|
| `version` | Semantic version string, stamped onto every produced report. |
| `normalization` | Saturation constants for the four unbounded environmental amounts (each strictly `> 0` — it is a divisor). |
| `dimensions` | `DecisionDimension` wire value → `{ signal name → weight }`. **All six dimensions required.** |
| `confidence` | Confidence source → weight, over the five sources (≥ 1 positive). |

Each dimension's weight map may name any subset of the eleven canonical signals;
every weight is `≥ 0` and at least one per dimension must be `> 0`. The shipped
catalogue's weights are **deliberate, transparent priors** — each dimension is
dominated by its most direct upstream signal, with smaller corroborating weights
— meant to be tuned against real triage data before any external reporting.

## Knowledge base & loader

`decision/knowledge.py` turns the catalogue file into validated, immutable value
objects, and owns the **fixed vocabulary** the catalogue is validated against:

- **`CANONICAL_SIGNALS`** — the eleven normalized input signals the engine
  projects from the upstream reports. The catalogue may re-weight these but may
  **not** invent new ones, so a typo in a dimension's weight map is caught at load
  time rather than silently ignored.
- **`CONFIDENCE_SOURCES`** — the five upstream confidence sources
  (`recoverability`, `components`, `materials`, `environmental`, `fusion`).
- **`Normalization`** — the four saturation constants that map the environmental
  engine's unbounded physical amounts (kg CO₂e, MJ, L, kg recovered) onto a
  `[0, 1]` signal so they can be blended with the already-normalized scores.
- **`KnowledgeBase`** — the whole loaded catalogue: `version`, the per-dimension
  `signal → weight` maps, the `confidence source → weight` map and the
  normalization constants. `weights_for(dimension)` returns a dimension's map.

`load_knowledge(path)` reads YAML (or JSON, by suffix), then **validates
aggressively**, raising a typed `DecisionKnowledgeError` on any structural
problem:

- file missing / unparseable / not a mapping / empty;
- missing or empty `version`;
- missing `normalization`, or any saturation constant missing, non-numeric,
  boolean, or not strictly positive;
- an unknown dimension name, or **any** of the six dimensions missing;
- an unknown signal name in a dimension, a negative or boolean weight, or an
  all-zero dimension;
- missing `confidence`, an unknown confidence source, or an all-zero confidence
  map.

Because the loader fails loudly on a bad catalogue, a malformed knowledge file
**never silently degrades** the engine.

## Inference engine

`decision/inference.py` holds the deterministic fold. `infer(...)` has three
clean stages:

1. **Project** the five upstream reports onto the eleven canonical normalized
   `[0, 1]` signals. The already-normalized upstream scores
   (`repairability`, `reusability`, `recyclability`, `circularity_index`,
   `hazard_reduction`) pass through; `hazard_severity` is mapped from
   `HazardLevel` (`NONE` 0.0, `UNKNOWN` 0.25, `LOW` 0.4, `MEDIUM` 0.7, `HIGH`
   1.0 — matching the environmental engine's ordering); the environmental
   engine's unbounded amounts (`environmental_savings` = mean of saturated
   carbon/energy/water; `critical_material_presence` = saturated critical
   recovery) are divided by the catalogue's saturation constants and clamped;
   `hazardous_mass_fraction` and `recoverable_mass_fraction` are computed from the
   material report's own totals (guarding zero total mass); `identity_completeness`
   is the fraction of the four strong identity attributes (model, serial, IMEI,
   MAC) fusion resolved.
2. **Blend** each of the six dimensions as the weighted average of its signals,
   using the per-dimension weights from the catalogue: for each dimension the
   engine walks its weights in order, records each `(signal, value, weight)` for
   auditability, and divides the weight-value sum by the total weight. Every
   dimension score is therefore a transparent weighted mean in `[0, 1]`.
3. **Aggregate confidence** on a wholly separate axis by blending the five
   upstream confidences with the catalogue's confidence weights (see below).

Finally it assembles ordered reasoning and operator warnings (elevated hazard,
empty material breakdown, low environmental confidence, unresolved device type).
There is **no model and no I/O** here — given the same inputs the engine always
produces the same `DecisionKnowledgeReport`.

## The six dimensions & eleven signals

The eleven canonical signals, and which upstream surface each is projected from:

| Signal | Source | Range |
|---|---|---|
| `repairability` | `recoverability.repairability` | `[0, 1]` pass-through |
| `reusability` | `recoverability.reusability` | `[0, 1]` pass-through |
| `recyclability` | `recoverability.recyclability` | `[0, 1]` pass-through |
| `circularity_index` | `environmental.circularity_index` | `[0, 1]` pass-through |
| `hazard_severity` | `recoverability.hazard_level` (mapped) | `[0, 1]` |
| `hazard_reduction` | `environmental.hazard_reduction_score` | `[0, 1]` pass-through |
| `hazardous_mass_fraction` | `materials.hazardous_mass_g / total_mass_g` | `[0, 1]` |
| `critical_material_presence` | `environmental.critical_material_recovery_kg` (saturated) | `[0, 1]` |
| `recoverable_mass_fraction` | `materials.recoverable_mass_g / total_mass_g` | `[0, 1]` |
| `environmental_savings` | mean of saturated carbon/energy/water | `[0, 1]` |
| `identity_completeness` | fused model/serial/IMEI/MAC presence | `[0, 1]` |

The shipped catalogue's per-dimension priors (each dominated by its most direct
signal):

| Dimension | Dominant signal(s) | Corroborating |
|---|---|---|
| `repairability` | `repairability` (0.80) | `identity_completeness` (0.20) |
| `reusability` | `reusability` (0.80) | `identity_completeness` (0.20) |
| `recycling` | `recyclability` (0.55) | `circularity_index` (0.25), `recoverable_mass_fraction` (0.20) |
| `hazard` | `hazard_severity` (0.60) | `hazardous_mass_fraction` (0.25), `hazard_reduction` (0.15) |
| `environmental_priority` | `environmental_savings` (0.45) | `circularity_index` (0.25), `critical_material_presence` (0.30) |
| `material_value` | `critical_material_presence` (0.50) | `recoverable_mass_fraction` (0.25), `environmental_savings` (0.25) |

Scores are clamped to `[0, 1]` and rounded to 6 decimals (`_SCORE_PRECISION`),
matching the fusion, recoverability, component, material and environmental
engines so every engine's numbers compare cleanly.

## Confidence — a separate axis

`overall_confidence` blends the five upstream confidences
(`recoverability.confidence`, `components.overall_confidence`,
`materials.overall_confidence`, `environmental.confidence`,
`context.confidence`) with the catalogue's confidence weights:

```
overall_confidence = Σ (confidenceₛ × weightₛ) / Σ weightₛ
                     over sources s whose weight > 0 and confidence > floor
```

A source whose confidence is **at or below** the configured floor
(`min_confidence`) is **dropped** from the blend entirely — its weight removed —
so a genuinely absent upstream signal neither anchors nor inflates the result.
When every source is below the floor the confidence is `0`.

Crucially, the engine applies **no separate unknown-type or conflict damping** of
its own. Every consumed upstream confidence **already folds in** device-type
familiarity and fusion conflicts, so re-damping here would **double-count** the
same signals. This keeps the "how strong is the evidence" and "how sure are we"
questions fully separable — halving every upstream confidence leaves every
dimension score byte-for-byte unchanged while lowering only `overall_confidence`.

## Configuration

`DecisionConfig` (frozen slotted) holds the catalogue locator and the one
tunable operational knob, so the config stays a thin locator plus filter —
everything that actually shapes a score lives in the external catalogue:

| Field | Default | Meaning |
|---|---|---|
| `knowledge_path` | `decision/data/knowledge.yaml` | Catalogue locator, resolved against the package root when relative. |
| `min_confidence` | `0.05` | Confidence at or below which an upstream confidence source is dropped from the blend. |

Both knobs are **env-driven** via `DecisionConfig.from_settings(settings)`:

| Env var | Field |
|---|---|
| `DECISION_KNOWLEDGE_PATH` | `knowledge_path` |
| `DECISION_MIN_CONFIDENCE` | `min_confidence` |

The typed exceptions added for this engine are `DecisionError`
(`DECISION_ERROR`, 500) and its loader subclass `DecisionKnowledgeError`
(`DECISION_KNOWLEDGE_ERROR`, 422).

## Testing

Three test modules under `tests/`, all offline (no images, no models; only the
external catalogues are read from disk):

- **`test_decision_knowledge.py`** — the shipped catalogue's structure and
  invariants (every dimension defined, only canonical signals used, a positive
  weight per dimension, strictly-positive saturation constants), `weights_for`,
  and the loader's validation on hand-written good/bad catalogues in `tmp_path`
  (missing file, malformed YAML, empty, missing version, missing normalization,
  non-positive saturation, missing / unknown dimension, unknown signal, negative
  / boolean / all-zero weight, unknown / all-zero / missing confidence), JSON
  parity, and `from_settings` mapping.
- **`test_decision_inference.py`** — the deterministic fold against a small
  hand-built knowledge base and hand-built reports: pass-through scores, the
  hazard-severity mapping (every level), environmental saturation and clamping,
  mass fractions (and zero-mass guard), identity completeness, the per-dimension
  weighted mean, the evidence breakdown, the unit-interval invariant, the
  separate confidence blend (with its floor, and that it never scales a score),
  reasoning/warnings, device-type resolution, provenance and determinism.
- **`test_decision_service.py`** — end-to-end `analyze(...)` against the
  **shipped** catalogue, with upstream inputs built by actually running the
  recoverability, component, material and environmental engines over a
  hand-built `DeviceContext`: an identifiable laptop, a hazardous CRT, an unknown
  device and a conflicted context, plus the normalized-evidence-only invariant
  (no recommendation/monetary keys), determinism, provenance/version stamping,
  the injected clock, the JSON shape, report immutability and injected
  knowledge/config.

The three modules add **71** new tests, all passing; the module is `ruff`-,
`black`- and `isort`-clean and adds **zero** `mypy` errors.

## Integration guide

The engine is consumed **directly** (no HTTP). Orchestrating code runs the five
upstream engines and hands their reports to `DecisionService.analyze`:

```python
from device_ai.fusion import FusionService
from device_ai.recoverability import RecoverabilityService
from device_ai.components import ComponentService
from device_ai.materials import MaterialService
from device_ai.environmental import EnvironmentalService
from device_ai.decision import DecisionService

# 1. Fuse the perception engines into an immutable context (M1.7).
context = FusionService().fuse(evidence)

# 2. Assess recoverability (M1.8), infer components (M1.9), estimate materials
#    (M1.10), compute environmental impact (M1.11).
recoverability = RecoverabilityService().assess(context)
components = ComponentService().analyze(context, recoverability)
materials = MaterialService().analyze(context, recoverability, components)
environmental = EnvironmentalService().analyze(
    context, recoverability, components, materials
)

# 3. Consolidate into normalized decision evidence (M2.1). Every collaborator is
#    injected, so the service is constructible as-is or with a fixed clock /
#    custom config / pre-loaded knowledge base. The external catalogue is loaded
#    once at construction.
decision = DecisionService().analyze(
    context, recoverability, components, materials, environmental
)

payload = decision.to_dict()   # JSON-serializable; feed the M2.2+ decision layer
```

For **deterministic** use (tests, reproducible pipelines) construct the service
with `clock=None` (drops the timestamp) and/or inject a hand-built
`KnowledgeBase` or a custom `DecisionConfig`.

## Worked examples

### Identifiable laptop — balanced evidence, high confidence

A confident, well-identified laptop yields healthy repairability, reusability and
recycling scores (strong pass-through recoverability scores lifted by full
identity completeness), a moderate material-value score (boards' critical metals
plus recoverable mass), a low hazard score, and a high `overall_confidence`
blended from the five strong upstream confidences.

### CRT monitor — hazard dimension elevated

A CRT's leaded glass drives a `HIGH` hazard upstream, so `hazard_score` is well
above zero and a warning notes the hazard dimension should gate any downstream
disposition. Repairability and reusability are correspondingly low.

### Unknown device — generic evidence, damped confidence

An unrecognized type falls back upstream to generic scores and a generic material
breakdown at damped confidence; the decision engine still produces the six
dimensions, but its `overall_confidence` is **lower** than a known device's —
inherited from the upstream damping, not re-applied here — and a warning notes
the device type is unresolved.

## Backward compatibility

M2.1 is **purely additive** and **internal-only**:

- **No endpoint, no router, no schema change.** `application.py` and the
  `/predict` request/response contract are untouched; the only new symbols are
  the `decision/` package, two `Settings` fields and two typed exceptions.
- **No change to any upstream engine.** The engine consumes the existing public
  surfaces of the M1.7–M1.11 reports and adds nothing to them.
- **External catalogue.** All decision knowledge is data in
  `decision/data/knowledge.yaml`, versioned independently of the code.

## Design rationale

- **Normalized evidence, not a decision.** The report deliberately stops at
  comparable `[0, 1]` evidence: no recommended action, no monetary value, no
  optimization. That boundary keeps M2.1 a clean, auditable input for the later
  decision layer rather than a black-box verdict.
- **Data, not logic.** The signal weights and normalization constants are tuning
  knowledge that improves as the upstream engines evolve; keeping them in an
  external, versioned, strictly-validated catalogue lets them be corrected
  without redeploying — and a malformed catalogue fails loudly rather than
  silently degrading the evidence.
- **Fixed vocabulary, re-weightable priors.** The eleven signals and five
  confidence sources are a closed set the catalogue validates against, so a typo
  is a load-time error; only the *weights* are data. Every dimension score is a
  transparent weighted mean an operator can reconstruct from the evidence
  breakdown.
- **Two axes, kept apart.** The six dimensions are normalized `[0, 1]` evidence;
  confidence is a second, independent axis that never scales a score. This lets
  an operator trust "how strong is the evidence" and "how sure are we" as
  separate answers.
- **No double-counting.** Because each upstream confidence already encodes
  device-type familiarity and fusion conflicts, the decision engine blends rather
  than re-damps — the same signal is applied exactly once.
- **Deterministic and injectable.** Like every engine before it, the fold is a
  pure function and every collaborator is constructor-injected with a sensible
  default, so production wires nothing while tests inject a knowledge base, clock
  or config at will.
