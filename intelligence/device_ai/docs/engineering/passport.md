# Device Passport Core (M2.3)

> The seventh **downstream consumer** of the Device Intelligence Engine and the
> third component of milestone **M2** — an internal-only, **deterministic
> assembler** that composes the reports the upstream engines already produced into
> a single, immutable **`DevicePassport`** document. It consumes the immutable
> `DeviceContext` from the **fusion engine** (M1.7), the actionable
> `DecisionReport` from the **circular decision engine** (M2.2), the
> `MaterialReport` from the **material engine** (M1.10), the
> `EnvironmentalImpactReport` from the **environmental engine** (M1.11) and the
> device's `DeviceFingerprint` (M1.5), and **composes** them into one
> self-describing snapshot — a **passport id**, the **EcoID**, the resolved
> **identity** and **classification**, a **decision**, **material**,
> **environmental**, **fingerprint** and **confidence** summary, provenance
> **metadata**, and ordered human-readable **reasoning** and **warnings**.
> Unlike M2.1 (normalized evidence) and M2.2 (an actual recommendation), the
> passport core carries **no inference of its own**: every value it holds is
> copied or plainly summarized from an upstream report. Its **structural
> contract** — which sections a passport must contain and their field/range shape —
> lives in an **external, versioned YAML/JSON schema** so the contract is data, not
> logic; a **strict validator** checks every assembled passport against it. It
> ships **no new endpoint** and leaves the `/predict` API contract **unchanged and
> backward-compatible**.

**Module:** `intelligence/device_ai`
**Milestone:** M2.3 — Device Passport Core
**Status:** implemented; internal-only (no router, no HTTP surface)

---

## Table of contents

1. [Scope](#scope)
2. [Architecture](#architecture)
3. [Domain models](#domain-models)
4. [The external passport schema](#the-external-passport-schema)
5. [Schema loader & validator](#schema-loader--validator)
6. [The deterministic builder](#the-deterministic-builder)
7. [The passport id](#the-passport-id)
8. [Confidence — a transparent composition](#confidence--a-transparent-composition)
9. [Deterministic serialization](#deterministic-serialization)
10. [Configuration](#configuration)
11. [Testing](#testing)
12. [Integration guide](#integration-guide)
13. [Worked examples](#worked-examples)
14. [Backward compatibility](#backward-compatibility)
15. [Design rationale](#design-rationale)

---

## Scope

M2.3 is the **seventh** component to consume the fusion engine's output, and the
first that produces a **document** rather than a new analysis. Fusion (M1.7)
produces an immutable `DeviceContext`; the material (M1.10) and environmental
(M1.11) engines turn that into a `MaterialReport` and an
`EnvironmentalImpactReport`; the circular decision engine (M2.2) turns the
consolidated evidence into an actionable `DecisionReport`; the fingerprint engine
(M1.5) anchors the device with a hash-backed `DeviceFingerprint`. The passport
core answers the next question: *"gather everything we know and decided about this
device into one auditable snapshot."* Every value on the passport is **copied or
plainly summarized** from one of the five inputs — never re-derived:

| # | Input | Source | Passport section it feeds |
|---|---|---|---|
| 1 | **Fused context** | `context.brand` / `.model` / `.serial_number` / `.imei` / `.mac_address` / `.device_type` / `.confidence` / `.has_conflicts` / `.eco_id` / `.source_hashes` / `.engine_version` | `device_identity`, `classification`, `eco_id`, and the identity part of the `passport_id` |
| 2 | **Circular decision** | `decision.recommended_action` / `.priority` / `.confidence` / `.winning_rule` / `.triggered_count` / `.reasoning` / `.warnings` | `decision_summary`, and the lead of the composed `reasoning` |
| 3 | **Material estimate** | `materials.material_count` / `.total_mass_g` / `.recoverable_mass_g` / `.hazardous_mass_g` / `.overall_confidence` / `.warnings` | `material_summary` |
| 4 | **Environmental impact** | `environmental.carbon_saved_kg` / `.energy_saved_mj` / `.water_saved_l` / `.landfill_diversion_kg` / `.critical_material_recovery_kg` / `.circularity_index` / `.hazard_reduction_score` / `.confidence` / `.warnings` | `environmental_summary` |
| 5 | **Fingerprint** | `fingerprint.fingerprint` / `.dimension` / `.encoder_name` / `.encoder_version` / `.metric` | `fingerprint_summary`, and the anchor part of the `passport_id` |

**Explicitly in scope**

- `DevicePassport` — the immutable, composed document with a content-addressed
  passport id, the passport/EcoID, eight summarized sections, provenance metadata
  and ordered reasoning/warnings.
- An **external, versioned** passport schema (YAML/JSON) with a strict loader that
  validates aggressively and fails with a typed error.
- A pure `PassportBuilder` composition (summarize each input → compose confidence
  → identify → narrate).
- A strict `validate_passport` guard that checks every assembled passport against
  the schema before it leaves the service.
- Deterministic JSON serialization (`to_json`) suitable for hashing, diffing or a
  future anchor.
- An injected `PassportService` orchestration facade.

**Explicitly out of scope** (do **not** implement in M2.3): **blockchain
anchoring**, **QR codes**, **CBOR** encoding, **digital signatures**,
**ownership history**, **lifecycle events**, **database persistence** and **REST
endpoints**. The passport is a **composition** of existing reports, **not** a new
inference — no field is a score the builder invented, and no field is a currency
amount. The core is **internal only** — no router is mounted, `application.py` is
untouched, and the `/predict` response schema is **unchanged**.

**Key input constraint.** The builder consumes only the **public surfaces** of
its five inputs (the resolved identity, the recommendation summary, the mass and
avoided-burden totals, the confidences, the fingerprint anchor and each report's
own reasoning/warnings). It never re-derives anything from raw images, models or
per-material rows, and it **adds no score of its own** — the only value it
composes is the arithmetic mean of four confidences the inputs already reported.

## Architecture

The core is a **pure domain layer** with the same shape as `fusion/`,
`circular/` and `environmental/`: frozen slotted dataclasses, a stateless
builder, and an injected service. It imports the five upstream report types and
the settings `Settings` **only under `TYPE_CHECKING`**, so there is no runtime
coupling and no import cycle — all five inputs are passed in, never reached into
past their public surface. The one runtime dependency it takes is the
`FusionAttribute` enum (to read the device-type confidence), plus the shared
`hash_bytes` helper it uses to content-address the passport id.

```
        fusion engine (M1.7) ─► DeviceContext ────────────────────┐
                                                                  │
     circular engine (M2.2) ─► DecisionReport ────────────────────┤
                                                                  │
      material engine (M1.10) ─► MaterialReport ───────────────────┤
                                                                  │
   environmental engine (M1.11) ─► EnvironmentalImpactReport ──────┤
                                                                  │
     fingerprint engine (M1.5) ─► DeviceFingerprint ──────────────┤
                                                                  │
      ┌──────────────── passport/ (internal) ───────────────────────▼──────────┐
      │  service.py  PassportService.build(ctx, decision, mat, env, fp)         │
      │        │            │              │                                    │
      │        ▼            ▼              ▼                                    │
      │   schema.py    builder.py     config.py                             │
      │  load_schema   PassportBuilder PassportConfig                       │
      │  PassportSchema (summarize →    (schema locator +                   │
      │  validate_      compose conf →  passport_version +                  │
      │  passport       identify →      max_reasoning/warnings)             │
      │  (external      narrate)                                            │
      │   YAML/JSON,        │                                               │
      │   validated)        ▼                                               │
      │   models.py  DevicePassport (frozen) · 8 section summaries · metadata│
      └──────────────────────────────────────────────────────────────────────┘
                                ▼
       downstream (M2.4+ blockchain / QR / reporting) — never /predict
```

Layering (dependencies point downward, never upward):

```
fusion/ · circular/ · materials/ · environmental/ · fingerprint/   (M1.5–M2.2 — produce the immutable inputs)
   ↓  (TYPE_CHECKING only; all five inputs are passed in)
passport/  (models.py + schema.py + config.py + builder.py + service.py)
   ↓
exceptions · configs · utils/hashing   (cross-cutting foundations)
```

The package contains **no HTTP imports, no FastAPI, and its only I/O is reading
the schema file once at service construction.** After that, `build()` is a pure
function of its inputs except for the injected clock (which defaults to UTC `now`
and can be replaced or disabled for determinism).

## Domain models

`passport/models.py` defines the vocabulary of the snapshot. Each is a small,
frozen, slotted section with its own `to_dict()` so the passport serializes
deterministically section by section.

### Section summaries

| Model | Fields | Copied from |
|---|---|---|
| `DeviceIdentity` | `brand`, `model`, `serial_number`, `imei`, `mac_address` | the fused context's resolved identity |
| `Classification` | `device_type`, `confidence`, `has_conflicts` | the fused device type + its confidence + conflict flag |
| `DecisionSummary` | `recommended_action`, `priority`, `confidence`, `winning_rule_id`, `triggered_count` | the circular `DecisionReport` |
| `MaterialSummary` | `material_count`, `total_mass_g`, `recoverable_mass_g`, `hazardous_mass_g`, `confidence` | the `MaterialReport` totals |
| `EnvironmentalSummary` | `carbon_saved_kg`, `energy_saved_mj`, `water_saved_l`, `landfill_diversion_kg`, `critical_material_recovery_kg`, `circularity_index`, `hazard_reduction_score`, `confidence` | the `EnvironmentalImpactReport` headline metrics |
| `FingerprintSummary` | `fingerprint`, `dimension`, `encoder_name`, `encoder_version`, `metric` | the `DeviceFingerprint` anchor + encoder provenance |
| `ConfidenceSummary` | `identity_confidence`, `decision_confidence`, `material_confidence`, `environmental_confidence`, `overall` | the four upstream confidences + their mean |
| `PassportMetadata` | `passport_engine_version`, `schema_version`, `fusion_engine_version`, `decision_engine_version`, `decision_rules_version`, `material_engine_version`, `material_profile_version`, `environmental_engine_version`, `environmental_factors_version`, `source_image_count`, `created_at` | every source engine's provenance |

### `DevicePassport`

The immutable, composed document — a frozen slotted dataclass with **thirteen**
fields, exactly the sections the external schema requires:

| Field | Meaning |
|---|---|
| `passport_id` | Deterministic content-addressed identifier (`ET-PP-XXXXXXXXXXXX`). |
| `passport_version` | Semantic version of the passport structure. |
| `eco_id` | Public EcoID carried over from the device context. |
| `device_identity` | The resolved identity fields. |
| `classification` | The resolved device type and its confidence. |
| `decision_summary` | The circular decision recommendation summary. |
| `material_summary` | The material estimate totals. |
| `environmental_summary` | The avoided-burden headline metrics. |
| `fingerprint_summary` | The hash-backed identity anchor and encoder provenance. |
| `confidence_summary` | The gathered upstream confidences and their mean. |
| `metadata` | The provenance of every source engine and the timestamp. |
| `reasoning` | Ordered, human-readable reasons composed from the inputs. |
| `warnings` | Ordered operator-facing cautions composed from the inputs. |

Convenience API: `reasoning_count`, `warning_count`. `to_dict()` renders a fully
JSON-serializable payload with the thirteen sections in a **fixed** key order;
`to_json()` renders a **canonical** serialization (see
[Deterministic serialization](#deterministic-serialization)).

## The external passport schema

The passport's structural contract lives **outside the code** in
`passport/data/schema.yaml` — a versioned schema that is **data, not logic**, so
*which sections a passport must contain, and the shape and ranges of each* can be
reviewed and versioned as the passport evolves without touching or redeploying the
builder.

Top-level keys:

| Key | Meaning |
|---|---|
| `version` | Semantic version string, stamped onto every produced passport as its `schema_version` and checked by the validator. |
| `sections` | Mapping of section name → `{ kind, [fields], [confidence_fields] }`. |

A section's `kind` is one of:

| Kind | Meaning |
|---|---|
| `string` | A plain string value (e.g. the passport id). |
| `object` | A mapping that must contain every name in its `fields` list. |
| `array` | An ordered list (e.g. reasoning, warnings). |

`confidence_fields` (object sections only) names the subset of `fields` whose
values must be numeric and within `[0, 1]`; the validator rejects anything else.
The shipped schema declares the thirteen required sections — three strings
(`passport_id`, `passport_version`, `eco_id`), eight objects (`device_identity`,
`classification`, `decision_summary`, `material_summary`, `environmental_summary`,
`fingerprint_summary`, `confidence_summary`, `metadata`) and two arrays
(`reasoning`, `warnings`) — and marks every normalized confidence
(`classification.confidence`, the three summary confidences,
`environmental_summary.circularity_index` / `.hazard_reduction_score`, and all
five `confidence_summary` fields) as a `[0, 1]` confidence field. It holds **no
scoring weights, no thresholds and no policy** — only shape and ranges.

## Schema loader & validator

`passport/schema.py` turns the schema file into validated, immutable value
objects, and owns the **fixed vocabulary** the schema is validated against:

- **`SectionKind`** — the three legal section kinds (`string`, `object`, `array`);
  a schema naming a kind outside this set is rejected.
- **`SectionSchema`** — one section's contract: its `name`, `kind`, the `fields` an
  object section must contain, and the `confidence_fields` subset that must be
  `[0, 1]`.
- **`PassportSchema`** — the whole loaded schema: its `version` and the ordered
  sections a passport must contain. Convenience API: `section_count`,
  `section_names`, `section(name)`.

`load_schema(path)` reads YAML (or JSON, by suffix), then **validates
aggressively**, raising a typed `PassportSchemaError` on any structural problem:

- file missing / unparseable / not a mapping / empty;
- missing or empty `version`;
- no `sections`, `sections` not a mapping, or an empty `sections` mapping;
- an unknown section `kind`;
- an object section with no `fields`, a null/`non-list` `fields`, or a duplicate
  field name;
- a `confidence_fields` entry not present in the section's own `fields`;
- a non-object section that nonetheless declares `fields`.

`validate_passport(payload, schema)` then checks a built passport's `to_dict()`
against the loaded schema, raising a typed `PassportValidationError` when:

- a declared section is missing;
- a `string` section is not a string, an `array` section not a list, or an
  `object` section not a mapping;
- an object section is missing one of its declared fields;
- a declared confidence field is non-numeric, boolean, or outside `[0, 1]`.

Because both halves fail loudly, a malformed schema **never silently degrades**
the builder and a malformed passport **never leaves** the service.

## The deterministic builder

`passport/builder.py` holds the deterministic composition. `build(...)` has four
clean stages, and there is **no model and no I/O** — given the same inputs it
always produces the same `DevicePassport`:

1. **Summarize** each upstream report into its passport section, copying values
   verbatim (identity, classification, decision, material, environmental,
   fingerprint). A `None` fingerprint yields an all-empty (still schema-valid)
   `fingerprint_summary`.
2. **Compose confidence** by gathering the four upstream confidences
   (`context.confidence`, `decision.confidence`, `materials.overall_confidence`,
   `environmental.confidence`) onto one axis and taking their plain arithmetic
   mean, rounded to 6 decimals — a transparent composition, **not** a new
   inference.
3. **Identify** the passport with a deterministic, content-addressed id (see
   below).
4. **Narrate** by composing the ordered reasoning and warnings: the reasoning
   leads with a passport-level summary line and then carries over the circular
   decision's own reasoning; the warnings are the de-duplicated union of the
   decision, material and environmental warnings, plus a passport-level note when
   no fingerprint anchor is present. Both are capped by the config
   (`max_reasoning` / `max_warnings`) so the document stays bounded.

The builder derives nothing an operator could not re-derive from the inputs by
hand; it exists to make that composition uniform, deterministic and validated.

## The passport id

The passport id is a **content-addressed** identifier — a stable hash of the
device's identifying evidence, carrying the human-readable `ET-PP-` prefix and a
12-character uppercase SHA-256 prefix (`ET-PP-XXXXXXXXXXXX`). It is composed from
the EcoID, the hash-backed fingerprint, the resolved device type and identity
fields (brand, model, serial, IMEI, MAC) and the recommended action, joined with
an ASCII unit-separator and hashed via the shared `hash_bytes` helper:

```
passport_id = "ET-PP-" + upper( sha256( eco_id ⋮ fingerprint ⋮ device_type ⋮ brand ⋮
                                         model ⋮ serial ⋮ imei ⋮ mac ⋮ action )[:12] )
```

Two consequences follow by construction:

- **Deterministic.** The same device and reports always yield the same id, so a
  passport rebuilt later for the same device keeps its id.
- **Timestamp-free.** The id is a pure function of the device evidence — it carries
  no `created_at`, so it is stable across assembly times and service instances.

## Confidence — a transparent composition

The passport derives **no confidence of its own**. `ConfidenceSummary` gathers the
four confidences the inputs already reported onto one axis and its `overall` is
their plain arithmetic mean:

```
overall = round( (identity_confidence + decision_confidence +
                  material_confidence + environmental_confidence) / 4, 6 )
```

This is a **transparent composition**, not an inference: an operator can
re-compute it by hand from the four component confidences, all of which are
carried on the same summary. Rounding to 6 decimals matches the fusion,
recoverability, decision, environmental and circular engines so every engine's
numbers compare cleanly.

## Deterministic serialization

`DevicePassport.to_json()` renders a **canonical** JSON serialization: keys are
sorted (`sort_keys=True`), non-ASCII is preserved (`ensure_ascii=False`) and
separators are fixed, so the same passport always serializes to the exact same
bytes — suitable for hashing, diffing or a future anchor. Because `to_dict()` is
itself a pure function of the inputs (the thirteen sections in a fixed key order),
the **only** source of variation is the optional `created_at` timestamp in the
metadata. Passing `indent=` pretty-prints while staying canonical; the default
emits the most compact canonical form. This determinism is what makes the passport
an auditable snapshot rather than a re-interpretation.

## Configuration

`PassportConfig` (frozen slotted) holds the schema locator, the passport version
and two presentation caps, so the config stays a thin locator plus version —
everything that shapes the passport's *structure* lives in the external schema:

| Field | Default | Meaning |
|---|---|---|
| `schema_path` | `passport/data/schema.yaml` | Schema locator, resolved against the package root when relative. |
| `passport_version` | `1.0.0` | Semantic version stamped onto every produced passport. |
| `max_reasoning` | `32` | Maximum composed reasoning entries kept on a passport. |
| `max_warnings` | `32` | Maximum composed warnings kept on a passport. |

The two env-driven knobs are mapped via `PassportConfig.from_settings(settings)`;
the presentation caps keep their defaults (still overridable in code):

| Env var | Field |
|---|---|
| `PASSPORT_SCHEMA_PATH` | `schema_path` |
| `PASSPORT_VERSION` | `passport_version` |

The typed exceptions added for this core are `PassportError` (`PASSPORT_ERROR`,
500), and its loader/validator subclasses `PassportSchemaError`
(`PASSPORT_SCHEMA_ERROR`, 422) and `PassportValidationError`
(`PASSPORT_VALIDATION_ERROR`, 422).

## Testing

Three test modules under `tests/`, all offline (no images, no models; only the
external schema is read from disk):

- **`test_passport_schema.py`** — the shipped schema's structure and invariants
  (13 sections, the required section names, object sections carry fields,
  confidence fields declared), and the loader's validation on hand-written
  good/bad schemas in `tmp_path` (missing file, empty, missing version, missing /
  empty sections, unknown kind, object section with null / empty fields, a
  confidence field not in the section's fields), plus the validator against
  conformant and malformed payloads (missing section, wrong string/array/object
  type, missing object field, out-of-range confidence, boolean confidence).
- **`test_passport_builder.py`** — the deterministic composition against
  hand-built inputs: identity/classification/decision/material/environmental/
  fingerprint copied verbatim, the empty-fingerprint section + warning, the
  arithmetic-mean confidence (and its unit-interval bound), the content-addressed
  passport id (prefix + fixed length, deterministic, changes with identity,
  ignores the timestamp), metadata provenance carry-over, the passport-version
  config fallback, the composed reasoning/warnings (lead line, de-duplicated
  union, config caps), deterministic JSON, the canonical/compact form, the
  no-monetary-field invariant and immutability.
- **`test_passport_service.py`** — end-to-end `build(...)` against the **shipped**
  schema, with the four report inputs built by actually running the
  recoverability, component, material, environmental, decision-knowledge and
  circular engines over a hand-built `DeviceContext`, plus a real
  `DeviceFingerprint`: an identifiable laptop, schema validation, the default
  schema load, a no-fingerprint passport, provenance/version stamping, the
  injected clock, schema-version stamping, determinism, passport-id stability
  across service instances, the confidence bound, a conflicted context, injected
  config / `from_settings` mapping, the no-monetary-field invariant and
  immutability.

The three modules add **61** new tests, all passing; the module is `ruff`-,
`black`- and `isort`-clean and adds **zero** `mypy` errors.

## Integration guide

The core is consumed **directly** (no HTTP). Orchestrating code runs the upstream
engines and hands their reports to `PassportService.build`:

```python
from device_ai.fusion import FusionService
from device_ai.recoverability import RecoverabilityService
from device_ai.components import ComponentService
from device_ai.materials import MaterialService
from device_ai.environmental import EnvironmentalService
from device_ai.decision import DecisionService
from device_ai.circular import CircularService
from device_ai.passport import PassportService

# 1. Fuse the perception engines into an immutable context (M1.7).
context = FusionService().fuse(evidence)

# 2. Assess recoverability (M1.8), infer components (M1.9), estimate materials
#    (M1.10), compute environmental impact (M1.11), recommend a circular
#    disposition (M2.2).
recoverability = RecoverabilityService().assess(context)
components = ComponentService().analyze(context, recoverability)
materials = MaterialService().analyze(context, recoverability, components)
environmental = EnvironmentalService().analyze(
    context, recoverability, components, materials
)
knowledge = DecisionService().analyze(
    context, recoverability, components, materials, environmental
)
decision = CircularService().decide(
    context, knowledge, recoverability, environmental
)

# 3. Compose the device passport (M2.3). Every collaborator is injected, so the
#    service is constructible as-is or with a fixed clock / custom config /
#    pre-loaded schema. The external schema is loaded once at construction and
#    every assembled passport is validated against it before return. The
#    fingerprint is optional (pass None when unavailable).
passport = PassportService().build(
    context, decision, materials, environmental, fingerprint
)

payload = passport.to_dict()      # JSON-serializable mapping
canonical = passport.to_json()    # deterministic bytes for hashing / a future anchor
```

For **deterministic** use (tests, reproducible pipelines) construct the service
with `clock=None` (drops the timestamp, making the passport a pure function of its
inputs) and/or inject a hand-built `PassportSchema` or a custom `PassportConfig`.

## Worked examples

### Identifiable laptop — a full passport

A confident, well-identified laptop recommended for **refurbish** by the circular
engine composes into a passport whose `device_identity` carries the resolved
brand/model/serial, whose `decision_summary` names the winning rule and the
`refurbish` / `medium` recommendation, whose `material_summary` and
`environmental_summary` carry the mass and avoided-burden totals, and whose
`confidence_summary.overall` is the mean of the four upstream confidences. The
`passport_id` is a stable hash of the EcoID, fingerprint, identity and action, and
the composed `reasoning` leads with a one-line summary before the decision's own
reasoning.

### A device with no fingerprint

When no fingerprint is available the builder emits an all-empty (still
schema-valid) `fingerprint_summary`, the `passport_id` is computed from the empty
anchor plus the remaining identity evidence, and a passport-level **warning** is
appended noting the passport carries no hash-backed identity anchor. The passport
still validates and is still deterministic.

### Rebuilding the same device later

Because the `passport_id` is timestamp-free and `to_json()` is canonical, running
`build(...)` again for the same device and reports — even on a different service
instance, even months later — yields the **same** passport id and, with the clock
disabled, byte-identical JSON. That reproducibility is what lets a downstream
layer (blockchain / QR / reporting, out of scope here) treat the passport as a
stable content-addressed snapshot.

## Backward compatibility

M2.3 is **purely additive** and **internal-only**:

- **No endpoint, no router, no schema change.** `application.py` and the
  `/predict` request/response contract are untouched; the only new symbols are the
  `passport/` package, two `Settings` fields and three typed exceptions.
- **No change to any upstream engine.** The core consumes the existing public
  surfaces of the M1.5 / M1.7 / M1.10 / M1.11 / M2.2 reports and adds nothing to
  them; it **re-uses** their vocabulary rather than redefining it.
- **External schema.** The passport's structural contract is data in
  `passport/data/schema.yaml`, versioned independently of the code.

## Design rationale

- **A composition, not an inference.** The passport's job is to gather what the
  pipeline already decided into one auditable document. Making it a **pure
  assembler** — copying or plainly summarizing every value, and deriving only a
  transparent mean and a content hash — keeps the snapshot faithful rather than a
  re-interpretation, and means an operator can re-derive every field by hand.
- **Structure is data, not logic.** *Which sections a passport must contain, and
  their field/range shape* is a contract that evolves; keeping it in an external,
  versioned, strictly-validated schema lets it be reviewed and corrected without
  redeploying — and a malformed schema or passport fails loudly rather than
  silently emitting a bad document.
- **Content-addressed identity.** A timestamp-free hash of the device's stable
  evidence gives every passport a reproducible id, so the same device always maps
  to the same passport — the property a future anchor/QR layer needs.
- **Deterministic bytes.** Canonical JSON (sorted keys, fixed separators) makes the
  passport hashable and diffable, and makes the assembler testable to the byte.
- **Validated at the boundary.** The service validates every assembled passport
  against the schema before returning it, so a structural regression in the builder
  is caught immediately rather than propagating downstream.
- **Deterministic and injectable.** Like every engine before it, the composition is
  a pure function and every collaborator is constructor-injected with a sensible
  default, so production wires nothing while tests inject a schema, clock or config
  at will.
