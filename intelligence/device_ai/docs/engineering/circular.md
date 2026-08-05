# Circular Decision Engine (M2.2)

> The sixth **downstream consumer** of the Device Intelligence Engine and the
> second engine of milestone **M2** — an internal-only, **deterministic
> rule-evaluation engine** that turns the immutable `DeviceContext` produced by
> the **fusion engine** (M1.7), the `DecisionKnowledgeReport` produced by the
> **decision-knowledge engine** (M2.1), the `RecoverabilityReport` produced by the
> **recoverability engine** (M1.8) and the `EnvironmentalImpactReport` produced by
> the **environmental engine** (M1.11) into a single, actionable
> **`DecisionReport`** — a recommended **end-of-life action**, a **triage
> priority**, an **aggregated confidence**, the exact **rules that fired** (with
> explicit precedence) and ordered human-readable **reasoning** and **warnings**.
> Unlike M2.1 (normalized evidence only), this is the **first report in the
> pipeline that carries an actual recommendation**. Like the M2.1 and M1.11
> engines, its decision policy — *which evidence triggers which recommendation, and
> in what order of precedence* — lives in an **external, versioned YAML/JSON rule
> catalogue** so the policy is data, not logic. It ships **no new endpoint** and
> leaves the `/predict` API contract **unchanged and backward-compatible**.

**Module:** `intelligence/device_ai`
**Milestone:** M2.2 — Circular Decision Engine
**Status:** implemented; internal-only (no router, no HTTP surface)

---

## Table of contents

1. [Scope](#scope)
2. [Architecture](#architecture)
3. [Domain models](#domain-models)
4. [The external rule catalogue](#the-external-rule-catalogue)
5. [Rule catalogue & loader](#rule-catalogue--loader)
6. [Decision engine](#decision-engine)
7. [The sixteen signals](#the-sixteen-signals)
8. [Precedence & determinism](#precedence--determinism)
9. [Confidence — a separate axis](#confidence--a-separate-axis)
10. [Configuration](#configuration)
11. [Testing](#testing)
12. [Integration guide](#integration-guide)
13. [Worked examples](#worked-examples)
14. [Backward compatibility](#backward-compatibility)
15. [Design rationale](#design-rationale)

---

## Scope

M2.2 is the **sixth** engine to consume the fusion engine's output, and the first
to turn consolidated evidence into an **actionable recommendation**. Fusion
(M1.7) produces an immutable `DeviceContext`; recoverability (M1.8) turns that
into a `RecoverabilityReport`; the environmental engine (M1.11) computes an
`EnvironmentalImpactReport`; the decision-knowledge engine (M2.1) consolidates all
five downstream reports into a normalized `DecisionKnowledgeReport`. The circular
decision engine answers the next question: *"given that consolidated evidence,
what should actually be done with this device — and how urgently?"* Every part of
the recommendation is derived from **deterministic rule evaluation** over the four
upstream inputs and an external rule catalogue, never from learned models:

| # | Signal source | Source report | Effect on the report |
|---|---|---|---|
| 1 | **Consolidated dimensions** | `knowledge.repairability_score` / `.reusability_score` / `.recycling_score` / `.hazard_score` / `.environmental_priority` / `.material_value_score` / `.overall_confidence` | The seven normalized `[0, 1]` dimension scores drive the recovery ladder (refurbish → repair → recycle) and the review/hazard gates. |
| 2 | **Recoverability forces** | `recoverability.hazard_level` / `.confidence` / `.recommended_action` | Hazard severity gates every disposition; a forced `MANUAL_REVIEW` / `HAZARDOUS_DISPOSAL` upstream is honoured ahead of any recovery pathway. |
| 3 | **Environmental indices** | `environmental.circularity_index` / `.hazard_reduction_score` / `.confidence` | Available as rule signals for policy tuning (e.g. weighing circularity into a recovery decision). |
| 4 | **Fused device context** | `context.model` / `.serial` / `.imei` / `.mac` / `.has_conflicts` / `.eco_id` | Strong-identity presence gives an **identity-completeness** signal; a cross-module **conflict** flag forces a review gate. |

**Explicitly in scope**

- `DecisionReport` — the actionable, immutable recommendation with the recommended
  action, priority, aggregated confidence, the ordered triggered rules (winner
  flagged) and ordered reasoning/warnings.
- An **external, versioned** rule catalogue (YAML/JSON) with a strict loader that
  validates aggressively and fails with a typed error.
- A pure `CircularDecisionEngine` evaluation (project upstream inputs → sixteen
  normalized signals → precedence-ordered rule match → recommendation + damped
  confidence).
- An injected `CircularService` orchestration facade.

**Explicitly out of scope** (do **not** implement in M2.2): **economic/monetary
valuation**, the **marketplace**, **optimization**, blockchain anchoring, the
Digital Device Passport, **carbon-credit** issuance and **fleet analytics**. The
report recommends *what to do*, **not** *what it is worth* — no field is a
currency amount. The engine is **internal only** — no router is mounted,
`application.py` is untouched, and the `/predict` response schema is **unchanged**.

**Key input constraint.** The circular engine consumes only the **public,
aggregate surfaces** of its four upstream inputs: the consolidated dimension
scores, hazard level, confidences, environmental indices, identity attributes and
conflict flag. It never re-derives anything from raw images, models or
per-material rows — the upstream reports and the rule catalogue **only**. It also
notably does **not** consume the `ComponentReport` (M1.9) or `MaterialReport`
(M1.10) directly; their evidence already reaches it, consolidated, through the
M2.1 report.

## Architecture

The engine is a **pure domain layer** with the same shape as `fusion/`,
`recoverability/`, `decision/` and `environmental/`: frozen slotted dataclasses,
a stateless engine, and an injected service. It imports the four upstream report
types and the settings `Settings` **only under `TYPE_CHECKING`**, so there is no
runtime coupling and no import cycle — all four inputs are passed in, never
reached into past their public surface. The two runtime dependencies it does take
are the `HazardLevel` enum (to map the hazard signal) and the `FusionAttribute`
enum (to read identity attributes) — enums only, plus the `RecommendedAction`
enum it **re-uses** from the recoverability engine so a circular `DecisionReport`
and a `RecoverabilityReport` speak the same action vocabulary.

```
       fusion engine (M1.7) ─► DeviceContext ─────────────────────┐
                                                                  │
   recoverability engine (M1.8) ─► RecoverabilityReport ──────────┤
                                                                  │
    environmental engine (M1.11) ─► EnvironmentalImpactReport ────┤
                                                                  │
 decision-knowledge engine (M2.1) ─► DecisionKnowledgeReport ─────┤
                                                                  │
        ┌──────────────── circular/ (internal) ───────────────────▼─────────────┐
        │  service.py  CircularService.decide(ctx, knowledge, recov, env)        │
        │        │            │              │                                   │
        │        ▼            ▼              ▼                                   │
        │   rules.py     engine.py      config.py                             │
        │  load_rules   CircularDecision CircularConfig                       │
        │  RuleCatalogue Engine          (locator + min_confidence            │
        │  (external     (project → 16    + identity_field_count)             │
        │   YAML/JSON,   signals, match rules by precedence,                  │
        │   validated)   damp confidence)                                     │
        │        └────────────┬─────────────┘                                  │
        │                     ▼                                                │
        │   models.py  DecisionReport (frozen) · TriggeredRule · Priority     │
        └────────────────────────────────────────────────────────────────────────┘
                                ▼
       downstream (M2.3+ passport / routing) — never /predict
```

Layering (dependencies point downward, never upward):

```
fusion/ · recoverability/ · environmental/ · decision/   (M1.7–M2.1 — produce the immutable inputs)
   ↓  (TYPE_CHECKING only; all four inputs are passed in)
circular/  (models.py + rules.py + config.py + engine.py + service.py)
   ↓
exceptions · configs   (cross-cutting foundations)
```

The package contains **no HTTP imports, no FastAPI, and its only I/O is reading
the catalogue file once at service construction.** After that, `decide()` is a
pure function of its inputs except for the injected clock (which defaults to UTC
`now` and can be replaced or disabled for determinism).

## Domain models

`circular/models.py` defines the vocabulary that makes the recommendation
auditable.

### `RecommendedAction`

**Re-used verbatim** from `recoverability/models.py` (`REFURBISH`, `REPAIR`,
`RECYCLE`, `HAZARDOUS_DISPOSAL`, `MANUAL_REVIEW`) so the upstream recoverability
assessment and the circular recommendation share one action vocabulary rather
than two divergent ones. The circular engine **recommends** the action; it does
not redefine it.

### `Priority`

A `str` enum of the triage urgency of acting on the device — `HIGH`, `MEDIUM`,
`LOW`. Because it is a `str` enum, members serialize to their wire value directly
and can be constructed from a catalogue string. Ordering is **not** semantic; the
engine reads a rule's priority from the catalogue rather than from member order.

### `TriggeredRule`

The provenance of one rule that matched the evidence — a frozen slotted dataclass:

| Field | Type | Meaning |
|---|---|---|
| `rule_id` | `str` | Machine-readable identifier of the rule (catalogue provenance). |
| `action` | `RecommendedAction` | The end-of-life action this rule advises. |
| `priority` | `Priority` | The triage priority this rule advises. |
| `precedence` | `int` | The rule's precedence rank (lower wins); recorded for audit. |
| `reason` | `str` | Human-readable explanation of why the rule matched. |
| `won` | `bool` | Whether this rule determined the report's recommendation. |

Retaining **every** triggered rule (not just the winner) is what makes the
precedence decision transparent: an operator can see exactly what else applied and
why it was overridden.

### `DecisionReport`

The actionable, immutable outcome — a frozen slotted dataclass:

| Field | Meaning |
|---|---|
| `recommended_action` | The advised end-of-life disposition. |
| `priority` | The triage priority of acting on the recommendation. |
| `confidence` | Aggregated confidence `[0, 1]`, blended from the consolidated decision confidence and every triggered rule's confidence factor. |
| `triggered_rules` | The rules that matched, ordered by precedence (winner first); empty when only the catalogue fallback applied. |
| `reasoning` | Ordered, human-readable reasons behind the recommendation. |
| `warnings` | Ordered operator-facing cautions (may be empty). |

Plus provenance (`device_type`, `eco_id`, `engine_version`, `rules_version`,
`created_at`). Convenience API: `triggered_count`, `winning_rule` (the `won` rule
or `None` when the fallback applied). `to_dict()` renders a fully
JSON-serializable payload (enum → wire value, timestamp → ISO-8601 or `None`).

## The external rule catalogue

The engine's decision policy lives **outside the code** in
`circular/data/rules.yaml` — a versioned catalogue that is **data, not logic**, so
*which evidence triggers which recommendation, and in what order of precedence*
can be reviewed, tuned or corrected as triage policy evolves without touching or
redeploying the engine.

Top-level keys:

| Key | Meaning |
|---|---|
| `version` | Semantic version string, stamped onto every produced report. |
| `rules` | List of rules; each has `id`, `precedence`, `action`, `priority`, `reason`, a non-empty `when` list of conditions, and optional `confidence_factor` (in `(0, 1]`) and `warning`. |
| `default` | Fallback `{ action, priority, reason }` applied when no rule fires. |

A `when` condition is `{ signal, operator, threshold }`, where `operator` is one
of `gte` / `lte` / `gt` / `lt` and `threshold` is in `[0, 1]`. A rule fires only
when **all** of its conditions hold (a conjunction). The shipped catalogue's ten
rules encode a **hazard-first, then review-gate, then recovery-ladder** policy:

| Precedence | Rule | Fires when | Recommends |
|---|---|---|---|
| 10 | `upstream_forced_hazardous_disposal` | `upstream_hazardous_disposal ≥ 1` | `hazardous_disposal` / high |
| 20 | `high_hazard_severity` | `hazard_severity ≥ 0.7` | `hazardous_disposal` / high |
| 30 | `upstream_forced_manual_review` | `upstream_manual_review ≥ 1` | `manual_review` / medium (conf ×0.85) |
| 40 | `identity_conflict_review` | `conflict ≥ 1` | `manual_review` / medium (conf ×0.85) |
| 50 | `low_confidence_review` | `decision_confidence ≤ 0.35` | `manual_review` / low |
| 60 | `high_value_refurbish` | `reusability ≥ 0.65` **and** `environmental_priority ≥ 0.5` | `refurbish` / high |
| 70 | `refurbish` | `reusability ≥ 0.65` | `refurbish` / medium |
| 80 | `repair` | `repairability ≥ 0.55` | `repair` / medium |
| 90 | `high_value_recycle` | `recycling ≥ 0.45` **and** `material_value ≥ 0.6` | `recycle` / high |
| 100 | `recycle` | `recycling ≥ 0.45` | `recycle` / low |
| — | `default` | nothing above fires | `manual_review` / low |

## Rule catalogue & loader

`circular/rules.py` turns the catalogue file into validated, immutable value
objects, and owns the **fixed vocabulary** the catalogue is validated against:

- **`CANONICAL_SIGNALS`** — the sixteen normalized input signals the engine
  projects from the four upstream inputs. The catalogue may reference these in
  conditions but may **not** invent new ones, so a typo in a condition is caught at
  load time rather than silently ignored.
- **`CONDITION_OPERATORS`** — the four comparison operators (`gte`, `lte`, `gt`,
  `lt`); there is deliberately **no** float-equality operator (signals are
  continuous).
- **`RuleCondition`** — one conjunction term: a projected signal compared to a
  threshold. `matches(signals)` reads a missing signal as `0.0` (absent evidence
  contributes nothing).
- **`DecisionRule`** — one policy rule (id, precedence, action, priority, reason,
  conditions, optional confidence factor / warning). `matches(signals)` is the
  conjunction of its conditions.
- **`DefaultRule`** — the required fallback recommendation.
- **`RuleCatalogue`** — the whole loaded catalogue: `version`, the rules sorted by
  ascending precedence (winner first), and the default. `rule_count` returns the
  number of rules.

`load_rules(path)` reads YAML (or JSON, by suffix), then **validates
aggressively**, raising a typed `CircularRuleError` on any structural problem:

- file missing / unparseable / not a mapping / empty;
- missing or empty `version`;
- no `rules`, or `rules` not a list;
- a rule missing its `id` / `precedence` / `action` / `priority` / `reason`, a
  **duplicate rule id** or a **duplicate precedence** (precedence must be unique so
  the winner is unambiguous);
- a non-integer / boolean / negative precedence;
- an unknown `action` or `priority` name;
- a rule with **no** `when` conditions;
- an unknown signal or operator in a condition, or an out-of-range / non-numeric /
  boolean threshold;
- a `confidence_factor` outside `(0, 1]`;
- a missing `default` fallback.

Because the loader fails loudly on a bad catalogue, a malformed rule file **never
silently degrades** the engine.

## Decision engine

`circular/engine.py` holds the deterministic evaluation. `evaluate(...)` has three
clean stages:

1. **Project** the four upstream inputs onto the sixteen canonical normalized
   `[0, 1]` signals (see below). The already-normalized upstream scores pass
   through; `hazard_severity` is mapped from `HazardLevel` (`NONE` 0.0, `UNKNOWN`
   0.25, `LOW` 0.4, `MEDIUM` 0.7, `HIGH` 1.0 — matching the decision and
   environmental engines); the boolean upstream forces (manual review, hazardous
   disposal) and the conflict flag become `0.0` / `1.0`; `identity_completeness` is
   the fraction of the four strong identity attributes fusion resolved.
2. **Match** every catalogue rule against the projected signals. A rule fires only
   when **all** its conditions hold. Because the catalogue is pre-sorted by
   ascending precedence, the **first** rule that fires is the winner; every fired
   rule is retained (winner flagged) as a lower-precedence alternative. When
   nothing fires, the catalogue's required `default` supplies the recommendation,
   so the engine always yields a defined action.
3. **Aggregate confidence** from the consolidated decision confidence, damped by
   the product of every fired rule's confidence factor, then clamp and round.
   Confidence is a **separate axis** and never changes which action was recommended.

Finally it assembles ordered reasoning (the winning-rule or default line, an
overridden-rules line, a confidence line) and operator warnings (each fired
rule's own warning in precedence order, an assessed-hazard warning, a
manual-review warning, and a low-confidence warning when confidence is at/below
the configured floor). There is **no model and no I/O** here — given the same
inputs the engine always produces the same `DecisionReport`.

## The sixteen signals

The sixteen canonical signals, and which upstream surface each is projected from:

| Signal | Source | Range |
|---|---|---|
| `repairability` | `knowledge.repairability_score` | `[0, 1]` pass-through |
| `reusability` | `knowledge.reusability_score` | `[0, 1]` pass-through |
| `recycling` | `knowledge.recycling_score` | `[0, 1]` pass-through |
| `hazard_score` | `knowledge.hazard_score` | `[0, 1]` pass-through |
| `environmental_priority` | `knowledge.environmental_priority` | `[0, 1]` pass-through |
| `material_value` | `knowledge.material_value_score` | `[0, 1]` pass-through |
| `decision_confidence` | `knowledge.overall_confidence` | `[0, 1]` pass-through |
| `hazard_severity` | `recoverability.hazard_level` (mapped) | `[0, 1]` |
| `recoverability_confidence` | `recoverability.confidence` | `[0, 1]` pass-through |
| `upstream_manual_review` | `recoverability.recommended_action is MANUAL_REVIEW` | `0.0` / `1.0` |
| `upstream_hazardous_disposal` | `recoverability.recommended_action is HAZARDOUS_DISPOSAL` | `0.0` / `1.0` |
| `circularity_index` | `environmental.circularity_index` | `[0, 1]` pass-through |
| `hazard_reduction` | `environmental.hazard_reduction_score` | `[0, 1]` pass-through |
| `environmental_confidence` | `environmental.confidence` | `[0, 1]` pass-through |
| `identity_completeness` | fused model/serial/IMEI/MAC presence | `[0, 1]` |
| `conflict` | `context.has_conflicts` | `0.0` / `1.0` |

Every projected signal is clamped to `[0, 1]` and rounded to 6 decimals
(`_SCORE_PRECISION`), matching the fusion, recoverability, decision and
environmental engines so every engine's numbers compare cleanly.

## Precedence & determinism

Every rule carries a **unique** integer precedence (the loader rejects
duplicates). The engine fires **every** rule whose conditions all hold, then the
fired rule with the **lowest** precedence determines the recommendation; the rest
are retained on the report as overridden alternatives. Because the catalogue is
sorted by ascending precedence at load and the match preserves that order, the
winner is simply the first fired rule — the recommendation is fully reproducible
and auditable. When no rule fires, the required `default` applies, so the engine
never guesses and never returns an undefined action.

This is what makes the recommendation **explainable end to end**: the report names
the winning rule *and* every rule it overrode, in precedence order, so an operator
can reconstruct exactly why a device was routed the way it was.

## Confidence — a separate axis

`confidence` starts from the consolidated `knowledge.overall_confidence` and is
damped by the **product** of every fired rule's `confidence_factor` (`1.0` for
rules that do not damp), then clamped and rounded:

```
confidence = clamp( decision_confidence × Π factorᵣ )   over fired rules r
```

Independent damping signals therefore compound (e.g. a forced review *and* a
conflict both damp). Crucially, confidence is a **separate axis**: it never
changes which action was recommended — the rules decide that. A recommendation
whose aggregated confidence is at or below the configured floor
(`min_confidence`) gets an operator-facing low-confidence **warning**, but the
action itself is untouched.

## Configuration

`CircularConfig` (frozen slotted) holds the catalogue locator and two tunable
operational knobs, so the config stays a thin locator plus projection knobs —
everything that actually shapes a *recommendation* lives in the external
catalogue:

| Field | Default | Meaning |
|---|---|---|
| `rules_path` | `circular/data/rules.yaml` | Catalogue locator, resolved against the package root when relative. |
| `min_confidence` | `0.35` | Aggregated confidence at or below which the report gets a low-confidence warning. Never changes the action. |
| `identity_field_count` | `4` | Number of identity fields (model, serial, IMEI, MAC) the `identity_completeness` signal is normalized against. |

The two env-driven knobs are mapped via `CircularConfig.from_settings(settings)`:

| Env var | Field |
|---|---|
| `CIRCULAR_RULES_PATH` | `rules_path` |
| `CIRCULAR_MIN_CONFIDENCE` | `min_confidence` |

The typed exceptions added for this engine are `CircularDecisionError`
(`CIRCULAR_DECISION_ERROR`, 500) and its loader subclass `CircularRuleError`
(`CIRCULAR_RULE_ERROR`, 422).

## Testing

Three test modules under `tests/`, all offline (no images, no models; only the
external catalogues are read from disk):

- **`test_circular_rules.py`** — the shipped catalogue's structure and invariants
  (rules sorted by precedence, unique ids and precedences, only canonical
  signals/operators used, in-range thresholds, known actions/priorities, a valid
  default), the condition/rule matching semantics (operator predicates, missing
  signal read as `0.0`, conjunction), `to_dict` round-trips, and the loader's
  validation on hand-written good/bad catalogues in `tmp_path` (missing file,
  malformed YAML, empty, non-mapping root, missing version, no/`non-list` rules,
  missing default, a rule with no conditions, unknown signal/operator/action/
  priority, out-of-range threshold, negative/boolean precedence, boolean
  threshold, out-of-range confidence factor, duplicate id, duplicate precedence,
  precedence sorting), and JSON parity.
- **`test_circular_engine.py`** — the deterministic evaluation against a small
  hand-built catalogue and hand-built reports: signal pass-through, the
  hazard-severity mapping (every level), the upstream-force and conflict flags,
  identity completeness, precedence (lowest wins), triggered-rule ordering,
  determinism, every action and every priority reachable, the default fallback,
  confidence aggregation (pass-through, compounding factors, action invariance),
  reasoning/warnings (winning reason, rule warning, hazard warning, low-confidence
  warning, overridden note), and provenance / device-type resolution.
- **`test_circular_service.py`** — end-to-end `decide(...)` against the **shipped**
  catalogue, with the four upstream inputs built by actually running the
  recoverability, component, material, environmental and decision-knowledge engines
  over a hand-built `DeviceContext`: an identifiable laptop, a hazardous CRT (→
  `hazardous_disposal` / high), an unknown device (→ `manual_review`) and a
  conflicted context (confidence damped), plus the no-monetary-field invariant,
  determinism, provenance/version stamping, the injected clock, the JSON shape,
  report immutability, at-most-one-winner, and injected config/catalogue /
  `from_settings` mapping.

The three modules add **80** new tests, all passing; the module is `ruff`-,
`black`- and `isort`-clean and adds **zero** `mypy` errors.

## Integration guide

The engine is consumed **directly** (no HTTP). Orchestrating code runs the
upstream engines and hands their reports to `CircularService.decide`:

```python
from device_ai.fusion import FusionService
from device_ai.recoverability import RecoverabilityService
from device_ai.components import ComponentService
from device_ai.materials import MaterialService
from device_ai.environmental import EnvironmentalService
from device_ai.decision import DecisionService
from device_ai.circular import CircularService

# 1. Fuse the perception engines into an immutable context (M1.7).
context = FusionService().fuse(evidence)

# 2. Assess recoverability (M1.8), infer components (M1.9), estimate materials
#    (M1.10), compute environmental impact (M1.11), consolidate decision
#    knowledge (M2.1).
recoverability = RecoverabilityService().assess(context)
components = ComponentService().analyze(context, recoverability)
materials = MaterialService().analyze(context, recoverability, components)
environmental = EnvironmentalService().analyze(
    context, recoverability, components, materials
)
knowledge = DecisionService().analyze(
    context, recoverability, components, materials, environmental
)

# 3. Recommend a circular disposition (M2.2). Every collaborator is injected, so
#    the service is constructible as-is or with a fixed clock / custom config /
#    pre-loaded rule catalogue. The external catalogue is loaded once at
#    construction. Note the four inputs: context, knowledge, recoverability, env.
decision = CircularService().decide(
    context, knowledge, recoverability, environmental
)

payload = decision.to_dict()   # JSON-serializable; feed the M2.3+ routing/passport layer
```

For **deterministic** use (tests, reproducible pipelines) construct the service
with `clock=None` (drops the timestamp) and/or inject a hand-built `RuleCatalogue`
or a custom `CircularConfig`.

## Worked examples

### Identifiable laptop — recovery ladder

A confident, well-identified laptop with no high hazard and healthy consolidated
scores clears the recovery ladder: if `reusability ≥ 0.65` it is recommended for
**refurbish** (high priority when the environmental stake is also large), else
**repair** if `repairability ≥ 0.55`, else **recycle** if `recycling ≥ 0.45`. The
winning rule and any lower-precedence rules it overrode are both listed, and the
confidence carries over the consolidated decision confidence.

### CRT monitor — hazard gates everything

A CRT's leaded glass drives a `HIGH` hazard upstream and a forced
`HAZARDOUS_DISPOSAL`, so the precedence-10 `upstream_forced_hazardous_disposal`
rule wins and the report recommends **`hazardous_disposal` at high priority** —
regardless of any recovery scores — with a mandatory-handling warning. The
hazard-first precedence ordering is exactly what guarantees a hazardous device is
never routed to reuse or standard recycling.

### Unknown device — review gate

An unrecognized type falls back upstream to a forced `MANUAL_REVIEW` at damped
confidence, so the precedence-30 `upstream_forced_manual_review` rule wins and the
report recommends **`manual_review`** with a human-decision warning and a damped
confidence (`×0.85`). The engine never guesses a disposition for a device it
cannot identify.

## Backward compatibility

M2.2 is **purely additive** and **internal-only**:

- **No endpoint, no router, no schema change.** `application.py` and the
  `/predict` request/response contract are untouched; the only new symbols are the
  `circular/` package, two `Settings` fields and two typed exceptions.
- **No change to any upstream engine.** The engine consumes the existing public
  surfaces of the M1.7 / M1.8 / M1.11 / M2.1 reports and adds nothing to them; it
  **re-uses** the recoverability engine's `RecommendedAction` rather than
  redefining it.
- **External catalogue.** All decision policy is data in `circular/data/rules.yaml`,
  versioned independently of the code.

## Design rationale

- **The first recommendation, kept auditable.** Unlike M2.1's normalized
  evidence, this report tells an operator *what to do*. Making every recommendation
  the output of an **explicit, precedence-ordered** rule match — with the winner
  and every overridden rule named on the report — keeps that recommendation
  transparent rather than a black-box verdict.
- **Policy is data, not logic.** *Which evidence triggers which action, and in what
  order* is triage policy that evolves; keeping it in an external, versioned,
  strictly-validated catalogue lets it be reviewed and corrected without
  redeploying — and a malformed catalogue fails loudly rather than silently
  routing devices wrongly.
- **Hazard first, then review, then recover.** The precedence ordering encodes a
  deliberate safety priority: a hazard or an upstream-forced review always
  overrides a recovery pathway, so the engine can never route a hazardous or
  unidentified device to reuse.
- **One action vocabulary.** Re-using the recoverability engine's
  `RecommendedAction` means the upstream assessment and the final recommendation
  speak the same language, so the two reports compose without translation.
- **Two axes, kept apart.** The action/priority is decided by the rules; confidence
  is a second, independent axis that only *annotates* the recommendation (and
  raises a warning when weak) but never changes it.
- **Deterministic and injectable.** Like every engine before it, the evaluation is
  a pure function and every collaborator is constructor-injected with a sensible
  default, so production wires nothing while tests inject a rule catalogue, clock
  or config at will.
