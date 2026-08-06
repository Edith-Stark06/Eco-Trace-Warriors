# 04 — Decision Intelligence Architecture

**Document Version:** 1.0  
**Status:** Active  
**Last Updated:** 2026-08-06  
**Scope:** Decision Intelligence Layer only (milestones M2.1–M2.5)  
**Audience:** IEEE YESIST reviewers, patent reviewers, enterprise architects, AI researchers, software engineers

---

## Table of Contents

1. Executive Summary
2. Decision Intelligence Overview
3. Overall Decision Pipeline
4. Decision Engine Relationships
5. Decision Knowledge Engine (M2.1)
6. Circular Decision Engine (M2.2)
7. Device Passport Core (M2.3)
8. Passport Integrity Engine (M2.4)
9. Trust & Provenance Engine (M2.5)
10. End-to-End Decision Flow
11. Shared Decision Domain Models
12. Knowledge Catalogue Architecture
13. Rule Evaluation Architecture
14. Confidence Propagation Strategy
15. Passport Assembly Strategy
16. Integrity Verification Strategy
17. Trust Computation Strategy
18. Configuration
19. Error Handling
20. Dependency Injection
21. Explainability
22. Testing Strategy
23. Performance
24. Extension Points
25. Current Limitations
26. Future Decision Platform Evolution

---

## 1. Executive Summary

The **Decision Intelligence Layer** is the second major subsystem of the Device Intelligence Engine that turns the raw perception and knowledge-tier outputs into actionable, auditable, immutable decision artifacts: what action to recommend, what the device passport document should carry, whether that passport is structurally sound, and how trustworthy it is.

Spanning milestones **M2.1 through M2.5**, this layer is where the EcoTrace India platform moves from *knowing* (the Device Intelligence engines M1.1–M1.11 in [03 — Device Intelligence Architecture]) to *deciding* and *certifying*. It orchestrates five sequential, internal-only engines into a deterministic pipeline:

1. **Decision Knowledge Engine (M2.1)** — consolidates the five upstream device-intelligence reports into six normalized `[0, 1]` decision dimensions (repairability, reusability, recycling, hazard, environmental priority, material value) and a separate overall-confidence axis. It is **evidence only** — no recommended action.

2. **Circular Decision Engine (M2.2)** — evaluates a versioned, precedence-ordered policy rule catalogue against the decision-knowledge evidence and recommends one end-of-life action (`repair`, `refurbish`, `recycle`, `manual_review`, or `hazardous_disposal`). Every recommendation is auditable: the fired rules, their precedence, and the winning rule are all retained.

3. **Device Passport Core (M2.3)** — assembles a canonical, immutable `DevicePassport` document from the upstream reports. It performs **no inference**; every value is copied or plainly summarized. The passport is a structured snapshot validated against an external schema.

4. **Passport Integrity Engine (M2.4)** — re-validates the assembled passport against an external rule-set, reports structural errors and warnings, and computes a deterministic SHA-256 integrity hash over the passport's canonical JSON serialization. A malformed passport is **reported** (`is_valid=False`), never raised.

5. **Trust & Provenance Engine (M2.5)** — scores how trustworthy the passport is by blending four sub-axes (identity confidence, evidence consistency, decision confidence, integrity confidence) into a normalized trust score, then maps that score to a trust level (`high`, `medium`, `low`, `untrusted`). Low-trust passports are **reported** with ordered warnings, never rejected.

All five engines are **internal-only**: they expose no HTTP surface and are consumed in-process by the orchestrating pipeline. Failures surface as typed exceptions (engine faults) or low-confidence/low-trust/invalid reports (data faults). Every engine is deterministic, independently testable, and mirrors the design established in M1.11 (external versioned catalogue + strict loader + frozen config + injectable service + optional clock).

---

## 2. Decision Intelligence Overview

The Decision Intelligence Layer sits between the perception/knowledge tier (M1.1–M1.11, documented in [03 — Device Intelligence Architecture]) and the downstream blockchain ledger (M3.1–M3.3). It answers four questions in sequence:

1. **What does the evidence weigh?** (M2.1) — Six normalized decision dimensions scored from upstream reports.
2. **What should be done?** (M2.2) — One recommended end-of-life action chosen by policy rules.
3. **What is the authoritative document?** (M2.3) — A canonical device passport assembled from all upstream evidence.
4. **Is that document structurally sound?** (M2.4) — Validation status + deterministic integrity hash.
5. **How trustworthy is it?** (M2.5) — Trust score + trust level derived from consistency and confidence signals.

### Design Philosophy

The layer is deliberately **staged and unidirectional**: M2.1 feeds M2.2, M2.2 feeds M2.3, M2.3 feeds M2.4, and M2.4 feeds M2.5. No engine sees future stages' outputs; no engine loops back. This keeps the dependency graph acyclic, the testing independent, and the orchestration simple.

Every engine follows the **external catalogue + strict loader + frozen config** pattern established in M1.11:

- **Policy lives outside code** — signal weights, rule precedences, schema contracts, validation rules, and trust thresholds are versioned YAML/JSON files loaded at service construction. Tuning policy never touches the engine.
- **Loaders validate aggressively** — a malformed catalogue, duplicate rule id, unknown signal name, negative weight, or missing required dimension is rejected at load time with a typed exception. A bad catalogue never silently degrades an engine.
- **Services are fully injectable** — every collaborator (config, catalogue, engine, clock) is constructor-injected with a sensible default, so production code wires nothing while tests inject hand-built catalogues and fixed clocks.
- **Reports are deterministic** — given the same inputs, an engine always produces byte-identical output. Every score is rounded to 6 decimals (`_SCORE_PRECISION = 6`); every JSON serialization is canonical (`sort_keys=True`, stable separators); every timestamp is optional (pass `clock=None` to omit `created_at` entirely).

### Internal-Only Architecture

None of the five engines exposes an HTTP endpoint. They are consumed in-process by the orchestrating pipeline (out of scope for this document; the `/predict` contract is frozen at M1.4 and unchanged). This internal-only posture has three consequences:

1. **Typed exceptions** — a malformed catalogue, unsupported hash algorithm, or missing schema file raises a typed exception (`DecisionKnowledgeError`, `CircularRuleError`, `PassportSchemaError`, `PassportIntegrityRuleError`, `PassportTrustRuleError`) that surfaces directly to the orchestrating code. There is no HTTP error envelope here.

2. **Report-based faults** — a low-scoring device, a low-trust passport, or a structurally invalid passport is **reported** (`confidence=0.15`, `trust_level=untrusted`, `status=INVALID`), never raised. The distinction is deliberate: a malformed **engine** (bad catalogue) is a fault; a malformed **input** (low-confidence data) is a verdict.

3. **No transport concerns** — domain models (`DecisionKnowledgeReport`, `DecisionReport`, `DevicePassport`, `PassportIntegrityReport`, `PassportTrustReport`) are frozen, slotted dataclasses with `to_dict()` and `to_json()` methods. They carry no Pydantic, FastAPI, or HTTP logic.

---

## 3. Overall Decision Pipeline

The five engines form a linear, acyclic dependency chain. Each consumes the outputs of all prior stages and produces exactly one immutable report:

```
┌────────────────────────────────────────────────────────────────────┐
│                    OVERALL DECISION PIPELINE                        │
│                                                                      │
│  Upstream (M1.1–M1.11)                                              │
│  ─────────────────                                                  │
│  • DeviceContext (M1.7 fusion)                                     │
│  • RecoverabilityReport (M1.8)                                     │
│  • ComponentReport (M1.9)                                          │
│  • MaterialReport (M1.10)                                          │
│  • EnvironmentalImpactReport (M1.11)                               │
│  • DeviceFingerprint (M1.5, optional)                              │
│                                                                      │
│                           ↓                                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ M2.1: Decision Knowledge Engine                               │  │
│  │ ─────────────────────────────────────────────────────────────│  │
│  │ Consolidates 5 upstream reports → 6 normalized [0,1]         │  │
│  │ decision dimensions + separate overall confidence.            │  │
│  │ External: decision/data/knowledge.yaml (version 1.0.0)        │  │
│  │ Output: DecisionKnowledgeReport                               │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                           ↓                                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ M2.2: Circular Decision Engine                                │  │
│  │ ─────────────────────────────────────────────────────────────│  │
│  │ Evaluates precedence-ordered policy rules → one recommended  │  │
│  │ action (repair/refurbish/recycle/manual_review/disposal).     │  │
│  │ External: circular/data/rules.yaml (version 1.0.0, 10 rules) │  │
│  │ Output: DecisionReport                                        │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                           ↓                                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ M2.3: Device Passport Core                                    │  │
│  │ ─────────────────────────────────────────────────────────────│  │
│  │ Assembles upstream reports → canonical DevicePassport         │  │
│  │ document (13 sections, no new inference).                     │  │
│  │ External: passport/data/schema.yaml (version 1.0.0)           │  │
│  │ Output: DevicePassport                                        │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                           ↓                                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ M2.4: Passport Integrity Engine                               │  │
│  │ ─────────────────────────────────────────────────────────────│  │
│  │ Re-validates passport structure → status + ordered errors/    │  │
│  │ warnings + SHA-256 integrity hash over canonical JSON.        │  │
│  │ External: integrity/data/rules.yaml (version 1.0.0)           │  │
│  │ Output: PassportIntegrityReport                               │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                           ↓                                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ M2.5: Trust & Provenance Engine                               │  │
│  │ ─────────────────────────────────────────────────────────────│  │
│  │ Scores 4 trust sub-axes → trust score [0,1] → trust level    │  │
│  │ (high/medium/low/untrusted).                                  │  │
│  │ External: trust/data/rules.yaml (version 1.0.0)               │  │
│  │ Output: PassportTrustReport                                   │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  Final outputs: DevicePassport + PassportIntegrityReport +         │
│                 PassportTrustReport → blockchain ledger (M3.1)      │
└────────────────────────────────────────────────────────────────────┘
```

### Pipeline Characteristics

- **Linear**: M2.1 → M2.2 → M2.3 → M2.4 → M2.5. No engine sees future stages.
- **Deterministic**: Same inputs → byte-identical outputs (when `clock=None`).
- **Versioned**: Every catalogue declares a semantic `version` stamped onto its report.
- **Auditable**: Every score/action/level carries ordered human-readable reasoning.
- **No side effects**: No HTTP calls, no database writes, no file I/O during inference.
- **Injectable**: Every service accepts `config`, `catalogue`, `engine`, `clock` at construction.

---

## 4. Decision Engine Relationships

The five engines collaborate through immutable report objects. The dependency graph is strictly acyclic:

**M2.1 Decision Knowledge Engine**
- **Consumes**: `DeviceContext` (M1.7), `RecoverabilityReport` (M1.8), `ComponentReport` (M1.9), `MaterialReport` (M1.10), `EnvironmentalImpactReport` (M1.11)
- **Produces**: `DecisionKnowledgeReport` (6 decision dimensions + overall confidence)
- **Feeds**: M2.2, M2.5

**M2.2 Circular Decision Engine**
- **Consumes**: `DeviceContext` (M1.7), `DecisionKnowledgeReport` (M2.1), `RecoverabilityReport` (M1.8), `EnvironmentalImpactReport` (M1.11)
- **Produces**: `DecisionReport` (recommended action + priority + fired rules)
- **Feeds**: M2.3, M2.5

**M2.3 Device Passport Core**
- **Consumes**: `DeviceContext` (M1.7), `DecisionReport` (M2.2), `MaterialReport` (M1.10), `EnvironmentalImpactReport` (M1.11), `DeviceFingerprint` (M1.5, optional)
- **Produces**: `DevicePassport` (13-section canonical document)
- **Feeds**: M2.4, M2.5

**M2.4 Passport Integrity Engine**
- **Consumes**: `DevicePassport` (M2.3)
- **Produces**: `PassportIntegrityReport` (validation status + integrity hash)
- **Feeds**: M2.5

**M2.5 Trust & Provenance Engine**
- **Consumes**: `DevicePassport` (M2.3), `PassportIntegrityReport` (M2.4), `DecisionKnowledgeReport` (M2.1), `DecisionReport` (M2.2)
- **Produces**: `PassportTrustReport` (trust score + trust level + 4 sub-axes)
- **Feeds**: Blockchain ledger (M3.1–M3.3, out of scope)

### Shared Design Invariants

All five engines honor these invariants:

- **Immutability** — every report is `@dataclass(frozen=True, slots=True)`.
- **Determinism** — same inputs → byte-identical output (when `clock=None`).
- **6-decimal precision** — every score/confidence rounded to `_SCORE_PRECISION = 6`.
- **Canonical JSON** — `sort_keys=True`, stable separators, `ensure_ascii=False`.
- **Optional timestamps** — pass `clock=None` at service construction to omit `created_at`.
- **Versioned catalogues** — every external YAML/JSON file declares a semantic `version`.
- **Aggressive loaders** — malformed catalogues raise typed exceptions at load time.
- **Constructor injection** — every collaborator injectable with sensible defaults.
- **Internal-only** — no HTTP surface; failures surface as typed exceptions or low-confidence/low-trust/invalid reports.

---

## 5. Decision Knowledge Engine (M2.1)

### Purpose

The Decision Knowledge Engine consolidates the five upstream device-intelligence reports — `DeviceContext` (M1.7), `RecoverabilityReport` (M1.8), `ComponentReport` (M1.9), `MaterialReport` (M1.10), and `EnvironmentalImpactReport` (M1.11) — into a single, normalized `DecisionKnowledgeReport` containing six comparable `[0, 1]` decision dimensions and a separate overall-confidence axis.

The report is **normalized evidence only**. It answers "how much does each decision dimension weigh for this device" on a common scale; it deliberately contains **no recommended action**, no economic valuation, and no optimization. The engine consolidates upstream signals into comparable evidence so a later decision layer (M2.2) has one clean, auditable input.

### Responsibilities

1. **Project** — map the five upstream reports onto eleven normalized `[0, 1]` input signals:
   - Already-normalized upstream scores (repairability, reusability, recyclability, circularity_index, hazard_reduction) pass through unchanged.
   - Environmental engine's unbounded physical amounts (carbon/energy/water saved, critical material recovered) are divided by saturation constants and clamped to `[0, 1]`.
   - Mass fractions (recoverable/hazardous) computed from material report totals.
   - Identity completeness computed as the fraction of strong identity fields present (model, serial, IMEI, MAC).

2. **Blend** — score each of the six decision dimensions as the weighted average of its signals, using per-dimension weights from the external knowledge catalogue. Every dimension score is a transparent weighted mean.

3. **Aggregate confidence** — blend the five upstream confidences (from recoverability, components, materials, environmental, fusion) into a single overall-confidence axis, weighted by the catalogue. Confidence never scales a dimension score; it is a separate axis.

4. **Explain** — generate ordered human-readable reasoning and warnings describing how each dimension was scored and what caveats apply.

### Inputs

- `DeviceContext` (M1.7) — fused identity, device type, confidence, conflict flags.
- `RecoverabilityReport` (M1.8) — repairability, reusability, recyclability, hazard level/severity, confidence.
- `ComponentReport` (M1.9) — component breakdown, overall confidence.
- `MaterialReport` (M1.10) — material breakdown, masses (total, recoverable, hazardous), confidence.
- `EnvironmentalImpactReport` (M1.11) — carbon/energy/water saved, circularity index, critical material recovered, hazard reduction score, confidence.
- `KnowledgeBase` (external catalogue) — per-dimension signal weights, confidence weights, saturation constants.

### Outputs

`DecisionKnowledgeReport` containing:

- Six normalized `[0, 1]` decision dimensions: `repairability_score`, `reusability_score`, `recycling_score`, `hazard_score`, `environmental_priority`, `material_value_score`
- Separate `overall_confidence` axis (never scales dimension scores)
- Per-dimension evidence breakdown (`DimensionEvidence` for each dimension, with ordered `EvidenceSignal` records showing `name`, `value`, `weight`)
- Ordered reasoning and warnings
- Provenance: `eco_id`, `device_type`, `engine_version`, `knowledge_version`, `created_at`

### Internal Workflow

The engine implements a three-stage pipeline:

**Stage 1: Project** — Map the five upstream reports onto eleven normalized `[0, 1]` input signals (the canonical vocabulary defined in `CANONICAL_SIGNALS`):

- `repairability` ← `recoverability.repairability` (pass through)
- `reusability` ← `recoverability.reusability` (pass through)
- `recyclability` ← `recoverability.recyclability` (pass through)
- `circularity_index` ← `environmental.circularity_index` (pass through)
- `hazard_severity` ← `recoverability.hazard_level` mapped to `{NONE:0.0, UNKNOWN:0.25, LOW:0.4, MEDIUM:0.7, HIGH:1.0}`
- `hazard_reduction` ← `environmental.hazard_reduction_score` (pass through)
- `hazardous_mass_fraction` ← `materials.hazardous_mass_g / materials.total_mass_g` (computed, 0 when total is 0)
- `critical_material_presence` ← `environmental.critical_material_recovery_kg / normalization.critical_recovery_saturation_kg` (saturated, clamped)
- `recoverable_mass_fraction` ← `materials.recoverable_mass_g / materials.total_mass_g` (computed, 0 when total is 0)
- `environmental_savings` ← mean of three saturated resource axes: `(carbon_saved/carbon_saturation + energy_saved/energy_saturation + water_saved/water_saturation) / 3` (saturated, clamped)
- `identity_completeness` ← fraction of strong identity fields present: `count(model, serial, IMEI, MAC present) / 4`

Every signal is clamped to `[0, 1]` and rounded to 6 decimals.

**Stage 2: Blend** — Score each of the six decision dimensions as the weighted average of its signals:

For each dimension `d`:
1. Read the dimension's `signal → weight` map from the knowledge catalogue.
2. For each signal in that map, multiply the signal's projected value by its weight.
3. Sum the weighted values and divide by the total weight.
4. Clamp to `[0, 1]` and round to 6 decimals.

Formula: `dimension_score = clamp_round(Σ(signal_value × signal_weight) / Σ(signal_weight))`

Each dimension is scored independently; the loader guarantees at least one positive weight per dimension, so division by zero never occurs.

**Stage 3: Aggregate confidence** — Blend the five upstream confidences into `overall_confidence`:

1. Read the five upstream confidence values: `recoverability.confidence`, `components.overall_confidence`, `materials.overall_confidence`, `environmental.confidence`, `context.confidence`.
2. For each source, if its confidence is above the configured `min_confidence` floor and its catalogue weight is positive, include it in the blend.
3. Compute the weighted average: `overall_confidence = clamp_round(Σ(source_confidence × source_weight) / Σ(source_weight))`.

Sources at or below the floor are dropped entirely (their weight is removed), so a near-zero upstream confidence does not silently anchor the result. If all sources are dropped, `overall_confidence` is 0.

### Configuration

`DecisionConfig` (immutable, frozen, slotted):
- `knowledge_path` (string, default `"decision/data/knowledge.yaml"`) — locator of the external knowledge catalogue, resolved relative to `device_ai` package root when not absolute.
- `min_confidence` (float, default `0.05`, range `[0, 1]`) — confidence floor; upstream sources at or below this are dropped from the overall-confidence blend.

Mapped from environment via `DecisionConfig.from_settings(settings)`:
- `DECISION_KNOWLEDGE_PATH` → `knowledge_path`
- `DECISION_MIN_CONFIDENCE` → `min_confidence`

### Collaborators

- **Upstream reports**: `DeviceContext` (M1.7), `RecoverabilityReport` (M1.8), `ComponentReport` (M1.9), `MaterialReport` (M1.10), `EnvironmentalImpactReport` (M1.11)
- **External catalogue**: `decision/data/knowledge.yaml` (version 1.0.0) — loaded by `load_knowledge()` into immutable `KnowledgeBase`
- **Inference engine**: `DecisionInferenceEngine` — pure deterministic fold, no I/O
- **Service**: `DecisionService` — constructor-injectable façade that loads the catalogue once, stamps provenance, and optionally injects a clock

### Dependency Graph

```
DeviceContext ────┐
RecoverabilityReport ─┤
ComponentReport ──┤
MaterialReport ───┤──→ DecisionInferenceEngine ──→ DecisionKnowledgeReport
EnvironmentalImpactReport ─┘              ↑
                                           │
                                    KnowledgeBase
                                    (external YAML)
```

### Error Handling

**Load-time failures** (malformed catalogue) raise `DecisionKnowledgeError`:
- Missing or empty `version`
- Missing or non-positive saturation constant
- Missing dimension (all six `DecisionDimension` members required)
- Unknown signal name in a dimension's weight map (not in `CANONICAL_SIGNALS`)
- Unknown confidence source (not in `CONFIDENCE_SOURCES`)
- Negative weight
- All-zero dimension (at least one positive weight per dimension required)
- Non-numeric or out-of-range value

**Runtime behavior** (low-confidence data):
- Low upstream confidences → reported as low `overall_confidence`, never raised
- Missing device type → empty `device_type` field + warning
- Empty material breakdown → warning, dimensions scored from available signals
- Zero total mass → mass fractions default to 0, no error

### Testing Strategy

- **Unit tests** — test `DecisionInferenceEngine.infer()` directly with hand-built reports and a hand-built `KnowledgeBase`. Verify:
  - Signal projection (saturation, mass fractions, identity completeness)
  - Dimension blending (weighted averages, edge cases: all-zero weights, single signal)
  - Confidence aggregation (filtering by floor, all dropped → 0)
  - Determinism (same inputs → byte-identical output when `created_at=None`)
  - Reasoning and warnings generation
- **Loader tests** — test `load_knowledge()` with valid and malformed catalogues. Verify:
  - Valid catalogue loads successfully
  - Every structural violation raises `DecisionKnowledgeError` with the correct `code` and descriptive `details`
- **Config tests** — test `DecisionConfig.from_settings()` maps environment correctly
- **Service tests** — test `DecisionService.analyze()` end-to-end with injected fixed clock, verify provenance stamping

### Design Rationale

**Why normalized evidence only?** — The decision-knowledge report deliberately contains no recommended action. Separating "what the evidence weighs" (M2.1) from "what should be done" (M2.2) keeps the two concerns independent and auditable. The evidence can be reviewed and tuned without touching policy rules, and policy rules can be changed without re-scoring devices.

**Why external catalogue?** — The per-dimension signal weights, confidence weights, and saturation constants are **knowledge**, not logic. They will be tuned as the upstream engines evolve and as real triage data accumulates. Keeping them in an external YAML file (versioned and stamped onto every report) means they can be reviewed and changed without redeploying the engine.

**Why separate confidence axis?** — Confidence is a measure of uncertainty in the evidence, not a measure of the evidence itself. A high-hazard device with low confidence is still high-hazard; the confidence communicates "verify this manually" rather than damping the hazard score. Keeping confidence separate preserves the evidence's meaning and makes the report easier to reason about.

**Why 6-decimal precision?** — Matches the upstream engines (M1.7–M1.11) so all engines' numbers compare cleanly. Higher precision would suggest false accuracy; lower precision would lose signal when blending many weighted terms.

### Extension Strategy

The engine is extended by editing the external knowledge catalogue (`decision/data/knowledge.yaml`), not by modifying code:

- **Reweight a dimension** — change signal weights in the `dimensions` block, bump the catalogue `version`.
- **Reweight confidence** — change source weights in the `confidence` block, bump the catalogue `version`.
- **Retune saturation** — adjust the four constants in the `normalization` block, bump the catalogue `version`.

Adding a **new signal** requires code changes (project the new signal in `DecisionInferenceEngine._signals()`, add it to `CANONICAL_SIGNALS`, update the loader docstring). Adding a **new dimension** requires code changes (add the enum member to `DecisionDimension`, update `DecisionKnowledgeReport` fields, add the dimension to the catalogue, update the loader to require it).

### Knowledge Engine Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│          DECISION KNOWLEDGE ENGINE (M2.1) ARCHITECTURE                │
│                                                                        │
│  INPUTS (5 upstream reports)                                          │
│  ─────────────────────────────                                        │
│  DeviceContext            (eco_id, identity, device_type, conflicts)  │
│  RecoverabilityReport     (3 scores, hazard, confidence)              │
│  ComponentReport          (components, overall_confidence)            │
│  MaterialReport           (materials, masses, confidence)             │
│  EnvironmentalImpactReport (savings, circularity, critical, conf)    │
│                                                                        │
│                               ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  STAGE 1: PROJECT SIGNALS                                        │ │
│  │  ────────────────────────                                        │ │
│  │  Map 5 upstream reports → 11 normalized [0,1] signals:           │ │
│  │                                                                   │ │
│  │  • repairability (pass through)                                  │ │
│  │  • reusability (pass through)                                    │ │
│  │  • recyclability (pass through)                                  │ │
│  │  • circularity_index (pass through)                              │ │
│  │  • hazard_severity (enum → 0.0/0.25/0.4/0.7/1.0)                │ │
│  │  • hazard_reduction (pass through)                               │ │
│  │  • hazardous_mass_fraction (computed: hazardous/total)           │ │
│  │  • critical_material_presence (saturated: recovery/ceiling)      │ │
│  │  • recoverable_mass_fraction (computed: recoverable/total)       │ │
│  │  • environmental_savings (mean of 3 saturated resource axes)     │ │
│  │  • identity_completeness (fraction of 4 strong fields present)   │ │
│  │                                                                   │ │
│  │  All clamped to [0,1], rounded to 6 decimals                     │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                               ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  STAGE 2: BLEND DIMENSIONS                                       │ │
│  │  ─────────────────────────                                       │ │
│  │  For each of 6 decision dimensions:                              │ │
│  │                                                                   │ │
│  │  1. Read signal→weight map from KnowledgeBase                    │ │
│  │  2. Compute: dimension_score =                                   │ │
│  │     clamp_round(Σ(signal_value × weight) / Σ(weight))            │ │
│  │  3. Build DimensionEvidence(dimension, score, signals, reason)   │ │
│  │                                                                   │ │
│  │  Dimensions scored:                                              │ │
│  │  • REPAIRABILITY (repairability × 0.8 + identity × 0.2)          │ │
│  │  • REUSABILITY (reusability × 0.8 + identity × 0.2)              │ │
│  │  • RECYCLING (recyclability × 0.55 + circularity × 0.25 + ...)   │ │
│  │  • HAZARD (hazard_severity × 0.6 + hazardous_frac × 0.25 + ...) │ │
│  │  • ENVIRONMENTAL_PRIORITY (savings × 0.45 + circularity × ...)   │ │
│  │  • MATERIAL_VALUE (critical × 0.5 + recoverable × 0.25 + ...)    │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                               ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  STAGE 3: AGGREGATE CONFIDENCE (separate axis)                   │ │
│  │  ──────────────────────────────────────────                     │ │
│  │  Blend 5 upstream confidences with catalogue weights:            │ │
│  │                                                                   │ │
│  │  • recoverability.confidence × 0.20                              │ │
│  │  • components.overall_confidence × 0.15                          │ │
│  │  • materials.overall_confidence × 0.25                           │ │
│  │  • environmental.confidence × 0.25                               │ │
│  │  • fusion (context).confidence × 0.15                            │ │
│  │                                                                   │ │
│  │  Filter: drop sources at/below min_confidence floor (0.05)       │ │
│  │  overall_confidence = clamp_round(Σ(conf × wt) / Σ(wt))          │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                               ↓                                        │
│  OUTPUT: DecisionKnowledgeReport                                      │
│  ────────────────────────────────                                     │
│  • 6 dimension scores (each [0,1])                                    │
│  • overall_confidence (separate axis, never scales scores)            │
│  • 6 DimensionEvidence records (score + ordered signals + reason)    │
│  • Ordered reasoning (3+ sentences)                                   │
│  • Ordered warnings (0+ cautions)                                     │
│  • Provenance: eco_id, device_type, engine v1.0.0, knowledge v1.0.0  │
│  • Optional created_at (when clock injected)                          │
│                                                                        │
│  EXTERNAL CATALOGUE: decision/data/knowledge.yaml                     │
│  ────────────────────────────────────────────                        │
│  • version: "1.0.0"                                                   │
│  • normalization: 4 saturation constants (carbon, energy, water,     │
│    critical recovery) — all strictly positive                         │
│  • dimensions: 6 required maps (signal→weight), all ≥0, ≥1 positive  │
│  • confidence: 5 source weights, all ≥0, ≥1 positive                 │
│                                                                        │
│  Loader validates: all dimensions present, all signals known, all     │
│  weights ≥0, ≥1 positive weight per dimension, all constants > 0.     │
│  Malformed → DecisionKnowledgeError at load time.                     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 6. Circular Decision Engine (M2.2)

### Purpose

The Circular Decision Engine evaluates a versioned, precedence-ordered policy rule catalogue against the upstream decision-knowledge evidence and recommends one end-of-life action: `repair`, `refurbish`, `recycle`, `manual_review`, or `hazardous_disposal`. It is the first stage in the pipeline that produces an **actionable recommendation** rather than normalized evidence.

Every recommendation is auditable: the engine retains every rule that fired, their precedence order, and which rule won (lowest precedence). The confidence in the recommendation is a separate axis (propagated from upstream and damped by rule confidence factors) that never changes the action itself.

### Responsibilities

1. **Project** — map the four upstream reports (`DeviceContext`, `DecisionKnowledgeReport`, `RecoverabilityReport`, `EnvironmentalImpactReport`) onto sixteen normalized `[0, 1]` decision signals (the canonical vocabulary defined in `CANONICAL_SIGNALS`).

2. **Match** — evaluate each rule in the precedence-ordered catalogue: a rule fires when all its conditions hold (each condition tests one signal against a threshold with an operator: `gte`, `lte`, `gt`, `lt`).

3. **Aggregate** — select the winning action from the fired rules: the rule with the **lowest precedence** (highest priority) wins. If no rule fires, the catalogue's mandatory `default` fallback is used. Confidence is damped multiplicatively by each fired rule's `confidence_factor`.

4. **Explain** — generate ordered human-readable reasoning and warnings describing which rules fired, which won, and what caveats apply.

### Inputs

- `DeviceContext` (M1.7) — fused identity, device type, eco_id, conflict flags.
- `DecisionKnowledgeReport` (M2.1) — six normalized decision dimensions, overall confidence.
- `RecoverabilityReport` (M1.8) — hazard level, disassembly score.
- `EnvironmentalImpactReport` (M1.11) — circularity index, hazard reduction score.
- `RuleCatalogue` (external) — versioned, precedence-ordered policy rules + mandatory default fallback.

### Outputs

`DecisionReport` containing:

- `recommended_action` — one of `repair`, `refurbish`, `recycle`, `manual_review`, `hazardous_disposal`
- `priority` — action urgency: `high`, `medium`, `low`
- `confidence` — aggregated confidence in the recommendation (damped by rule confidence factors)
- `triggered_rules` — ordered list of every rule that fired (each with `rule_id`, `action`, `priority`, `precedence`, `reason`, `won` flag)
- `reasoning` — ordered human-readable explanations
- `warnings` — ordered operator-facing cautions
- Provenance: `device_type`, `eco_id`, `engine_version`, `rules_version`, `created_at`

### Internal Workflow

The engine implements a three-stage pipeline:

**Stage 1: Project** — Map the four upstream reports onto sixteen normalized `[0, 1]` decision signals (the canonical vocabulary defined in `CANONICAL_SIGNALS`):

From `DecisionKnowledgeReport`:
- `repairability` ← `knowledge.repairability_score`
- `reusability` ← `knowledge.reusability_score`
- `recyclability` ← `knowledge.recycling_score`
- `hazard` ← `knowledge.hazard_score`
- `environmental_priority` ← `knowledge.environmental_priority`
- `material_value` ← `knowledge.material_value_score`
- `overall_confidence` ← `knowledge.overall_confidence`

From `RecoverabilityReport`:
- `disassembly_score` ← `recoverability.disassembly_score`

From `EnvironmentalImpactReport`:
- `circularity_index` ← `environmental.circularity_index`
- `hazard_reduction_score` ← `environmental.hazard_reduction_score`

Computed/mapped:
- `hazard_severity` ← `recoverability.hazard_level` mapped to `{NONE:0.0, UNKNOWN:0.25, LOW:0.4, MEDIUM:0.7, HIGH:1.0}`
- `has_conflicts` ← `context.has_conflicts` (boolean → 1.0 if true, 0.0 if false)
- `identity_completeness` ← count of strong identity fields present / 4
- `upstream_forced_action` ← special signal: 1.0 when `recoverability.recommended_action` is `hazardous_disposal` or `manual_review`, else 0.0
- `upstream_forced_disposal` ← 1.0 when `recoverability.recommended_action == hazardous_disposal`, else 0.0
- `upstream_forced_review` ← 1.0 when `recoverability.recommended_action == manual_review`, else 0.0

All signals clamped to `[0, 1]` and rounded to 6 decimals.

**Stage 2: Match** — Evaluate each rule in precedence order (lowest precedence number first):

For each rule:
1. Check all its conditions: each condition tests one signal against a threshold with an operator (`gte`, `lte`, `gt`, `lt`).
2. If all conditions hold, the rule **fires**: record it as a `TriggeredRule`.
3. Continue checking all rules (rules do not short-circuit; the engine retains every fired rule for auditability).

**Stage 3: Aggregate** — Select the winning action and compute final confidence:

1. **Select winner**: Among all fired rules, the rule with the **lowest precedence** (highest priority) wins. Mark it with `won=True`; all others have `won=False`.
2. If no rule fired, use the catalogue's mandatory `default` fallback (action + priority).
3. **Damp confidence**: Start with `knowledge.overall_confidence`. For each fired rule (in precedence order), multiply by the rule's `confidence_factor` (range `[0, 1]`). Clamp to `[0, 1]` and round to 6 decimals.

Formula: `confidence = knowledge.overall_confidence × Π(fired_rule.confidence_factor)`

4. **Emit warning if low**: If final confidence ≤ `config.min_confidence`, append a low-confidence warning to the report.

### Configuration

`CircularConfig` (immutable, frozen, slotted):
- `rules_path` (string, default `"circular/data/rules.yaml"`) — locator of the external rule catalogue, resolved relative to `device_ai` package root when not absolute.
- `min_confidence` (float, default `0.35`, range `[0, 1]`) — confidence floor; recommendations at or below this trigger a low-confidence warning.
- `identity_field_count` (int, default `4`) — number of strong identity fields (model, serial, IMEI, MAC) the engine normalizes identity completeness against.

Mapped from environment via `CircularConfig.from_settings(settings)`:
- `CIRCULAR_RULES_PATH` → `rules_path`
- `CIRCULAR_MIN_CONFIDENCE` → `min_confidence`

### Collaborators

- **Upstream reports**: `DeviceContext` (M1.7), `DecisionKnowledgeReport` (M2.1), `RecoverabilityReport` (M1.8), `EnvironmentalImpactReport` (M1.11)
- **External catalogue**: `circular/data/rules.yaml` (version 1.0.0, 10 rules + default) — loaded by `load_rules()` into immutable `RuleCatalogue`
- **Decision engine**: `CircularDecisionEngine` — pure deterministic rule evaluator, no I/O
- **Service**: `CircularService` — constructor-injectable façade that loads the catalogue once, stamps provenance, and optionally injects a clock

### Dependency Graph

```
DeviceContext ────────┐
DecisionKnowledgeReport ──┤
RecoverabilityReport ──┤──→ CircularDecisionEngine ──→ DecisionReport
EnvironmentalImpactReport ─┘              ↑
                                           │
                                    RuleCatalogue
                                    (external YAML)
```

### Error Handling

**Load-time failures** (malformed catalogue) raise `CircularRuleError`:
- Missing or empty `version`
- Missing or empty `rules` list
- Missing or empty `default` fallback
- Duplicate `rule_id`
- Duplicate `precedence` (each rule must have a unique precedence)
- Unknown signal name in a condition (not in `CANONICAL_SIGNALS`)
- Unknown operator (not in `gte`, `lte`, `gt`, `lt`)
- Unknown action (not in `repair`, `refurbish`, `recycle`, `manual_review`, `hazardous_disposal`)
- Unknown priority (not in `high`, `medium`, `low`)
- Threshold outside `[0, 1]`
- Rule with zero conditions (each rule must have ≥1 condition)
- `confidence_factor` outside `[0, 1]`

**Runtime behavior** (low-confidence data):
- No rules fire → default fallback used, never an error
- Low confidence → reported as low `confidence`, warning emitted, action unchanged
- Missing device type → empty `device_type` field, no error
- Conflicting upstream signals → reported via `has_conflicts` signal, rules decide

### Testing Strategy

- **Unit tests** — test `CircularDecisionEngine.decide()` directly with hand-built reports and a hand-built `RuleCatalogue`. Verify:
  - Signal projection (all 16 signals, edge cases: hazard enum, boolean conflict, identity completeness)
  - Rule matching (each operator, threshold boundaries, multi-condition AND logic)
  - Winner selection (lowest precedence wins, default when no rules fire)
  - Confidence damping (multiplicative, clamped to `[0, 1]`)
  - Determinism (same inputs → byte-identical output when `created_at=None`)
  - Reasoning and warnings generation
- **Loader tests** — test `load_rules()` with valid and malformed catalogues. Verify:
  - Valid catalogue loads successfully
  - Every structural violation raises `CircularRuleError` with the correct `code` and descriptive `details`
- **Config tests** — test `CircularConfig.from_settings()` maps environment correctly
- **Service tests** — test `CircularService.decide()` end-to-end with injected fixed clock, verify provenance stamping

### Design Rationale

**Why lowest precedence wins?** — In a multi-rule system where rules can fire simultaneously, the precedence mechanism ensures a deterministic, auditable outcome. Lowest precedence (highest priority) means the most critical rules (hazard, identity conflicts) win over optimization rules (repair vs recycle). This makes the catalogue easy to reason about: rules at the top of the list (lower precedence numbers) override rules at the bottom.

**Why external catalogue?** — The policy rules are **business logic**, not inference logic. They will be tuned as real triage data accumulates, as regulatory requirements change, and as the upstream scoring engines evolve. Keeping them in an external YAML file (versioned and stamped onto every report) means policy can be reviewed and changed by domain experts without redeploying the engine.

**Why confidence damping?** — Each rule carries a `confidence_factor` that communicates "how confident should the system be when this rule fires?" A rule like `identity_conflict_review` (confidence factor 0.85) signals "this device needs manual review, but we're not 100% certain" — the confidence is damped by 15% when that rule fires. This preserves the upstream confidence signal while layering in rule-specific uncertainty.

**Why retain all fired rules?** — Retaining every rule that fired (not just the winner) makes the recommendation auditable: an operator can see which rules would have recommended different actions, their precedence, and why the winner was chosen. This is critical for trust and debugging.

### Extension Strategy

The engine is extended by editing the external rule catalogue (`circular/data/rules.yaml`), not by modifying code:

- **Add a new rule** — insert a new rule with a unique `rule_id`, unique `precedence`, and conditions/action/priority. Bump the catalogue `version`.
- **Reorder rules** — change precedences to reorder which rule wins when multiple fire. Lower precedence = higher priority.
- **Tune confidence** — change `confidence_factor` (range `[0, 1]`) to damp confidence more or less when a rule fires.
- **Change default** — edit the `default` fallback (action + priority) to change the outcome when no rules fire.

Adding a **new signal** requires code changes (project the new signal in `CircularDecisionEngine._project_signals()`, add it to `CANONICAL_SIGNALS`, update the loader docstring). Adding a **new action** or **priority** requires code changes (add the enum member, update the loader's allowed sets).

### Circular Decision Pipeline Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│        CIRCULAR DECISION ENGINE (M2.2) ARCHITECTURE                   │
│                                                                        │
│  INPUTS (4 upstream reports)                                          │
│  ────────────────────────────                                         │
│  DeviceContext            (identity, device_type, conflicts, eco_id)  │
│  DecisionKnowledgeReport  (6 dimensions, overall_confidence)          │
│  RecoverabilityReport     (hazard_level, recommended_action, disasm) │
│  EnvironmentalImpactReport (circularity, hazard_reduction)           │
│                                                                        │
│                               ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  STAGE 1: PROJECT SIGNALS (16 normalized [0,1] signals)          │ │
│  │  ────────────────────────────────────────────────────────────────│ │
│  │  From DecisionKnowledgeReport:                                   │ │
│  │    repairability, reusability, recyclability, hazard,            │ │
│  │    environmental_priority, material_value, overall_confidence    │ │
│  │                                                                   │ │
│  │  From RecoverabilityReport:                                      │ │
│  │    hazard_severity (enum→0.0/0.25/0.4/0.7/1.0), disassembly     │ │
│  │                                                                   │ │
│  │  From EnvironmentalImpactReport:                                 │ │
│  │    circularity_index, hazard_reduction_score                     │ │
│  │                                                                   │ │
│  │  Computed:                                                        │ │
│  │    has_conflicts (bool→1.0/0.0), identity_completeness (0-4/4),  │ │
│  │    upstream_forced_disposal, upstream_forced_review,             │ │
│  │    upstream_forced_action                                         │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                               ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  STAGE 2: MATCH RULES (precedence-ordered evaluation)            │ │
│  │  ────────────────────────────────────────────────────────────────│ │
│  │  For each rule (in precedence order, 10→100):                    │ │
│  │    1. Check all conditions (AND logic):                          │ │
│  │       condition: signal operator threshold                       │ │
│  │       operators: gte, lte, gt, lt                                │ │
│  │    2. If ALL conditions hold → rule FIRES                        │ │
│  │    3. Record as TriggeredRule(id, action, priority, precedence,  │ │
│  │       reason, confidence_factor, won=False)                      │ │
│  │    4. Continue (no short-circuit; retain all fired rules)        │ │
│  │                                                                   │ │
│  │  Example rules (circular/data/rules.yaml v1.0.0):                │ │
│  │    precedence 10:  upstream_forced_hazardous_disposal            │ │
│  │    precedence 20:  high_hazard_severity                          │ │
│  │    precedence 30:  upstream_forced_manual_review (cf=0.85)       │ │
│  │    precedence 40:  identity_conflict_review (cf=0.85)            │ │
│  │    precedence 50:  low_confidence_review                         │ │
│  │    precedence 60:  high_value_refurbish                          │ │
│  │    precedence 70:  refurbish                                     │ │
│  │    precedence 80:  repair                                        │ │
│  │    precedence 90:  high_value_recycle                            │ │
│  │    precedence 100: recycle                                       │ │
│  │    default:        manual_review / low (when no rules fire)      │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                               ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  STAGE 3: AGGREGATE WINNER & CONFIDENCE                          │ │
│  │  ────────────────────────────────────────────────────────────────│ │
│  │  1. SELECT WINNER:                                               │ │
│  │     • Among all fired rules, LOWEST precedence wins (highest     │ │
│  │       priority)                                                   │ │
│  │     • Mark winning rule with won=True; others won=False          │ │
│  │     • If no rules fired, use catalogue default fallback          │ │
│  │                                                                   │ │
│  │  2. DAMP CONFIDENCE:                                             │ │
│  │     Start: confidence = knowledge.overall_confidence             │ │
│  │     For each fired rule (precedence order):                      │ │
│  │       confidence *= rule.confidence_factor                       │ │
│  │     Clamp to [0,1], round to 6 decimals                          │ │
│  │                                                                   │ │
│  │  3. EMIT WARNING IF LOW:                                         │ │
│  │     If confidence ≤ config.min_confidence (0.35) → warning       │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                               ↓                                        │
│  OUTPUT: DecisionReport                                               │
│  ───────────────────────                                              │
│  • recommended_action (repair/refurbish/recycle/manual_review/        │
│    hazardous_disposal)                                                │
│  • priority (high/medium/low)                                         │
│  • confidence (damped from upstream)                                  │
│  • triggered_rules (ordered, each with won flag)                      │
│  • reasoning (ordered, 3+ sentences)                                  │
│  • warnings (ordered, 0+ cautions)                                    │
│  • Provenance: device_type, eco_id, engine v1.0.0, rules v1.0.0      │
│                                                                        │
│  EXTERNAL CATALOGUE: circular/data/rules.yaml                         │
│  ──────────────────────────────────────────                          │
│  • version: "1.0.0"                                                   │
│  • rules: 10 precedence-ordered policy rules                          │
│  • default: manual_review / low (mandatory fallback)                  │
│  • Each rule: unique id, unique precedence, ≥1 condition, action,    │
│    priority, reason, optional confidence_factor [0,1]                 │
│                                                                        │
│  Loader validates: unique ids, unique precedences, known signals,     │
│  known operators, known actions/priorities, thresholds in [0,1],      │
│  ≥1 condition per rule, required default fallback.                    │
│  Malformed → CircularRuleError at load time.                          │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 7. Device Passport Core (M2.3)

### Purpose

The Device Passport Core assembles a canonical, immutable `DevicePassport` document from the upstream reports the pipeline already produced. It performs **no inference of its own**: every value it holds is copied or plainly summarized from an upstream report, so the passport is a faithful, auditable snapshot rather than a re-interpretation.

The passport is the authoritative document that downstream consumers (integrity engine M2.4, trust engine M2.5, blockchain ledger M3.1) operate on. Its structural contract lives in an external, versioned schema; its builder is deterministic; and its JSON serialization is canonical, so the same inputs always yield byte-identical output.

### Responsibilities

1. **Summarize** — extract key values from five upstream reports into eight section dataclasses:
   - `DeviceIdentity` (5 fields: brand, model, serial_number, imei, mac_address)
   - `Classification` (3 fields: device_type, confidence, has_conflicts)
   - `DecisionSummary` (5 fields: recommended_action, priority, confidence, winning_rule_id, triggered_count)
   - `MaterialSummary` (5 fields: material_count, total_mass_g, recoverable_mass_g, hazardous_mass_g, confidence)
   - `EnvironmentalSummary` (8 fields: carbon/energy/water saved, landfill diversion, critical material recovery, circularity index, hazard reduction score, confidence)
   - `FingerprintSummary` (5 fields: fingerprint base64, dimension, encoder_name, encoder_version, metric)
   - `ConfidenceSummary` (5 fields: identity/decision/material/environmental confidences, overall mean)
   - `PassportMetadata` (11 fields: engine versions, schema version, created_at)

2. **Compose confidence** — compute the mean of four upstream confidences (identity/classification, decision, material, environmental) as the passport's overall confidence.

3. **Identify** — generate a content-addressed passport ID from a hash of the device's identity and action (format: `ET-PP-` + 12-character uppercase SHA-256 prefix).

4. **Narrate** — aggregate ordered reasoning and warnings from the upstream reports.

5. **Validate** — check the assembled passport against the external schema before returning (raises `PassportValidationError` if validation fails).

### Inputs

- `DeviceContext` (M1.7) — fused identity, device type, confidence, conflict flags, eco_id.
- `DecisionReport` (M2.2) — recommended action, priority, confidence, fired rules.
- `MaterialReport` (M1.10) — material breakdown, masses, confidence.
- `EnvironmentalImpactReport` (M1.11) — carbon/energy/water saved, circularity, critical material, hazard reduction, confidence.
- `DeviceFingerprint` (M1.5, optional) — base64 fingerprint, dimension, encoder metadata, metric.
- `PassportSchema` (external) — structural contract declaring required sections, fields, and confidence field ranges.

### Outputs

`DevicePassport` containing 13 sections:

1. `passport_id` (string) — content-addressed identifier, format `ET-PP-{12-char SHA-256 prefix}`
2. `passport_version` (string) — semantic version (default `1.0.0`)
3. `eco_id` (string) — carried from context (empty when no fingerprint)
4. `device_identity` (object) — 5 fields: brand, model, serial_number, imei, mac_address
5. `classification` (object) — device_type, confidence, has_conflicts
6. `decision_summary` (object) — recommended_action, priority, confidence, winning_rule_id, triggered_count
7. `material_summary` (object) — material_count, total_mass_g, recoverable_mass_g, hazardous_mass_g, confidence
8. `environmental_summary` (object) — 8 fields: carbon/energy/water saved, landfill diversion, critical recovery, circularity, hazard reduction, confidence
9. `fingerprint_summary` (object) — fingerprint base64, dimension, encoder_name, encoder_version, metric (all empty when no fingerprint)
10. `confidence_summary` (object) — identity_confidence, decision_confidence, material_confidence, environmental_confidence, overall (mean of 4)
11. `metadata` (object) — 11 provenance fields: passport/schema/fusion/decision/material/environmental engine versions, decision/material/environmental catalogue versions, source_image_count, created_at
12. `reasoning` (array) — ordered human-readable explanations
13. `warnings` (array) — ordered operator-facing cautions

Plus two methods: `to_dict()` → plain dict; `to_json(*, indent=None)` → canonical JSON string.

### Internal Workflow

The builder implements a four-stage pipeline:

**Stage 1: Summarize** — Extract values from five upstream reports into eight section dataclasses. Every value is copied or plainly computed; no inference:

- `DeviceIdentity` ← `context` (brand, model, serial_number, imei, mac_address)
- `Classification` ← `context` (device_type, confidence, has_conflicts)
- `DecisionSummary` ← `decision` (action, priority, confidence, winning rule id, triggered count)
- `MaterialSummary` ← `materials` (count, masses, confidence)
- `EnvironmentalSummary` ← `environmental` (8 fields)
- `FingerprintSummary` ← `fingerprint` when present, else all-empty placeholders
- `ConfidenceSummary` ← computed below (stage 2)
- `PassportMetadata` ← provenance from all reports + config

**Stage 2: Compose confidence** — Compute overall confidence as the mean of four upstream confidences:

```
overall = mean(
  context.confidence,           # identity/classification
  decision.confidence,          # circular decision
  materials.overall_confidence, # material report
  environmental.confidence      # environmental report
)
```

Rounded to 6 decimals (`_CONFIDENCE_PRECISION = 6`).

**Stage 3: Identify** — Generate content-addressed passport ID from a hash of identity and action:

1. Concatenate these fields with `\x1f` separator (ASCII unit separator): `eco_id`, `fingerprint.fingerprint`, `classification.device_type`, `device_identity.brand`, `device_identity.model`, `device_identity.serial_number`, `device_identity.imei`, `device_identity.mac_address`, `decision_summary.recommended_action`.
2. Compute SHA-256 hash of the UTF-8 bytes.
3. Take the first 12 characters of the uppercase hex digest.
4. Prepend `ET-PP-` prefix.

Formula: `passport_id = "ET-PP-" + short_hash(joined_fields, length=12)`

Because the ID is deterministic and content-addressed, the same device + action always yields the same ID (no timestamp in the hash).

**Stage 4: Narrate** — Aggregate ordered reasoning and warnings from upstream reports:

- Reasoning: 3 base sentences + per-section summaries from `decision` and `environmental`
- Warnings: merge warnings from `decision`, `materials`, `environmental`; truncate each list to `config.max_reasoning` / `config.max_warnings` (default 32 each)

**Stage 5: Validate** (in service, not builder) — Check the assembled passport's dict representation against the loaded schema via `validate_passport(passport.to_dict(), schema)`. If validation fails, raise `PassportValidationError` with ordered errors/warnings. The passport never leaves the service invalid.

### Configuration

`PassportConfig` (immutable, frozen, slotted):
- `schema_path` (string, default `"passport/data/schema.yaml"`) — locator of the external schema, resolved relative to `device_ai` package root when not absolute.
- `passport_version` (string, default `"1.0.0"`) — semantic version stamped onto every passport as its `passport_version`.
- `max_reasoning` (int, default `32`) — maximum reasoning entries retained from upstream.
- `max_warnings` (int, default `32`) — maximum warning entries retained from upstream.

Mapped from environment via `PassportConfig.from_settings(settings)`:
- `PASSPORT_SCHEMA_PATH` → `schema_path`
- `PASSPORT_VERSION` → `passport_version`

### Collaborators

- **Upstream reports**: `DeviceContext` (M1.7), `DecisionReport` (M2.2), `MaterialReport` (M1.10), `EnvironmentalImpactReport` (M1.11), `DeviceFingerprint` (M1.5, optional)
- **External schema**: `passport/data/schema.yaml` (version 1.0.0) — loaded by `load_schema()` into immutable `PassportSchema`
- **Builder**: `PassportBuilder` — pure deterministic assembler, no I/O
- **Validator**: `validate_passport()` — structural checker, no I/O
- **Service**: `PassportService` — constructor-injectable façade that loads the schema once, builds and validates, stamps provenance, optionally injects a clock

### Dependency Graph

```
DeviceContext ──────┐
DecisionReport ──┤
MaterialReport ──┤──→ PassportBuilder ──→ DevicePassport ──→ validate_passport
EnvironmentalImpactReport ─┤                                         ↑
DeviceFingerprint (opt) ─┘                                           │
                                                              PassportSchema
                                                              (external YAML)
```

### Error Handling

**Load-time failures** (malformed schema) raise `PassportSchemaError`:
- Missing or empty `version`
- Missing or empty `sections`
- Duplicate section name
- Unknown `SectionKind` (not `string`, `object`, `array`)
- Object section with no `fields`
- Duplicate field in a section
- Confidence field not in the section's own `fields` list

**Validation failures** (malformed passport) raise `PassportValidationError`:
- Missing required section
- Section present but wrong kind (e.g., string instead of object)
- Object section missing required field
- Confidence field value not numeric or outside `[0, 1]`

**Runtime behavior** (low-confidence data):
- Empty device type → empty `classification.device_type`, no error
- No fingerprint → all-empty `fingerprint_summary` placeholders, no error
- Zero materials → `material_count=0`, masses=0, no error

### Testing Strategy

- **Unit tests** — test `PassportBuilder.assemble()` directly with hand-built reports. Verify:
  - All 13 sections populated correctly (field mapping, empty placeholders when optional data missing)
  - Confidence composition (mean of 4, rounded to 6 decimals)
  - Passport ID generation (deterministic, content-addressed, no timestamp)
  - Reasoning/warnings aggregation (truncation at max limits)
  - Determinism (same inputs → byte-identical output when `created_at=None`)
- **Validator tests** — test `validate_passport()` with valid and malformed passport dicts. Verify:
  - Valid passport passes
  - Every structural violation detected (missing section, wrong kind, missing field, confidence out of range)
- **Loader tests** — test `load_schema()` with valid and malformed schemas. Verify:
  - Valid schema loads successfully
  - Every structural violation raises `PassportSchemaError` with the correct `code` and descriptive `details`
- **Config tests** — test `PassportConfig.from_settings()` maps environment correctly
- **Service tests** — test `PassportService.build()` end-to-end with injected fixed clock, verify provenance stamping and that `PassportValidationError` is raised for invalid passports

### Design Rationale

**Why no inference?** — The passport is a **composition**, not a new inference. Every value it carries is copied or plainly summarized from an upstream report. This keeps the passport a faithful snapshot: an operator can trace every field back to the report that produced it. Adding inference here would break that traceability and make the passport a re-interpretation rather than a document.

**Why external schema?** — The passport's structural contract (which sections, which fields, which confidence ranges) will evolve as the platform matures. Keeping it in an external YAML file (versioned and stamped onto every passport) means the contract can be reviewed and changed without redeploying the builder. The schema is documentation that the validator enforces.

**Why content-addressed ID?** — A content-addressed ID (hash of identity + action, no timestamp) is **stable** for a given device: the same device photographed twice yields the same passport ID if its identity and recommended action haven't changed. This enables deduplication, idempotent operations, and easier reasoning about "has this device been seen before?" The ID is not a primary key (the blockchain ledger M3.1 owns persistence); it's a fingerprint.

**Why validate before returning?** — The builder is deterministic and the schema is strict, so a validation failure is an **engine fault** (builder bug, schema mismatch, or upstream report producing out-of-contract data). Catching it at service exit time (rather than letting it escape to the blockchain or trust engines) surfaces the fault immediately and prevents malformed passports from propagating.

### Extension Strategy

The passport is extended by editing the external schema (`passport/data/schema.yaml`), not by modifying code:

- **Add a new section** — insert a new section with `kind` and `fields`, bump the schema `version`.
- **Add fields to a section** — append new field names to an existing section's `fields` list, bump the schema `version`.
- **Mark confidence fields** — add field names to a section's `confidence_fields` list (validator will enforce `[0, 1]` range).
- **Mark optional section** — set `required: false` on a section (validator will emit warning rather than error when missing).

Adding a **new section** that the builder must populate requires code changes (update `PassportBuilder.assemble()` to extract the new section from upstream reports, add the section dataclass to `passport/models.py`, update the builder's section list).

### Passport Assembly Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│         DEVICE PASSPORT CORE (M2.3) ARCHITECTURE                      │
│                                                                        │
│  INPUTS (5 upstream reports)                                          │
│  ────────────────────────────                                         │
│  DeviceContext            (identity, type, conf, eco_id, conflicts)   │
│  DecisionReport           (action, priority, conf, rules, reasoning)  │
│  MaterialReport           (materials, masses, conf, reasoning)        │
│  EnvironmentalImpactReport (savings, circularity, critical, conf)    │
│  DeviceFingerprint (opt)  (base64, dimension, encoder, metric)       │
│                                                                        │
│                               ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  STAGE 1: SUMMARIZE (extract 8 section dataclasses)              │ │
│  │  ────────────────────────────────────────────────────────────────│ │
│  │  DeviceIdentity ← context (brand, model, serial, IMEI, MAC)      │ │
│  │  Classification ← context (device_type, confidence, conflicts)   │ │
│  │  DecisionSummary ← decision (action, priority, conf, rule, cnt)  │ │
│  │  MaterialSummary ← materials (count, masses, conf)               │ │
│  │  EnvironmentalSummary ← environmental (8 fields)                 │ │
│  │  FingerprintSummary ← fingerprint when present, else all-empty   │ │
│  │  ConfidenceSummary ← computed in stage 2                         │ │
│  │  PassportMetadata ← provenance from all reports + config         │ │
│  │                                                                   │ │
│  │  NO INFERENCE: every value copied or plainly computed            │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                               ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  STAGE 2: COMPOSE CONFIDENCE (mean of 4 upstream confidences)    │ │
│  │  ────────────────────────────────────────────────────────────────│ │
│  │  overall = mean(                                                 │ │
│  │    context.confidence,           # identity/classification       │ │
│  │    decision.confidence,          # circular decision             │ │
│  │    materials.overall_confidence, # material report               │ │
│  │    environmental.confidence      # environmental report          │ │
│  │  )                                                                │ │
│  │  Rounded to 6 decimals                                           │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                               ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  STAGE 3: IDENTIFY (content-addressed passport ID)               │ │
│  │  ────────────────────────────────────────────────────────────────│ │
│  │  1. Concatenate with \x1f separator:                             │ │
│  │     eco_id, fingerprint, device_type, brand, model, serial,      │ │
│  │     imei, mac, recommended_action                                │ │
│  │  2. SHA-256 hash of UTF-8 bytes                                  │ │
│  │  3. Take first 12 chars of uppercase hex digest                  │ │
│  │  4. Prepend "ET-PP-" prefix                                      │ │
│  │                                                                   │ │
│  │  passport_id = "ET-PP-" + short_hash(joined, length=12)          │ │
│  │                                                                   │ │
│  │  STABLE: same device + action → same ID (no timestamp in hash)   │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                               ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  STAGE 4: NARRATE (aggregate reasoning & warnings)               │ │
│  │  ────────────────────────────────────────────────────────────────│ │
│  │  Reasoning: 3 base sentences + decision + environmental          │ │
│  │  Warnings: merge decision + materials + environmental            │ │
│  │  Truncate each to config.max_reasoning / max_warnings (32 each)  │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                               ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  STAGE 5: VALIDATE (before service returns)                      │ │
│  │  ────────────────────────────────────────────────────────────────│ │
│  │  validate_passport(passport.to_dict(), schema):                  │ │
│  │    • Check all required sections present                         │ │
│  │    • Check section kinds match (string/object/array)             │ │
│  │    • Check object sections have required fields                  │ │
│  │    • Check confidence fields numeric and in [0,1]                │ │
│  │    • If validation fails → PassportValidationError               │ │
│  │                                                                   │ │
│  │  Passport never leaves service invalid                           │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                               ↓                                        │
│  OUTPUT: DevicePassport (13 sections)                                 │
│  ────────────────────────────────────                                 │
│  1. passport_id (string, ET-PP-{12-char hash})                        │
│  2. passport_version (string, 1.0.0)                                  │
│  3. eco_id (string, from context)                                     │
│  4. device_identity (object, 5 fields)                                │
│  5. classification (object, 3 fields)                                 │
│  6. decision_summary (object, 5 fields)                               │
│  7. material_summary (object, 5 fields)                               │
│  8. environmental_summary (object, 8 fields)                          │
│  9. fingerprint_summary (object, 5 fields, empty when no fingerprint) │
│  10. confidence_summary (object, 5 fields, overall = mean of 4)       │
│  11. metadata (object, 11 provenance fields)                          │
│  12. reasoning (array, ordered human-readable explanations)           │
│  13. warnings (array, ordered operator-facing cautions)               │
│                                                                        │
│  Methods: to_dict() → plain dict, to_json(*, indent=None) → canonical│
│                                                                        │
│  EXTERNAL SCHEMA: passport/data/schema.yaml                           │
│  ────────────────────────────────────────                            │
│  • version: "1.0.0"                                                   │
│  • sections: 13 declarations (name, kind, fields, confidence_fields, │
│    required)                                                          │
│  • Loader validates: all sections named, no duplicates, known kinds, │
│    object sections have fields, confidence fields in own fields list  │
│  • Validator enforces: required sections present, correct kinds,      │
│    required fields present, confidence fields in [0,1]                │
│  • Malformed schema → PassportSchemaError at load time                │
│  • Malformed passport → PassportValidationError before service return │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 8. Passport Integrity Engine (M2.4)

### Purpose

The Passport Integrity Engine re-validates the assembled `DevicePassport` against an external validation rule-set, reports structural errors and warnings, and computes a deterministic SHA-256 integrity hash over the passport's canonical JSON serialization. It is a **checker**, not an assembler: it consumes a passport the pipeline already produced and reports its structural soundness.

A malformed passport is **reported** (`status=INVALID`, ordered errors), never raised. This is a deliberate asymmetry: a malformed **engine** (bad rule-set, unsupported hash algorithm) raises a typed exception; a malformed **passport** (missing section, confidence out of range) is reported as `is_valid=False` with ordered diagnostics.

### Responsibilities

1. **Validate structure** — check the passport's dict representation against the external rule-set:
   - Required sections present
   - Section kinds match (string/object/array)
   - Object sections have all required fields
   - Confidence fields are numeric and in `[0, 1]`

2. **Report errors and warnings** — collect ordered diagnostics:
   - Missing required section → error (passport becomes INVALID)
   - Missing optional section → warning (passport becomes VALID_WITH_WARNINGS)
   - Wrong section kind → error
   - Missing required field → error
   - Confidence field out of `[0, 1]` → error

3. **Compute integrity hash** — deterministic SHA-256 hash over passport's canonical JSON serialization (`passport.to_json()` with no indent, stable key order, UTF-8 bytes).

4. **Determine validation status** — map diagnostics to one of three status values:
   - `INVALID` — one or more errors present (`is_valid=False`)
   - `VALID_WITH_WARNINGS` — warnings present, no errors (`is_valid=True`)
   - `VALID` — no errors, no warnings (`is_valid=True`)

### Inputs

- `DevicePassport` (M2.3) — the assembled passport document to validate.
- `IntegrityRuleSet` (external) — validation rule-set declaring sections, required fields, confidence fields.
- `IntegrityConfig` — hash algorithm (default `sha256`).

### Outputs

`PassportIntegrityReport` containing:

- `passport_id` — carried from the passport
- `status` — `VALID`, `VALID_WITH_WARNINGS`, or `INVALID`
- `is_valid` — `True` unless status is `INVALID`
- `canonical_hash` — SHA-256 (or configured algorithm) hex digest of canonical JSON
- `hash_algorithm` — algorithm used (e.g., `sha256`)
- `schema_version` — validation rule-set version
- `passport_version` — carried from the passport
- `checked_sections` — ordered list of `CheckedSection(name, kind, present, valid)` records
- `warnings` — ordered operator-facing cautions
- `errors` — ordered structural violations
- Provenance: `rules_version`, `engine_version`, `created_at`

Plus properties: `checked_count`, `warning_count`, `error_count`.

### Internal Workflow

The engine implements a two-stage pipeline:

**Stage 1: Validate** — Check the passport's structure against the rule-set:

1. Convert `DevicePassport` to dict via `passport.to_dict()`.
2. For each section in the rule-set (in declaration order):
   - Check if section is present in passport dict.
   - If missing and `required=True` → error: "Missing required section"
   - If missing and `required=False` → warning: "Missing optional section"
   - If present, check kind matches (string/object/array) → error if mismatch
   - If object, check all `fields` present → error for each missing required field
   - If object, check all `confidence_fields` are numeric and in `[0, 1]` → error if out of range
   - Record `CheckedSection(name, kind, present=True/False, valid=True/False)`

3. Determine status:
   - If `errors` is non-empty → `INVALID`
   - If `errors` is empty and `warnings` is non-empty → `VALID_WITH_WARNINGS`
   - If both empty → `VALID`

**Stage 2: Hash** — Compute deterministic integrity hash:

1. Serialize passport to canonical JSON: `passport.to_json()` (no indent, `sort_keys=True`, stable separators, UTF-8).
2. Encode to UTF-8 bytes.
3. Hash with configured algorithm (default SHA-256) via `hash_bytes(canonical_json_bytes, algorithm=config.hash_algorithm)`.
4. Return lowercase hex digest.

If the algorithm is unsupported (not in `hashlib`), raise `PassportIntegrityRuleError`.

### Configuration

`IntegrityConfig` (immutable, frozen, slotted):
- `rules_path` (string, default `"integrity/data/rules.yaml"`) — locator of the external rule-set, resolved relative to `device_ai` package root when not absolute.
- `hash_algorithm` (string, default `"sha256"`) — digest algorithm name (any name `hashlib.new()` accepts).

Mapped from environment via `IntegrityConfig.from_settings(settings)`:
- `INTEGRITY_RULES_PATH` → `rules_path`
- `INTEGRITY_HASH_ALGORITHM` → `hash_algorithm`

### Collaborators

- **Upstream passport**: `DevicePassport` (M2.3)
- **External rule-set**: `integrity/data/rules.yaml` (version 1.0.0) — loaded by `load_rules()` into immutable `IntegrityRuleSet`
- **Validator**: `PassportValidator` — pure structural checker, no I/O
- **Hasher**: `hash_bytes()` from `utils/hashing.py` — deterministic hash computation
- **Service**: `IntegrityService` — constructor-injectable façade that loads the rule-set once, validates and hashes, stamps provenance, optionally injects a clock

### Dependency Graph

```
DevicePassport ──→ PassportValidator ──→ PassportIntegrityReport
                          ↑
                          │
                   IntegrityRuleSet
                   (external YAML)
```

### Error Handling

**Load-time failures** (malformed rule-set) raise `PassportIntegrityRuleError`:
- Missing or empty `version`
- Missing or empty `sections`
- Unknown `SectionKind` (not `string`, `object`, `array`)
- Object section with no `fields`
- Duplicate field in a section
- Confidence field not in the section's own `fields` list

**Runtime behavior** (malformed passport):
- Missing required section → error, `status=INVALID`
- Wrong section kind → error, `status=INVALID`
- Missing required field → error, `status=INVALID`
- Confidence field out of `[0, 1]` → error, `status=INVALID`
- Missing optional section → warning, `status=VALID_WITH_WARNINGS`
- No errors, no warnings → `status=VALID`

**Key asymmetry**: A malformed **rule-set** (engine fault) is **raised** as `PassportIntegrityRuleError`. A malformed **passport** (data fault) is **reported** as `is_valid=False` with ordered errors, never raised.

### Testing Strategy

- **Unit tests** — test `PassportValidator.validate()` directly with hand-built passport dicts and a hand-built `IntegrityRuleSet`. Verify:
  - Every validation rule (missing required, missing optional, wrong kind, missing field, confidence out of range)
  - Status determination (errors → INVALID, warnings → VALID_WITH_WARNINGS, neither → VALID)
  - `CheckedSection` records (present/absent, valid/invalid flags)
  - Hash computation (deterministic, algorithm parameter respected)
  - Unsupported algorithm raises `PassportIntegrityRuleError`
- **Loader tests** — test `load_rules()` with valid and malformed rule-sets. Verify:
  - Valid rule-set loads successfully
  - Every structural violation raises `PassportIntegrityRuleError` with the correct `code` and descriptive `details`
- **Config tests** — test `IntegrityConfig.from_settings()` maps environment correctly
- **Service tests** — test `IntegrityService.validate()` end-to-end with injected fixed clock, verify provenance stamping

### Design Rationale

**Why report rather than raise?** — The integrity engine validates **data** (the passport), not code. A structurally invalid passport is a **verdict** about the data, not an engine fault. Reporting it as `is_valid=False` with ordered diagnostics allows downstream consumers (trust engine M2.5, blockchain ledger M3.1) to decide how to handle low-integrity passports. Raising an exception would force the orchestrating code to catch and inspect it, which breaks the clean report-based flow.

**Why external rule-set?** — The validation contract (which sections are required, which fields are confidence fields) will evolve as the passport structure matures. Keeping it in an external YAML file (versioned and stamped onto every report) means the contract can be reviewed and changed without redeploying the validator. The rule-set is documentation that the validator enforces.

**Why canonical hash?** — The integrity hash is computed over the passport's canonical JSON serialization (`sort_keys=True`, stable separators, no whitespace variation). This ensures that the same passport always yields the same hash, regardless of how it was serialized in memory. The hash is a fingerprint: any mutation to the passport (a changed action, a tampered confidence, a missing field) produces a different hash, making tampering detectable.

**Why SHA-256?** — SHA-256 is cryptographically strong, widely supported, and produces a 64-character hex digest that is globally unique for practical purposes. The algorithm is configurable (via `config.hash_algorithm`) so it can be upgraded if needed without code changes.

### Extension Strategy

The engine is extended by editing the external rule-set (`integrity/data/rules.yaml`), not by modifying code:

- **Mark a section optional** — set `required: false` on a section (validator will emit warning rather than error when missing).
- **Add a new section** — insert a new section with `kind`, `fields`, and optional `confidence_fields`. Bump the rule-set `version`.
- **Add confidence fields** — append field names to a section's `confidence_fields` list (validator will enforce `[0, 1]` range).

Adding a **new validation rule** (beyond structural checks) requires code changes (update `PassportValidator` to implement the rule).

### Integrity Validation Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│     PASSPORT INTEGRITY ENGINE (M2.4) ARCHITECTURE                     │
│                                                                        │
│  INPUT: DevicePassport (M2.3, 13 sections)                            │
│  ────────────────────────────────────────                             │
│                               ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  STAGE 1: VALIDATE STRUCTURE                                     │ │
│  │  ────────────────────────────                                    │ │
│  │  Convert passport.to_dict() → plain dict                         │ │
│  │                                                                   │ │
│  │  For each section in IntegrityRuleSet (in declaration order):    │ │
│  │    1. Check if section present in passport dict                  │ │
│  │       • Missing + required=true → ERROR                          │ │
│  │       • Missing + required=false → WARNING                       │ │
│  │    2. Check section kind matches (string/object/array)           │ │
│  │       • Mismatch → ERROR                                         │ │
│  │    3. For object sections:                                       │ │
│  │       • Check all fields present → ERROR if missing              │ │
│  │       • Check confidence_fields numeric + in [0,1] → ERROR       │ │
│  │    4. Record CheckedSection(name, kind, present, valid)          │ │
│  │                                                                   │ │
│  │  Determine status:                                               │ │
│  │    • errors non-empty → INVALID (is_valid=False)                 │ │
│  │    • errors empty, warnings non-empty → VALID_WITH_WARNINGS      │ │
│  │    • both empty → VALID                                          │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                               ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  STAGE 2: HASH (deterministic integrity fingerprint)             │ │
│  │  ────────────────────────────────────────────────────────────────│ │
│  │  1. Serialize passport → canonical JSON:                         │ │
│  │     passport.to_json() (no indent, sort_keys=True, stable        │ │
│  │     separators, ensure_ascii=False)                              │ │
│  │  2. Encode to UTF-8 bytes                                        │ │
│  │  3. Hash with config.hash_algorithm (default SHA-256):           │ │
│  │     canonical_hash = hash_bytes(json_bytes, algorithm="sha256")  │ │
│  │  4. Return lowercase hex digest (64 chars for SHA-256)           │ │
│  │                                                                   │ │
│  │  Same passport → same hash (byte-identical)                      │ │
│  │  Any mutation → different hash (tamper-evident)                  │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                               ↓                                        │
│  OUTPUT: PassportIntegrityReport                                      │
│  ────────────────────────────────────                                 │
│  • passport_id (from passport)                                        │
│  • status (VALID / VALID_WITH_WARNINGS / INVALID)                     │
│  • is_valid (True unless INVALID)                                     │
│  • canonical_hash (hex digest, 64 chars for SHA-256)                  │
│  • hash_algorithm (e.g., "sha256")                                    │
│  • schema_version (from IntegrityRuleSet)                             │
│  • passport_version (from passport)                                   │
│  • checked_sections (ordered CheckedSection records)                  │
│  • warnings (ordered, 0+ soft cautions)                               │
│  • errors (ordered, 0+ structural violations)                         │
│  • Provenance: rules_version, engine_version, created_at             │
│                                                                        │
│  Properties: checked_count, warning_count, error_count                │
│                                                                        │
│  EXTERNAL RULE-SET: integrity/data/rules.yaml                         │
│  ───────────────────────────────────────────                         │
│  • version: "1.0.0"                                                   │
│  • sections: 13 declarations (name, kind, fields, confidence_fields, │
│    required)                                                          │
│  • fingerprint_summary: required=false (optional section)             │
│  • All others: required=true (mandatory sections)                     │
│                                                                        │
│  Loader validates: non-empty version, all sections named, known       │
│  kinds, object sections have fields, confidence fields in own fields. │
│  Malformed rule-set → PassportIntegrityRuleError at load time.        │
│                                                                        │
│  KEY ASYMMETRY:                                                       │
│  • Malformed rule-set (engine fault) → RAISED as exception           │
│  • Malformed passport (data fault) → REPORTED as is_valid=False      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 9. Trust & Provenance Engine (M2.5)

### Purpose

The Trust & Provenance Engine scores how trustworthy the `DevicePassport` is as a representation of the device by blending four trust sub-axes (identity confidence, evidence consistency, decision confidence, integrity confidence) into a normalized `[0, 1]` trust score, then maps that score to a trust level (`high`, `medium`, `low`, `untrusted`). It is the final verdict in the Decision Intelligence pipeline before the passport and its reports flow to the blockchain ledger (M3.1–M3.3, out of scope).

Low-trust passports are **reported** with ordered warnings, never rejected. This is the same asymmetry as M2.4: a malformed **engine** (bad trust catalogue, unsupported algorithm) raises a typed exception; a low-trust **passport** (low score, inconsistent evidence) is reported as `trust_level=untrusted` with ordered diagnostics.

### Responsibilities

1. **Project** — map the four upstream reports (`DevicePassport`, `PassportIntegrityReport`, `DecisionKnowledgeReport`, `DecisionReport`) onto the four normalized `[0, 1]` trust sub-axes:
   - **Identity confidence** — blends identity completeness (fraction of strong fields present) with classification confidence
   - **Evidence consistency** — checks cross-report device-type agreement and conflict flags
   - **Decision confidence** — mean of circular decision confidence and decision-knowledge overall confidence
   - **Integrity confidence** — reads passport validation status, damps by warnings

2. **Score** — compute the weighted average of the four axes using per-axis blend weights from the external trust catalogue. The trust score is transparent: an operator can see which axis moved it and by how much.

3. **Level** — map the trust score to a trust level by finding the first catalogue level whose floor the score meets or exceeds (levels sorted by descending floor). Because the loader guarantees a `0.0` floor, every score resolves to exactly one level.

4. **Explain** — generate ordered reasoning and warnings describing how the score was computed, which axes contributed, and what caveats apply.

### Inputs

- `DevicePassport` (M2.3) — the assembled passport document
- `PassportIntegrityReport` (M2.4) — validation status, warnings, errors
- `DecisionKnowledgeReport` (M2.1) — normalized decision dimensions, overall confidence
- `DecisionReport` (M2.2) — recommended action, confidence
- `TrustRuleSet` (external) — per-axis blend weights, trust-level thresholds

### Outputs

`PassportTrustReport` containing:

- `passport_id` — carried from the passport
- `trust_score` — normalized `[0, 1]` weighted average of four axes
- `trust_level` — `HIGH`, `MEDIUM`, `LOW`, or `UNTRUSTED`
- Four axis values: `identity_confidence`, `evidence_consistency`, `decision_confidence`, `integrity_confidence` (each `[0, 1]`)
- `axes` — ordered `TrustAxis` records (each with `name`, `value`, `weight`, `reason`)
- `reasoning` — ordered human-readable explanations
- `warnings` — ordered operator-facing cautions
- Provenance: `engine_version`, `rules_version`, `created_at`

Plus property: `axis_count` (always 4).

### Internal Workflow

The engine implements a three-stage pipeline:

**Stage 1: Project** — Map the four upstream reports onto the four normalized `[0, 1]` trust sub-axes (the canonical vocabulary defined in `CANONICAL_AXES`):

**Identity Confidence:**
```
completeness = count(model, serial, IMEI, MAC present) / 4
classification_conf = passport.classification.confidence
identity_confidence = (completeness + classification_conf) / 2
```

**Evidence Consistency:**
- Collect device types from `passport.classification.device_type`, `knowledge.device_type`, `decision.device_type` (non-empty only)
- Check `passport.classification.has_conflicts` flag
- Branch logic:
  - No types resolved → `0.5` (undefined consistency)
  - One type, no conflict → `1.0` (perfect agreement)
  - One type, conflict flagged → `0.8` (agreement but fusion flagged conflict)
  - Multiple types, no conflict → `0.4` (disagreement, no additional flag)
  - Multiple types, conflict flagged → `0.2` (disagreement + conflict flag)

**Decision Confidence:**
```
decision_confidence = (knowledge.overall_confidence + decision.confidence) / 2
```

**Integrity Confidence:**
- Read `integrity.status`:
  - `INVALID` → `0.0`
  - `VALID_WITH_WARNINGS` → `1.0 - (config.integrity_warning_penalty × integrity.warning_count)` (clamped to `[0, 1]`)
  - `VALID` → `1.0`

All axis values clamped to `[0, 1]` and rounded to 6 decimals.

**Stage 2: Score** — Blend the four axes into the trust score:

1. Read per-axis weights from the trust catalogue: `identity_confidence` → 0.30, `evidence_consistency` → 0.25, `decision_confidence` → 0.20, `integrity_confidence` → 0.25 (catalogue version 1.0.0 defaults).
2. Compute weighted average:
```
trust_score = clamp_round(
  (identity × 0.30 + evidence × 0.25 + decision × 0.20 + integrity × 0.25) / 1.00
)
```

Because the loader guarantees positive total weight, the average is always well-defined. Clamp to `[0, 1]` and round to 6 decimals.

**Stage 3: Level** — Map the trust score to a trust level:

1. Read trust-level thresholds from the catalogue (version 1.0.0 defaults): `high` ≥ 0.75, `medium` ≥ 0.50, `low` ≥ 0.25, `untrusted` ≥ 0.0.
2. Sort levels by descending `min_score` floor (highest first).
3. Find the first level whose floor the score meets or exceeds: that level wins.

Because the loader guarantees a `0.0` floor, every score in `[0, 1]` resolves to exactly one level.

4. **Emit warning if low**: If final score ≤ `config.min_trust_score` (default 0.4), append a low-trust warning to the report.

### Configuration

`TrustConfig` (immutable, frozen, slotted):
- `rules_path` (string, default `"trust/data/rules.yaml"`) — locator of the external trust catalogue, resolved relative to `device_ai` package root when not absolute.
- `min_trust_score` (float, default `0.4`, range `[0, 1]`) — trust score floor; passports at or below this trigger a low-trust warning (never changes the trust level itself).
- `identity_field_count` (int, default `4`) — number of strong identity fields (model, serial, IMEI, MAC) the engine normalizes identity completeness against.
- `integrity_warning_penalty` (float, default `0.1`) — per-warning penalty subtracted from the integrity axis when the integrity report carries soft cautions (a valid-with-warnings passport is slightly less trustworthy than a clean one).

Mapped from environment via `TrustConfig.from_settings(settings)`:
- `TRUST_RULES_PATH` → `rules_path`
- `TRUST_MIN_SCORE` → `min_trust_score`

### Collaborators

- **Upstream reports**: `DevicePassport` (M2.3), `PassportIntegrityReport` (M2.4), `DecisionKnowledgeReport` (M2.1), `DecisionReport` (M2.2)
- **External catalogue**: `trust/data/rules.yaml` (version 1.0.0) — loaded by `load_rules()` into immutable `TrustRuleSet`
- **Trust engine**: `TrustEngine` — pure deterministic scorer, no I/O
- **Service**: `TrustService` — constructor-injectable façade that loads the catalogue once, scores and levels, stamps provenance, optionally injects a clock

### Dependency Graph

```
DevicePassport ────────┐
PassportIntegrityReport ──┤
DecisionKnowledgeReport ──┤──→ TrustEngine ──→ PassportTrustReport
DecisionReport ───────┘              ↑
                                     │
                              TrustRuleSet
                              (external YAML)
```

### Error Handling

**Load-time failures** (malformed catalogue) raise `PassportTrustRuleError`:
- Missing or empty `version`
- Missing or empty `weights` or `levels`
- Unknown axis name (not in `CANONICAL_AXES`: `identity_confidence`, `evidence_consistency`, `decision_confidence`, `integrity_confidence`)
- Negative weight
- All-zero total weight (at least one positive weight required)
- Non-numeric weight
- Unknown level name (not in `HIGH`, `MEDIUM`, `LOW`, `UNTRUSTED`)
- Duplicate level
- Missing level (all four required)
- Non-numeric or out-of-range `min_score`
- No level with `0.0` floor (levels must cover `[0, 1]`)

**Runtime behavior** (low-trust data):
- Low trust score → reported as low `trust_score`, `trust_level=untrusted` or `low`, warning emitted, never raised
- Missing device type → reported in `evidence_consistency` reason, trust score still computed
- Invalid passport → `integrity_confidence=0.0`, trust score damped, warning emitted
- Disagreeing upstream reports → reported in `evidence_consistency` value (0.2–0.8), trust score damped

**Key asymmetry**: A malformed **catalogue** (engine fault) is **raised** as `PassportTrustRuleError`. A low-trust **passport** (data fault) is **reported** as `trust_level=untrusted` with ordered warnings, never raised.

### Testing Strategy

- **Unit tests** — test `TrustEngine.evaluate()` directly with hand-built reports and a hand-built `TrustRuleSet`. Verify:
  - All four axis projection formulas (identity, evidence, decision, integrity)
  - Axis score computation (weighted average, clamped to `[0, 1]`)
  - Level selection (descending floor, first met wins)
  - Warning emission (low score, invalid passport, soft warnings)
  - Determinism (same inputs → byte-identical output when `created_at=None`)
- **Loader tests** — test `load_rules()` with valid and malformed catalogues. Verify:
  - Valid catalogue loads successfully
  - Every structural violation raises `PassportTrustRuleError` with the correct `code` and descriptive `details`
- **Config tests** — test `TrustConfig.from_settings()` maps environment correctly
- **Service tests** — test `TrustService.assess()` end-to-end with injected fixed clock, verify provenance stamping

### Design Rationale

**Why four sub-axes?** — The four axes capture orthogonal trust signals: **identity** (how well-identified is the device?), **evidence** (do the upstream reports agree?), **decision** (how confident are the two decision engines?), and **integrity** (is the passport structurally sound?). Blending them into a single score makes trust comparable across passports; retaining the four axes makes trust explainable.

**Why external catalogue?** — The per-axis blend weights and the trust-level thresholds are **policy**, not inference logic. They will be tuned as real triage data accumulates and as the upstream scoring engines evolve. Keeping them in an external YAML file (versioned and stamped onto every report) means policy can be reviewed and changed by domain experts without redeploying the engine.

**Why report rather than raise?** — The trust engine validates **trustworthiness**, not structural correctness. A low-trust passport is a **verdict** about the data's reliability, not an engine fault. Reporting it as `trust_level=untrusted` with ordered warnings allows downstream consumers (blockchain ledger M3.1) to decide how to handle low-trust passports. Raising an exception would force the orchestrating code to catch and inspect it, which breaks the clean report-based flow.

**Why weighted average?** — A weighted average is transparent: an operator can see which axis contributed how much to the final score. It's also tunable: reweighting the axes changes the balance between identity, evidence, decision, and integrity without touching the engine. Alternative scoring functions (minimum, product, threshold voting) are less interpretable and harder to debug.

### Extension Strategy

The engine is extended by editing the external trust catalogue (`trust/data/rules.yaml`), not by modifying code:

- **Reweight an axis** — change axis weights in the `weights` block, bump the catalogue `version`.
- **Retune thresholds** — adjust `min_score` values in the `levels` block to shift the boundaries between trust levels, bump the catalogue `version`.

Adding a **new axis** requires code changes (project the new axis in `TrustEngine._*_confidence()` methods, add it to `CANONICAL_AXES`, add the axis to the loader's required set, add it to `_AXIS_ORDER` for byte-reproducibility). Adding a **new level** requires code changes (add the enum member to `TrustLevel`, update the loader's allowed set).

### Trust Computation Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│      TRUST & PROVENANCE ENGINE (M2.5) ARCHITECTURE                    │
│                                                                        │
│  INPUTS (4 upstream reports)                                          │
│  ────────────────────────────────                                     │
│  DevicePassport            (13 sections, identity, classification)    │
│  PassportIntegrityReport   (status, warnings, errors, hash)          │
│  DecisionKnowledgeReport   (6 dimensions, overall_confidence)        │
│  DecisionReport            (action, confidence)                       │
│                                                                        │
│                               ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  STAGE 1: PROJECT TRUST SUB-AXES (4 normalized [0,1] axes)       │ │
│  │  ────────────────────────────────────────────────────────────────│ │
│  │  IDENTITY CONFIDENCE:                                            │ │
│  │    completeness = count(model, serial, IMEI, MAC present) / 4    │ │
│  │    classification_conf = passport.classification.confidence      │ │
│  │    identity = (completeness + classification_conf) / 2           │ │
│  │                                                                   │ │
│  │  EVIDENCE CONSISTENCY (cross-report device-type agreement):      │ │
│  │    Collect device_type from passport, knowledge, decision        │ │
│  │    Check passport.classification.has_conflicts flag              │ │
│  │    Branch logic:                                                 │ │
│  │      • No types → 0.5 (undefined)                                │ │
│  │      • One type, no conflict → 1.0 (perfect)                     │ │
│  │      • One type, conflict flagged → 0.8 (flagged)                │ │
│  │      • Multiple types, no conflict → 0.4 (disagreement)          │ │
│  │      • Multiple types, conflict flagged → 0.2 (worst)            │ │
│  │                                                                   │ │
│  │  DECISION CONFIDENCE:                                            │ │
│  │    decision = (knowledge.overall_confidence +                    │ │
│  │                decision.confidence) / 2                           │ │
│  │                                                                   │ │
│  │  INTEGRITY CONFIDENCE (validation status):                       │ │
│  │    • INVALID → 0.0                                               │ │
│  │    • VALID_WITH_WARNINGS → 1.0 - (penalty × warning_count)      │ │
│  │    • VALID → 1.0                                                 │ │
│  │                                                                   │ │
│  │  All clamped to [0,1], rounded to 6 decimals                     │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                               ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  STAGE 2: SCORE (weighted average of 4 axes)                     │ │
│  │  ────────────────────────────────────────────────────────────────│ │
│  │  Read per-axis weights from TrustRuleSet (v1.0.0 defaults):      │ │
│  │    identity_confidence      : 0.30                               │ │
│  │    evidence_consistency     : 0.25                               │ │
│  │    decision_confidence      : 0.20                               │ │
│  │    integrity_confidence     : 0.25                               │ │
│  │    ─────────────────────────────                                │ │
│  │    total_weight             : 1.00                               │ │
│  │                                                                   │ │
│  │  Compute weighted average:                                       │ │
│  │    trust_score = clamp_round(                                    │ │
│  │      (identity × 0.30 + evidence × 0.25 +                        │ │
│  │       decision × 0.20 + integrity × 0.25) / 1.00                 │ │
│  │    )                                                              │ │
│  │                                                                   │ │
│  │  Rounded to 6 decimals                                           │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                               ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  STAGE 3: LEVEL (map score → trust level via thresholds)         │ │
│  │  ────────────────────────────────────────────────────────────────│ │
│  │  Read trust-level thresholds from TrustRuleSet (v1.0.0):         │ │
│  │    HIGH       min_score ≥ 0.75                                   │ │
│  │    MEDIUM     min_score ≥ 0.50                                   │ │
│  │    LOW        min_score ≥ 0.25                                   │ │
│  │    UNTRUSTED  min_score ≥ 0.00                                   │ │
│  │                                                                   │ │
│  │  Sort by descending floor, find first level whose floor the      │ │
│  │  score meets or exceeds: that level wins.                        │ │
│  │                                                                   │ │
│  │  Loader guarantees 0.0 floor → every score resolves to exactly   │ │
│  │  one level.                                                       │ │
│  │                                                                   │ │
│  │  EMIT WARNING IF LOW:                                            │ │
│  │    If trust_score ≤ config.min_trust_score (0.4) → warning       │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                               ↓                                        │
│  OUTPUT: PassportTrustReport                                          │
│  ────────────────────────────────                                     │
│  • passport_id (from passport)                                        │
│  • trust_score (normalized [0,1], weighted average of 4 axes)         │
│  • trust_level (HIGH / MEDIUM / LOW / UNTRUSTED)                      │
│  • 4 axis values: identity_confidence, evidence_consistency,          │
│    decision_confidence, integrity_confidence (each [0,1])             │
│  • axes (ordered TrustAxis records: name, value, weight, reason)      │
│  • reasoning (ordered, 5+ sentences)                                  │
│  • warnings (ordered, 0+ cautions)                                    │
│  • Provenance: engine_version, rules_version, created_at             │
│                                                                        │
│  Property: axis_count (always 4)                                      │
│                                                                        │
│  EXTERNAL CATALOGUE: trust/data/rules.yaml                            │
│  ────────────────────────────────────────────                        │
│  • version: "1.0.0"                                                   │
│  • weights: 4 per-axis blend weights (sum to 1.00)                    │
│  • levels: 4 trust-level thresholds (0.0, 0.25, 0.50, 0.75)          │
│                                                                        │
│  Loader validates: all 4 axes weighted once, positive total weight,   │
│  all 4 levels declared once, 0.0 floor exists, non-negative weights.  │
│  Malformed catalogue → PassportTrustRuleError at load time.           │
│                                                                        │
│  KEY ASYMMETRY:                                                       │
│  • Malformed catalogue (engine fault) → RAISED as exception          │
│  • Low-trust passport (data fault) → REPORTED as trust_level=low     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 10. End-to-End Decision Flow

The five engines form a complete, auditable pipeline from raw device-intelligence evidence to final trust verdict. This section traces one device through the entire Decision Intelligence Layer to show how the engines collaborate.

### Sample Device

- **Device**: iPhone 12, serial `F2LDP12X0D64`, classification confidence 0.92
- **Materials**: 189g total, 145g recoverable, 12g hazardous, 18 materials identified
- **Recoverability**: repairability 0.72, reusability 0.68, recyclability 0.81, hazard MEDIUM
- **Environmental**: 42kg CO₂e saved, circularity 0.74, 0.008kg critical material
- **Fingerprint**: present, 512-dim CLIP embedding

### Stage 1: Decision Knowledge (M2.1)

**Input**: DeviceContext + 4 intelligence reports  
**Processing**:
1. Project 11 signals: repairability 0.72, reusability 0.68, recyclability 0.81, circularity 0.74, hazard_severity 0.70 (MEDIUM), hazardous_fraction 0.063, identity_completeness 0.75 (3/4 strong fields), etc.
2. Blend 6 dimensions:
   - REPAIRABILITY: `0.72×0.8 + 0.75×0.2 = 0.726`
   - REUSABILITY: `0.68×0.8 + 0.75×0.2 = 0.694`
   - RECYCLING: `0.81×0.55 + 0.74×0.25 + 0.77×0.20 = 0.784`
   - HAZARD: `0.70×0.6 + 0.063×0.25 + 0.42×0.15 = 0.499`
   - ENVIRONMENTAL_PRIORITY: `0.42×0.45 + 0.74×0.25 + 0.16×0.30 = 0.422`
   - MATERIAL_VALUE: `0.16×0.5 + 0.77×0.25 + 0.42×0.25 = 0.377`
3. Aggregate confidence: `(0.89 + 0.82 + 0.88 + 0.91 + 0.92) / 5 = 0.884`

**Output**: `DecisionKnowledgeReport` with 6 dimensions, overall_confidence 0.884

### Stage 2: Circular Decision (M2.2)

**Input**: DecisionKnowledgeReport + DeviceContext + Recoverability + Environmental  
**Processing**:
1. Project 16 signals from stage 1 dimensions + upstream
2. Evaluate 10 rules (precedence 10→100):
   - `high_hazard_severity` (precedence 20): hazard_severity 0.70 ≥ 0.70 → **FIRES** (action: manual_review, priority: high)
   - `refurbish` (precedence 70): reusability 0.694 ≥ 0.60, material_value 0.377 ≥ 0.30 → **FIRES** (action: refurbish, priority: medium)
   - No other rules fire
3. Select winner: precedence 20 (lowest) wins → `manual_review` / `high`
4. Damp confidence: `0.884 × 1.0 (no confidence_factor on rule 20) = 0.884`

**Output**: `DecisionReport` — recommended_action: `manual_review`, priority: `high`, confidence: 0.884, 2 rules fired

### Stage 3: Device Passport (M2.3)

**Input**: DeviceContext + DecisionReport + MaterialReport + EnvironmentalImpactReport + DeviceFingerprint  
**Processing**:
1. Summarize 8 sections from upstream
2. Compose confidence: `(0.92 + 0.884 + 0.88 + 0.91) / 4 = 0.8985`
3. Identify: `ET-PP-` + SHA256(eco_id||fingerprint||iPhone 12||Apple||...) → `ET-PP-A7F3C9B2E1D4`
4. Narrate: aggregate 3 base + upstream reasoning/warnings

**Output**: `DevicePassport` — 13 sections, passport_id `ET-PP-A7F3C9B2E1D4`, overall confidence 0.899

### Stage 4: Passport Integrity (M2.4)

**Input**: DevicePassport  
**Processing**:
1. Validate structure against IntegrityRuleSet:
   - All 13 required sections present ✓
   - All object sections have required fields ✓
   - All confidence fields in [0,1] ✓
   - fingerprint_summary optional, present ✓
2. Determine status: 0 errors, 0 warnings → `VALID`
3. Hash: SHA-256(`passport.to_json()`) → `5c3a8f...` (64-char hex)

**Output**: `PassportIntegrityReport` — status: VALID, is_valid: true, canonical_hash: `5c3a8f...`, 13 sections checked

### Stage 5: Trust & Provenance (M2.5)

**Input**: DevicePassport + PassportIntegrityReport + DecisionKnowledgeReport + DecisionReport  
**Processing**:
1. Project 4 axes:
   - Identity: `(0.75 + 0.92) / 2 = 0.835`
   - Evidence: all 3 reports agree on "iPhone 12", no conflicts → `1.0`
   - Decision: `(0.884 + 0.884) / 2 = 0.884`
   - Integrity: VALID → `1.0`
2. Score: `(0.835×0.30 + 1.0×0.25 + 0.884×0.20 + 1.0×0.25) / 1.00 = 0.927`
3. Level: 0.927 ≥ 0.75 → `HIGH`

**Output**: `PassportTrustReport` — trust_score: 0.927, trust_level: HIGH, 4 axes, no warnings

### Final Outputs

The orchestrating pipeline delivers three immutable artifacts to the blockchain ledger (M3.1, out of scope):

1. **DevicePassport** `ET-PP-A7F3C9B2E1D4` — 13-section canonical document, recommended_action: manual_review
2. **PassportIntegrityReport** — VALID, hash `5c3a8f...`
3. **PassportTrustReport** — HIGH trust (0.927)

All three are deterministic, auditable, and byte-reproducible (when `created_at` omitted).

### End-to-End Decision Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│              END-TO-END DECISION FLOW (M2.1 → M2.5)                   │
│                                                                        │
│  UPSTREAM DEVICE INTELLIGENCE (M1.1–M1.11, see doc 03)               │
│  ─────────────────────────────────────────────────────               │
│   DeviceContext (M1.7)  Recoverability (M1.8)  Component (M1.9)       │
│   Material (M1.10)  Environmental (M1.11)  Fingerprint (M1.5)         │
│         │         │         │         │         │         │           │
│         ▼         ▼         ▼         ▼         ▼         │           │
│  ┌──────────────────────────────────────────────────┐    │           │
│  │  M2.1 DECISION KNOWLEDGE                          │    │           │
│  │  5 reports → 6 dimensions + overall_confidence    │    │           │
│  │  ══════════════════════════════════════════════   │    │           │
│  │  DecisionKnowledgeReport ────────────────┐        │    │           │
│  └──────────────────────────────────────────│────────┘    │           │
│         │                                    │             │           │
│         │  (feeds M2.2 and M2.5)             │             │           │
│         ▼                                    │             │           │
│  ┌──────────────────────────────────────────│────────┐    │           │
│  │  M2.2 CIRCULAR DECISION                   │        │    │           │
│  │  evidence + rules → recommended action    │        │    │           │
│  │  ══════════════════════════════════════   │        │    │           │
│  │  DecisionReport ──────────────────┐       │        │    │           │
│  └───────────────────────────────────│───────│────────┘    │           │
│         │                             │       │             │           │
│         │  (feeds M2.3 and M2.5)      │       │             │           │
│         ▼                             │       │             │           │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  M2.3 DEVICE PASSPORT CORE                                       │  │
│  │  compose upstream reports → canonical DevicePassport (13 sect.) │  │
│  │  (DeviceContext + DecisionReport + Material + Environmental +    │  │
│  │   Fingerprint) → NO INFERENCE, faithful snapshot                │  │
│  │  ═══════════════════════════════════════════════════════════    │  │
│  │  DevicePassport (id: ET-PP-{12-char hash}) ────────┐            │  │
│  └────────────────────────────────────────────────────│───────────┘  │
│         │                                              │                │
│         │  (feeds M2.4 and M2.5)                       │                │
│         ▼                                              │                │
│  ┌────────────────────────────────────────────────────│───────────┐  │
│  │  M2.4 PASSPORT INTEGRITY                            │           │  │
│  │  validate structure + SHA-256 hash                 │           │  │
│  │  ═══════════════════════════════════════════════    │           │  │
│  │  PassportIntegrityReport (status + hash) ──┐        │           │  │
│  └────────────────────────────────────────────│────────│───────────┘  │
│         │                                      │        │                │
│         │  (feeds M2.5)                        │        │                │
│         ▼                                      ▼        ▼                │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  M2.5 TRUST & PROVENANCE                                         │  │
│  │  4 axes (identity, evidence, decision, integrity) →             │  │
│  │  trust score → trust level                                       │  │
│  │  Inputs: DevicePassport + PassportIntegrityReport +             │  │
│  │          DecisionKnowledgeReport + DecisionReport               │  │
│  │  ═══════════════════════════════════════════════════════════    │  │
│  │  PassportTrustReport (trust_score + trust_level)                 │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                               │                                        │
│                               ▼                                        │
│  FINAL ARTIFACTS → Blockchain Ledger (M3.1–M3.3, see future docs)    │
│  ────────────────────────────────────                                 │
│  • DevicePassport (canonical, content-addressed)                      │
│  • PassportIntegrityReport (VALID + SHA-256 hash)                     │
│  • PassportTrustReport (trust level: HIGH/MEDIUM/LOW/UNTRUSTED)       │
│                                                                        │
│  PROPERTIES OF THE WHOLE PIPELINE:                                    │
│  • Linear & acyclic (no engine sees future stages)                    │
│  • Deterministic (same inputs → byte-identical outputs)               │
│  • Versioned (every catalogue stamps its version onto its report)     │
│  • Auditable (every score/action/level carries ordered reasoning)     │
│  • Internal-only (no HTTP surface; consumed in-process)               │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 11. Shared Decision Domain Models

All five engines share a consistent domain-model design. Every model is a frozen, slotted dataclass with no HTTP/I-O concerns, making the whole layer deterministic and independently testable.

### Model Design Conventions

Every domain model honors these conventions:

- **Immutability** — `@dataclass(frozen=True, slots=True)`. Once constructed, a model cannot be mutated. This guarantees that a report handed to a downstream engine cannot be accidentally modified.
- **Slotted** — `slots=True` eliminates per-instance `__dict__`, reducing memory footprint and preventing accidental attribute addition.
- **Serialization** — every model exposes `to_dict()` returning a plain JSON-serializable dict. Report-level models additionally expose `to_json(*, indent=None)` producing canonical JSON.
- **Provenance** — every report carries version fields (`engine_version`, catalogue version) and an optional `created_at` timestamp.
- **Ordered collections** — reasoning, warnings, and evidence records are tuples (ordered, immutable), preserving deterministic output.

### Enumerations

The layer defines several `str`-based enums so members serialize to their wire value directly and can be constructed from catalogue strings:

| Enum | Milestone | Members |
|------|-----------|---------|
| `DecisionDimension` | M2.1 | `REPAIRABILITY`, `REUSABILITY`, `RECYCLING`, `HAZARD`, `ENVIRONMENTAL_PRIORITY`, `MATERIAL_VALUE` |
| `RecommendedAction` (reused from M1.8) | M2.2 | `REPAIR`, `REFURBISH`, `RECYCLE`, `MANUAL_REVIEW`, `HAZARDOUS_DISPOSAL` |
| `Priority` | M2.2 | `HIGH`, `MEDIUM`, `LOW` |
| `SectionKind` | M2.3 | `STRING`, `OBJECT`, `ARRAY` |
| `ValidationStatus` | M2.4 | `VALID`, `VALID_WITH_WARNINGS`, `INVALID` |
| `TrustLevel` | M2.5 | `HIGH`, `MEDIUM`, `LOW`, `UNTRUSTED` |

### Report Models

| Report | Milestone | Key Fields |
|--------|-----------|-----------|
| `DecisionKnowledgeReport` | M2.1 | 6 dimension scores + overall_confidence + dimensions breakdown + reasoning/warnings + provenance |
| `DecisionReport` | M2.2 | recommended_action + priority + confidence + triggered_rules + reasoning/warnings + provenance |
| `DevicePassport` | M2.3 | 13 sections (passport_id, 8 section objects, reasoning, warnings) + provenance |
| `PassportIntegrityReport` | M2.4 | status + canonical_hash + checked_sections + warnings/errors + provenance |
| `PassportTrustReport` | M2.5 | trust_score + trust_level + 4 axes + reasoning/warnings + provenance |

### Value Objects

Supporting value objects that make reports explainable:

- `EvidenceSignal` (M2.1) — `name`, `value`, `weight` (one signal's contribution to a dimension)
- `DimensionEvidence` (M2.1) — `dimension`, `score`, `signals`, `reason` (one dimension's breakdown)
- `TriggeredRule` (M2.2) — `rule_id`, `action`, `priority`, `precedence`, `reason`, `won` (one fired rule)
- `CheckedSection` (M2.4) — `name`, `kind`, `present`, `valid` (one validated section)
- `TrustAxis` (M2.5) — `name`, `value`, `weight`, `reason` (one trust sub-axis)

Plus the eight passport section dataclasses (M2.3): `DeviceIdentity`, `Classification`, `DecisionSummary`, `MaterialSummary`, `EnvironmentalSummary`, `FingerprintSummary`, `ConfidenceSummary`, `PassportMetadata`.

---

## 12. Knowledge Catalogue Architecture

Three of the five engines (M2.1 decision knowledge, M2.2 circular rules, M2.5 trust) are driven by **external knowledge catalogues** — versioned YAML/JSON files that hold policy, not logic. The other two (M2.3 passport schema, M2.4 integrity rules) are driven by **external structural contracts** in the same format. This section describes the common catalogue architecture.

### The External Catalogue Pattern

Every catalogue-driven engine follows the same lifecycle:

1. **Locate** — the config holds a relative path (e.g., `decision/data/knowledge.yaml`), resolved against the `device_ai` package root so the packaged catalogue is found regardless of process working directory.

2. **Load** — a strict loader reads the file (YAML or JSON), validates every entry aggressively, and builds an immutable value object. The catalogue is loaded exactly once, at service construction, and held immutably.

3. **Validate** — the loader rejects any structural problem with a typed exception carrying a stable `code` and descriptive `details`. A malformed catalogue never silently degrades the engine.

4. **Version** — every catalogue declares a semantic `version` that is stamped onto every report the engine produces, so consumers can detect which policy version scored a device.

### Catalogue Inventory

| Catalogue | Engine | Version | Contents |
|-----------|--------|---------|----------|
| `decision/data/knowledge.yaml` | M2.1 | 1.0.0 | 6 dimension weight maps + confidence weights + 4 saturation constants |
| `circular/data/rules.yaml` | M2.2 | 1.0.0 | 10 precedence-ordered rules + default fallback |
| `passport/data/schema.yaml` | M2.3 | 1.0.0 | 13 section declarations (kind, fields, confidence fields) |
| `integrity/data/rules.yaml` | M2.4 | 1.0.0 | 13 section validation rules (kind, fields, required flags) |
| `trust/data/rules.yaml` | M2.5 | 1.0.0 | 4 axis weights + 4 trust-level thresholds |

### Fixed Vocabularies

Each catalogue is validated against a **fixed vocabulary** hardcoded in the engine — the catalogue may re-weight or re-threshold, but may not invent new terms:

- **M2.1**: `CANONICAL_SIGNALS` (11 signals), `CONFIDENCE_SOURCES` (5 sources), `DecisionDimension` (6 dimensions)
- **M2.2**: `CANONICAL_SIGNALS` (16 signals), `CONDITION_OPERATORS` (4: gte, lte, gt, lt), `RecommendedAction` (5 actions), `Priority` (3 priorities)
- **M2.3**: `SectionKind` (3 kinds: string, object, array)
- **M2.4**: `SectionKind` (3 kinds)
- **M2.5**: `CANONICAL_AXES` (4 axes), `TrustLevel` (4 levels)

A typo in a catalogue (e.g., `repairabilty` instead of `repairability`) is caught at load time rather than silently ignored, because the term is not in the engine's fixed vocabulary.

### Why External Catalogues?

**Separation of policy from logic** — the engine's arithmetic (weighted averages, rule evaluation, hashing) is logic; the weights, thresholds, and contracts are policy. Policy changes as data accumulates and requirements evolve; logic does not. Keeping them separate means policy can be tuned by domain experts (reviewers, regulators, engineers) without touching or redeploying the engine.

**Auditability** — every catalogue is versioned and its version is stamped onto every report. Given a report, one can determine exactly which policy version produced it. This is essential for reproducibility, debugging, and regulatory compliance.

**Testability** — because catalogues are injectable, tests can supply hand-built catalogues (e.g., a single-rule catalogue) to isolate specific behaviors without loading the shipped files.

---

## 13. Rule Evaluation Architecture

The Circular Decision Engine (M2.2) is the only engine in the layer that performs **rule evaluation** — the others perform weighted arithmetic (M2.1, M2.5) or structural validation (M2.3, M2.4). This section describes the rule-evaluation architecture in depth.

### Rule Structure

Each rule in the circular catalogue is a `DecisionRule` with:

- `rule_id` — unique machine-readable identifier (e.g., `high_hazard_severity`)
- `precedence` — unique integer (lower = higher priority); determines which rule wins when multiple fire
- `action` — the recommended action if the rule fires (`RecommendedAction`)
- `priority` — the action's urgency (`Priority`)
- `reason` — human-readable explanation
- `conditions` — one or more `RuleCondition` objects (all must hold for the rule to fire)
- `confidence_factor` — optional multiplier (default 1.0, range `[0, 1]`) that damps confidence when the rule fires
- `warning` — optional operator caution emitted when the rule fires

### Condition Structure

Each `RuleCondition` tests one signal against a threshold:

- `signal` — one of the 16 canonical signals
- `operator` — one of `gte` (≥), `lte` (≤), `gt` (>), `lt` (<)
- `threshold` — a value in `[0, 1]`

A condition holds when `signal_value <operator> threshold`. A rule fires when **all** its conditions hold (AND logic).

### Evaluation Algorithm

```
def decide(signals, catalogue):
    fired = []
    for rule in catalogue.rules:  # already precedence-ordered
        if all(check(condition, signals) for condition in rule.conditions):
            fired.append(TriggeredRule(rule, won=False))

    if fired:
        winner = min(fired, key=lambda r: r.precedence)  # lowest precedence
        winner.won = True
        action, priority = winner.action, winner.priority
    else:
        action, priority = catalogue.default.action, catalogue.default.priority

    confidence = knowledge.overall_confidence
    for rule in fired:
        confidence *= rule.confidence_factor

    return DecisionReport(action, priority, confidence, fired, ...)
```

### Precedence Semantics

The precedence mechanism is the heart of the rule engine's determinism:

- Rules are stored in the catalogue in precedence order (lowest first).
- All matching rules fire (no short-circuit) — this preserves the full audit trail.
- The rule with the **lowest precedence** (highest priority) wins.
- Precedences are unique (enforced at load time), so the winner is unambiguous.

The shipped catalogue uses precedence bands: safety-critical rules (10–50) override optimization rules (60–100). For example, `upstream_forced_hazardous_disposal` (10) always wins over `refurbish` (70) if both fire, because a hazardous device must be disposed regardless of its refurbishment potential.

### The Default Fallback

The catalogue's mandatory `default` fallback (shipped as `manual_review` / `low`) ensures the engine always produces a recommendation, even when no rule fires. This is a deliberate safety property: an unclassifiable device defaults to human review rather than an arbitrary automated action.

---

## 14. Confidence Propagation Strategy

Confidence flows through the entire Decision Intelligence Layer as a **separate axis** that never scales the primary outputs (dimension scores, recommended actions, trust levels). This section traces how confidence propagates and why it is kept separate.

### Confidence as a Separate Axis

The layer's defining confidence principle: **confidence measures uncertainty, not magnitude**. A high-hazard device with low confidence is still high-hazard; the confidence communicates "verify this manually" rather than damping the hazard score. Keeping confidence separate preserves the meaning of the primary outputs.

### Propagation Chain

```
M1.7–M1.11 upstream confidences (5 sources)
        │
        ▼
M2.1: overall_confidence = weighted mean of 5 upstream confidences
      (sources at/below floor dropped)
        │
        ▼
M2.2: confidence = knowledge.overall_confidence × Π(fired_rule.confidence_factor)
      (damped by rule-specific uncertainty)
        │
        ▼
M2.3: overall = mean(context.conf, decision.conf, material.conf, environmental.conf)
      (composed into passport ConfidenceSummary)
        │
        ▼
M2.5: decision_confidence axis = mean(knowledge.overall_conf, decision.conf)
      (folded into one of four trust axes)
```

### Stage-by-Stage Confidence Handling

**M2.1 Decision Knowledge** — Blends five upstream confidences (recoverability, components, materials, environmental, fusion) into `overall_confidence` using catalogue confidence weights. Sources at or below the `min_confidence` floor (0.05) are dropped entirely, so a genuinely absent upstream signal neither anchors nor inflates the result. No re-damping for conflicts is applied (upstream confidences already fold those in).

**M2.2 Circular Decision** — Starts with `knowledge.overall_confidence` and damps it multiplicatively by each fired rule's `confidence_factor`. A rule like `identity_conflict_review` (factor 0.85) reduces confidence by 15% when it fires, communicating rule-specific uncertainty. Confidence never changes the recommended action, which the rules decide. If the final confidence is at or below the floor (0.35), a low-confidence warning is emitted.

**M2.3 Device Passport** — Composes overall confidence as the mean of four upstream confidences (identity/classification, decision, material, environmental). This is a plain summary, not a re-inference. The four component confidences are retained in the `ConfidenceSummary` section for traceability.

**M2.5 Trust & Provenance** — Folds decision confidence into one of four trust axes: `decision_confidence = mean(knowledge.overall_confidence, decision.confidence)`. This axis is then weighted (0.20) and blended with the other three axes into the trust score.

### Confidence Floors

Two engines use configurable confidence floors:

- **M2.1** `min_confidence` (default 0.05) — drops near-zero upstream confidences from the overall-confidence blend.
- **M2.2** `min_confidence` (default 0.35) — triggers a low-confidence warning on the recommendation (never changes the action).

Both floors are advisory: they flag or filter, but never reject. Low confidence is a **reported verdict**, not an error.

---

## 15. Passport Assembly Strategy

The Device Passport Core (M2.3) is architecturally distinct from the other four engines: it performs **composition, not inference**. This section describes the assembly strategy and its guarantees.

### Composition, Not Inference

The passport core's defining property: **every value it holds is copied or plainly summarized from an upstream report**. It computes no new scores, makes no new decisions, and applies no new policy. This makes the passport a faithful snapshot — an operator can trace every field back to the report that produced it.

The only computed values are:
- **Overall confidence** — the mean of four upstream confidences (a plain summary).
- **Passport ID** — a content-addressed hash of identity + action (a fingerprint, not a decision).

Neither is inference; both are deterministic functions of the inputs.

### Content-Addressed Identity

The passport ID is generated by hashing the device's stable identity and recommended action:

```
joined = "\x1f".join([
    eco_id, fingerprint, device_type, brand, model,
    serial, imei, mac, recommended_action
])
passport_id = "ET-PP-" + short_hash(joined, length=12)  # 12-char uppercase SHA-256 prefix
```

Key properties:
- **Stable** — the same device + action always yields the same ID (no timestamp in the hash).
- **Content-addressed** — the ID is derived from the content, enabling deduplication and idempotency.
- **Prefixed** — the `ET-PP-` prefix makes passport IDs recognizable and namespaced.

### Section Assembly

The passport is assembled from eight section dataclasses, each mapped from one or two upstream reports:

| Section | Source | Fields |
|---------|--------|--------|
| `device_identity` | DeviceContext | brand, model, serial_number, imei, mac_address |
| `classification` | DeviceContext | device_type, confidence, has_conflicts |
| `decision_summary` | DecisionReport | recommended_action, priority, confidence, winning_rule_id, triggered_count |
| `material_summary` | MaterialReport | material_count, total_mass_g, recoverable_mass_g, hazardous_mass_g, confidence |
| `environmental_summary` | EnvironmentalImpactReport | 8 fields (savings, circularity, critical, hazard reduction, confidence) |
| `fingerprint_summary` | DeviceFingerprint (optional) | fingerprint, dimension, encoder_name, encoder_version, metric |
| `confidence_summary` | Computed | identity/decision/material/environmental confidences + overall mean |
| `metadata` | All reports + config | 11 provenance fields |

### Optional Fingerprint

The fingerprint is optional evidence, not a required identity. A passport built without a `DeviceFingerprint` carries an all-empty (but structurally valid) `fingerprint_summary`. The schema marks this section `required: false` in the integrity rule-set, so a missing fingerprint produces a warning (not an error) during integrity validation.

### Validate-Before-Return

The service validates every assembled passport against the schema (`validate_passport(passport.to_dict(), schema)`) before returning it. A validation failure is an engine fault (builder bug, schema mismatch, or upstream data out of contract) and raises `PassportValidationError`. This catches faults at service exit time, preventing malformed passports from propagating to the integrity or trust engines.

---

## 16. Integrity Verification Strategy

The Passport Integrity Engine (M2.4) provides two guarantees: **structural soundness** (validation) and **tamper evidence** (hashing). This section describes the verification strategy.

### Two-Phase Verification

**Phase 1: Structural Validation** — Re-checks the passport against an external rule-set (independent of the M2.3 schema, so the two can evolve separately). The rule-set declares which sections are required, which fields each section must contain, and which fields are normalized confidences. The validator produces:
- An ordered list of `CheckedSection` records (present/absent, valid/invalid)
- Ordered errors (missing required section, wrong kind, missing field, confidence out of range)
- Ordered warnings (missing optional section)
- A validation status (`VALID`, `VALID_WITH_WARNINGS`, `INVALID`)

**Phase 2: Integrity Hashing** — Computes a deterministic SHA-256 hash over the passport's canonical JSON serialization. This hash is a fingerprint: any mutation to the passport produces a different hash, making tampering detectable.

### Independent Rule-Set

The integrity engine validates against `integrity/data/rules.yaml`, which is **independent** of the passport schema `passport/data/schema.yaml`. Though the two files describe the same sections, they can evolve separately:

- The passport schema (M2.3) defines what the builder **produces**.
- The integrity rule-set (M2.4) defines what a valid passport **must satisfy**.

This separation allows the integrity engine to enforce stricter or looser constraints than the builder, and to add validation rules (e.g., marking a section optional) without touching the builder.

### The Report-vs-Raise Asymmetry

The integrity engine embodies a deliberate asymmetry central to the entire Decision Intelligence Layer:

| Fault Type | Example | Handling |
|-----------|---------|----------|
| **Engine fault** | Malformed rule-set, unsupported hash algorithm | **Raised** as `PassportIntegrityRuleError` |
| **Data fault** | Missing section, confidence out of range | **Reported** as `is_valid=False` with ordered errors |

The distinction: a malformed **engine** (bad configuration) is a bug that must be fixed; a malformed **passport** (bad data) is a verdict that downstream consumers must handle. Reporting data faults (rather than raising) keeps the report-based pipeline flow clean and lets consumers decide how to handle low-integrity passports.

### Canonical Serialization

The integrity hash is computed over `passport.to_json()` with:
- `sort_keys=True` — keys in stable alphabetical order
- Compact separators `(",", ":")` — no whitespace variation
- `ensure_ascii=False` — Unicode preserved

This canonical serialization guarantees that the same passport always produces the same hash, regardless of in-memory representation or serialization environment. The hash algorithm is configurable (default SHA-256) via `config.hash_algorithm`.

---

## 17. Trust Computation Strategy

The Trust & Provenance Engine (M2.5) synthesizes the entire pipeline's output into a single trust verdict. This section describes the trust-computation strategy.

### Four Orthogonal Axes

Trust is decomposed into four orthogonal sub-axes, each capturing a distinct trust signal:

1. **Identity Confidence** (weight 0.30) — "How well-identified is the device?" Blends identity completeness (fraction of strong fields present) with classification confidence.

2. **Evidence Consistency** (weight 0.25) — "Do the upstream reports agree?" Checks cross-report device-type agreement and the conflict flag. Ranges from 0.2 (disagreement + conflict) to 1.0 (perfect agreement).

3. **Decision Confidence** (weight 0.20) — "How confident are the decision engines?" Mean of the circular decision confidence and the decision-knowledge overall confidence.

4. **Integrity Confidence** (weight 0.25) — "Is the passport structurally sound?" Reads the integrity report's validation status: 1.0 (VALID), 1.0 − penalty (VALID_WITH_WARNINGS), 0.0 (INVALID).

The axes are orthogonal by design: a device can be well-identified but inconsistent (high identity, low evidence), or consistent but low-confidence (high evidence, low decision). Blending them captures the full trust picture; retaining them makes trust explainable.

### Weighted Blend

The trust score is the weighted average of the four axes:

```
trust_score = (identity × 0.30 + evidence × 0.25 + decision × 0.20 + integrity × 0.25) / 1.00
```

The weights (from the catalogue) sum to 1.00 in the shipped configuration, but the engine divides by the actual total weight, so the score is well-defined for any positive-weight catalogue.

### Threshold Mapping

The trust score maps to one of four trust levels via catalogue thresholds:

| Level | Floor | Interpretation |
|-------|-------|----------------|
| `HIGH` | ≥ 0.75 | Trustworthy; can be relied upon |
| `MEDIUM` | ≥ 0.50 | Reasonably trustworthy; spot-check advised |
| `LOW` | ≥ 0.25 | Low trust; verify before relying |
| `UNTRUSTED` | ≥ 0.0 | Do not rely without manual verification |

Levels are sorted by descending floor; the first level whose floor the score meets or exceeds wins. The loader guarantees a `0.0` floor, so every score resolves to exactly one level.

### Warnings

The trust engine emits ordered warnings for operator attention:
- Trust score at or below the floor (0.4) → "treat as low-trust"
- Passport failed integrity validation → "structural soundness questionable"
- Integrity report carries warnings → "review the integrity report"
- Passport itself carries warnings → "review the passport"

Warnings never change the trust level (the catalogue thresholds do that); they flag a genuinely weak verdict for attention. A low-trust passport is **reported**, never rejected.

---

## 18. Configuration

Every engine's operational knobs live in an immutable, frozen, slotted config object. Policy (weights, thresholds, contracts) lives in external catalogues; the config holds only the catalogue locator plus a handful of engine-specific projection knobs.

### Config Objects

| Config | Milestone | Fields |
|--------|-----------|--------|
| `DecisionConfig` | M2.1 | `knowledge_path`, `min_confidence` (0.05) |
| `CircularConfig` | M2.2 | `rules_path`, `min_confidence` (0.35), `identity_field_count` (4) |
| `PassportConfig` | M2.3 | `schema_path`, `passport_version` (1.0.0), `max_reasoning` (32), `max_warnings` (32) |
| `IntegrityConfig` | M2.4 | `rules_path`, `hash_algorithm` (sha256) |
| `TrustConfig` | M2.5 | `rules_path`, `min_trust_score` (0.4), `identity_field_count` (4), `integrity_warning_penalty` (0.1) |

### Environment Mapping

Every config provides a `from_settings(settings)` classmethod that maps the env-driven knobs onto the config. The mapping is explicit (one line per knob), so adding an env knob is a reviewable change:

| Setting | Default | Maps To |
|---------|---------|---------|
| `DECISION_KNOWLEDGE_PATH` | `decision/data/knowledge.yaml` | `DecisionConfig.knowledge_path` |
| `DECISION_MIN_CONFIDENCE` | `0.05` | `DecisionConfig.min_confidence` |
| `CIRCULAR_RULES_PATH` | `circular/data/rules.yaml` | `CircularConfig.rules_path` |
| `CIRCULAR_MIN_CONFIDENCE` | `0.35` | `CircularConfig.min_confidence` |
| `PASSPORT_SCHEMA_PATH` | `passport/data/schema.yaml` | `PassportConfig.schema_path` |
| `PASSPORT_VERSION` | `1.0.0` | `PassportConfig.passport_version` |
| `INTEGRITY_RULES_PATH` | `integrity/data/rules.yaml` | `IntegrityConfig.rules_path` |
| `INTEGRITY_HASH_ALGORITHM` | `sha256` | `IntegrityConfig.hash_algorithm` |
| `TRUST_RULES_PATH` | `trust/data/rules.yaml` | `TrustConfig.rules_path` |
| `TRUST_MIN_SCORE` | `0.4` | `TrustConfig.min_trust_score` |

Settings are validated by Pydantic (`ge=0.0, le=1.0` on the float knobs) and cached as an `@lru_cache(maxsize=1)` singleton, consistent with the M1.4 settings pattern documented in [02 — AI Platform Architecture].

### Path Resolution

Every config's `resolved_*_path(package_root)` method resolves a relative catalogue path against the `device_ai` package root, so the packaged catalogue is found regardless of the process working directory. Absolute paths are used verbatim.

### What Lives Where

The configuration architecture draws a clear line:

- **Config** holds: catalogue locator, projection knobs (confidence floors, field counts, penalties, hash algorithm, version, truncation limits).
- **Catalogue** holds: the actual policy (signal weights, rule precedences, schema contracts, validation rules, trust thresholds).

This separation means the config is a thin locator-plus-knobs object, while the substantive policy is versioned, reviewable, and tunable in external files.

---

## 19. Error Handling

The Decision Intelligence Layer uses a typed exception hierarchy that keeps the domain free of transport concerns while providing stable, machine-readable error codes.

### Exception Hierarchy

All exceptions derive from `DeviceAIError(message, *, details)`, which carries:
- `code` — stable machine-readable code (SCREAMING_SNAKE_CASE)
- `http_status` — suggested HTTP status hint (used by the API layer for other subsystems; unused here since these engines are internal-only)
- `details` — optional structured diagnostic context

The layer's exceptions:

| Exception | Code | Raised When |
|-----------|------|-------------|
| `DecisionError` | `DECISION_ERROR` | Base for M2.1 faults |
| `DecisionKnowledgeError` | `DECISION_KNOWLEDGE_ERROR` | Malformed knowledge catalogue |
| `CircularDecisionError` | `CIRCULAR_DECISION_ERROR` | Base for M2.2 faults |
| `CircularRuleError` | `CIRCULAR_RULE_ERROR` | Malformed rule catalogue |
| `PassportError` | `PASSPORT_ERROR` | Base for M2.3 faults |
| `PassportSchemaError` | `PASSPORT_SCHEMA_ERROR` | Malformed passport schema |
| `PassportValidationError` | `PASSPORT_VALIDATION_ERROR` | Assembled passport violates schema |
| `PassportIntegrityError` | `PASSPORT_INTEGRITY_ERROR` | Base for M2.4 faults (unsupported hash algorithm) |
| `PassportIntegrityRuleError` | `PASSPORT_INTEGRITY_RULE_ERROR` | Malformed validation rule-set |
| `PassportTrustError` | `PASSPORT_TRUST_ERROR` | Base for M2.5 faults |
| `PassportTrustRuleError` | `PASSPORT_TRUST_RULE_ERROR` | Malformed trust catalogue |

### The Raise-vs-Report Principle

The layer draws a sharp line between two fault categories:

**Engine faults — RAISED as typed exceptions:**
- Malformed catalogue/rule-set/schema (structural violation at load time)
- Unsupported hash algorithm
- Assembled passport violating its own schema (builder bug)

**Data faults — REPORTED on the produced report:**
- Low upstream confidence → low `overall_confidence` / `confidence`
- No rules fire → default fallback
- Structurally invalid passport → `is_valid=False` + ordered errors
- Low trustworthiness → `trust_level=untrusted` + ordered warnings

This principle is stated explicitly in the M2.4 and M2.5 exception docstrings: `PassportIntegrityError` signals "an engine fault — never a passport that merely fails validation"; `PassportTrustError` signals "an engine fault — never inputs that merely score as low-trust."

### Why This Matters

The raise-vs-report distinction keeps the pipeline flow clean:

- **Engine faults** are bugs — they must halt processing and surface immediately for a developer to fix. Raising a typed exception does exactly this.
- **Data faults** are verdicts — they are the engine's job to detect and report. A low-trust device is a **result**, not an error; forcing the orchestrator to catch an exception for every low-trust device would conflate "the engine broke" with "the device is low-trust."

Because all five engines are internal-only, exceptions surface directly to the orchestrating code (no HTTP error envelope). The `http_status` hints exist for consistency with the broader `DeviceAIError` hierarchy but are unused in this layer.

---

## 20. Dependency Injection

Every engine follows a consistent constructor-injection pattern that makes production wiring trivial and testing complete.

### The Injection Pattern

Each service accepts every collaborator as a keyword-only constructor argument with a sensible default:

```python
class DecisionService:
    def __init__(
        self,
        *,
        config: DecisionConfig | None = None,
        knowledge: KnowledgeBase | None = None,
        inference_engine: DecisionInferenceEngine | None = None,
        clock: Callable[[], datetime] | None = _utc_now,
        engine_version: str = DECISION_ENGINE_VERSION,
    ) -> None:
        self._config = config if config is not None else DecisionConfig()
        self._knowledge = knowledge if knowledge is not None else load_knowledge(...)
        self._inference = inference_engine if inference_engine is not None else DecisionInferenceEngine(self._config)
        self._clock = clock
        self._engine_version = engine_version
```

This pattern is identical across all five services (`DecisionService`, `CircularService`, `PassportService`, `IntegrityService`, `TrustService`).

### Injectable Collaborators

Each service injects:

1. **Config** — the operational knobs (defaults to the reference config).
2. **Catalogue** — the loaded policy/contract (defaults to loading from disk once at construction).
3. **Engine** — the pure inference/validation engine (defaults to constructing one bound to config).
4. **Clock** — a `Callable[[], datetime]` returning the current time (defaults to `_utc_now`). Pass `clock=None` to omit `created_at` entirely, making the report a pure function of its inputs.
5. **Engine version** — the version tag stamped onto reports (defaults to the module constant).

### Production vs Testing

**Production** wires nothing — every default is production-ready:
```python
service = DecisionService()  # loads shipped catalogue, uses UTC clock
```

**Testing** injects hand-built collaborators for complete isolation:
```python
service = DecisionService(
    knowledge=hand_built_knowledge_base,  # single-dimension catalogue
    clock=None,                            # omit timestamp for determinism
)
```

### The Injected Clock

The clock injection deserves special mention. Every service accepts a `clock` callable:
- **Default** (`_utc_now`) — stamps `created_at` with the current UTC time.
- **Fixed clock** (`clock=lambda: datetime(2026, 1, 1, tzinfo=UTC)`) — stamps a fixed time for reproducible test assertions.
- **No clock** (`clock=None`) — omits `created_at` entirely, making the report a pure function of its inputs (byte-identical across runs).

The no-clock mode is essential for the layer's determinism guarantee: with `clock=None`, the same inputs always produce byte-identical output, enabling content-addressed hashing and reproducible builds.

### Catalogue Loaded Once

Each service loads its catalogue exactly once, at construction, and holds it immutably. This means:
- The file is read once, not per-request.
- The catalogue is validated once (at startup), so malformed catalogues fail fast.
- Requests are pure in-memory arithmetic with no I/O.

Settings singletons use `@lru_cache(maxsize=1)`, consistent with the M1.4 pattern in [02 — AI Platform Architecture].

---

## 21. Explainability

Every engine in the Decision Intelligence Layer is designed for **explainability**: every score, action, and verdict carries ordered, human-readable reasoning that lets an operator understand exactly how the output was derived. This is a first-class architectural requirement, not an afterthought.

### Explainability Mechanisms

**Ordered reasoning** — every report carries a `reasoning` tuple of human-readable sentences describing how the output was computed. For example, M2.1's reasoning explains that dimensions are weighted means of upstream signals; M2.5's reasoning lists each axis's value, weight, and contribution.

**Ordered warnings** — every report carries a `warnings` tuple of operator-facing cautions flagging conditions that need attention (low confidence, hazards, disagreements, invalid passports).

**Evidence breakdown** — the scoring engines retain the raw evidence behind each score:
- M2.1: `DimensionEvidence` records show each dimension's ordered `EvidenceSignal` (name, value, weight).
- M2.2: `TriggeredRule` records show every fired rule (id, action, priority, precedence, reason, won flag).
- M2.5: `TrustAxis` records show each axis's value, weight, and reason.

**Winning-rule transparency** — M2.2 retains not just the winning rule but every rule that fired, so an operator can see which rules would have recommended different actions and why the winner was chosen.

### Why Explainability Matters

The EcoTrace India platform makes decisions with regulatory, environmental, and economic consequences (whether to repair, recycle, or dispose of a device; whether to trust a passport). These decisions must be:

- **Auditable** — a reviewer must be able to trace every decision back to its evidence.
- **Contestable** — an operator must be able to identify and correct a wrong decision.
- **Reproducible** — the same inputs must always produce the same explained output.

The ordered reasoning and evidence breakdowns satisfy all three requirements. Combined with the deterministic, content-addressed design, they make the entire layer a transparent, glass-box system rather than a black-box scorer.

### Example: Tracing a Trust Verdict

Given a `PassportTrustReport` with `trust_level=MEDIUM`, an operator can trace:
1. The overall reasoning: "Trust score 0.62 maps to level 'medium' via the catalogue thresholds."
2. The axis breakdown: identity 0.84 (weight 0.30), evidence 0.40 (weight 0.25), decision 0.71 (weight 0.20), integrity 1.0 (weight 0.25).
3. The low axis: evidence 0.40 with reason "Upstream reports disagree on device type ('laptop', 'tablet') with no additional conflict flagged."
4. The conclusion: the device is medium-trust because the upstream reports disagree on its type.

This full trace is available in the report itself, requiring no re-computation or external logging.

---

## 22. Testing Strategy

Every engine in the layer is deterministic and fully injectable, making it independently and exhaustively testable. This section describes the layer-wide testing strategy.

### Test Categories

Each engine is tested across four categories:

**1. Engine unit tests** — Test the pure inference/validation engine directly with hand-built inputs and hand-built catalogues:
- Signal/axis projection (each formula, edge cases)
- Blending/scoring (weighted averages, boundary conditions)
- Selection/leveling (winner selection, threshold mapping)
- Determinism (same inputs → byte-identical output when `created_at=None`)
- Reasoning/warning generation

**2. Loader tests** — Test the strict catalogue loader with valid and malformed catalogues:
- Valid catalogue loads successfully
- Every structural violation raises the correct typed exception with the correct `code` and descriptive `details`

**3. Config tests** — Test `from_settings()` maps environment onto config correctly.

**4. Service tests** — Test the injectable service end-to-end:
- Provenance stamping (engine version, catalogue version, timestamp)
- Fixed-clock injection produces expected `created_at`
- No-clock injection omits `created_at`
- Validation failures raise (M2.3) or report (M2.4, M2.5)

### Determinism Testing

The layer's determinism guarantee is tested by asserting byte-identical output for identical inputs:

```python
report_a = engine.infer(inputs, created_at=None)
report_b = engine.infer(inputs, created_at=None)
assert report_a.to_json() == report_b.to_json()  # byte-identical
```

This is critical for the content-addressed passport ID (M2.3) and the integrity hash (M2.4), both of which rely on canonical, deterministic serialization.

### Boundary Testing

Each engine's boundary conditions are tested explicitly:
- **M2.1**: all-zero weights, single signal, zero total mass, all confidences dropped
- **M2.2**: no rules fire (default), threshold boundaries (gte/gt/lte/lt), multi-condition AND
- **M2.3**: missing fingerprint, empty device type, zero materials
- **M2.4**: valid/valid-with-warnings/invalid transitions, unsupported hash algorithm
- **M2.5**: undefined consistency (no types), each evidence branch, INVALID integrity

### Loader Negative Testing

The strict loaders are tested against every documented failure mode. For example, M2.1's `load_knowledge()` is tested to raise `DecisionKnowledgeError` for: missing version, missing dimension, unknown signal, unknown confidence source, negative weight, all-zero dimension, non-positive saturation constant, non-numeric value. Each test asserts both the exception type and the `code`.

### Consistency with Prior Milestones

The testing strategy mirrors the M1.11 environmental engine (documented in [03 — Device Intelligence Architecture]), which established the external-catalogue + strict-loader + injectable-service pattern. Tests for this layer reuse the same fixtures, hand-built report builders, and assertion helpers where applicable.

---

## 23. Performance

The Decision Intelligence Layer is designed for low-latency, in-memory processing with no per-request I/O.

### Performance Characteristics

**No per-request I/O** — every catalogue is loaded once at service construction and held immutably. Requests are pure in-memory arithmetic (weighted averages, rule evaluation, hashing) with no file reads, network calls, or database queries.

**Deterministic arithmetic** — the engines perform bounded, deterministic computation:
- M2.1: 11 signal projections + 6 weighted averages + 1 confidence blend = O(signals × dimensions), constant for the fixed vocabulary
- M2.2: 16 signal projections + 10 rule evaluations (≤3 conditions each) = O(rules × conditions), constant for the catalogue
- M2.3: 8 section extractions + 1 hash + 1 validation = O(sections × fields), constant for the schema
- M2.4: 13 section validations + 1 canonical serialization + 1 hash = O(sections × fields)
- M2.5: 4 axis projections + 1 weighted average + 1 threshold scan = O(axes), constant

**No model inference** — unlike the perception tier (M1.1–M1.6), the decision layer runs no neural networks, loads no model weights, and requires no GPU. It is pure CPU arithmetic over already-computed upstream reports.

### Latency Profile

Each engine's per-request latency is dominated by:
- **M2.1–M2.2, M2.5**: floating-point arithmetic over a fixed number of signals/rules/axes — sub-millisecond.
- **M2.3**: dataclass construction + one SHA-256 hash (12-char prefix) + one schema validation — sub-millisecond.
- **M2.4**: one full canonical JSON serialization + one SHA-256 hash over the serialized bytes + 13 section validations — the serialization is the dominant cost, still sub-millisecond for a typical passport.

The entire five-stage pipeline processes one device in single-digit milliseconds on commodity CPU, with no warm-up or model-loading overhead after service construction.

### Memory Profile

- **Slotted dataclasses** — every model uses `slots=True`, eliminating per-instance `__dict__` overhead.
- **Immutable catalogues** — loaded once, shared across all requests (no per-request allocation of policy data).
- **Bounded collections** — reasoning and warnings are truncated (M2.3 limits to 32 each), preventing unbounded growth.

### Scalability

Because the engines are stateless (after construction) and perform no I/O, they scale horizontally trivially: multiple service instances share the same immutable catalogues and process requests independently. There is no shared mutable state, no locking, and no coordination overhead.

### Startup Cost

The only non-trivial cost is at service construction: each service loads and validates its catalogue once. For the five shipped catalogues (all small YAML files), total startup validation is negligible (milliseconds). Malformed catalogues fail fast at startup rather than at first request.

---

## 24. Extension Points

The layer is designed to be extended primarily through **external catalogues** (no code change) and secondarily through **code** (for new vocabulary or new engines).

### Catalogue-Only Extensions (No Code Change)

Most tuning is done by editing external catalogues and bumping their version:

| Extension | Catalogue | Change |
|-----------|-----------|--------|
| Reweight a decision dimension | `decision/data/knowledge.yaml` | Edit signal weights |
| Retune saturation constants | `decision/data/knowledge.yaml` | Edit normalization block |
| Reweight overall confidence | `decision/data/knowledge.yaml` | Edit confidence block |
| Add/reorder a decision rule | `circular/data/rules.yaml` | Add rule with unique id/precedence |
| Change the default action | `circular/data/rules.yaml` | Edit default fallback |
| Tune rule confidence damping | `circular/data/rules.yaml` | Edit confidence_factor |
| Mark a passport section optional | `integrity/data/rules.yaml` | Set required: false |
| Reweight a trust axis | `trust/data/rules.yaml` | Edit weights block |
| Retune trust thresholds | `trust/data/rules.yaml` | Edit levels block |

### Code Extensions (New Vocabulary)

Adding new terms to the fixed vocabularies requires code changes:

- **New signal (M2.1)** — project it in `DecisionInferenceEngine._signals()`, add to `CANONICAL_SIGNALS`, update loader docstring.
- **New signal (M2.2)** — project it in `CircularDecisionEngine._project_signals()`, add to `CANONICAL_SIGNALS`.
- **New dimension (M2.1)** — add enum member to `DecisionDimension`, add report field, require in loader.
- **New action/priority (M2.2)** — add enum member, update loader's allowed sets.
- **New passport section (M2.3)** — add section dataclass, extract in builder, add to schema.
- **New validation rule (M2.4)** — implement in `PassportValidator`.
- **New trust axis (M2.5)** — project in `TrustEngine`, add to `CANONICAL_AXES` and `_AXIS_ORDER`, require in loader.
- **New trust level (M2.5)** — add enum member to `TrustLevel`, update loader's allowed set.

### Code Extensions (New Engines)

The layer's design accommodates new engines that follow the established pattern:
1. Create a package under `intelligence/device_ai/` with `models.py`, `config.py`, catalogue loader, pure engine, and injectable service.
2. Add typed exceptions to `exceptions.py` (base + rule/config error).
3. Add settings knobs to `configs/settings.py` and a `from_settings()` mapping.
4. Ship an external catalogue under the package's `data/` directory.
5. Wire the engine into the orchestrating pipeline.

Any new engine inherits the layer's guarantees (determinism, versioning, auditability, injectability) by following the pattern.

### Injectable Collaborators as Extension Points

Because every collaborator is injectable, custom implementations can be substituted without modifying the service:
- A custom `KnowledgeBase`/`RuleCatalogue`/`TrustRuleSet` (e.g., loaded from a database instead of a file).
- A custom engine (e.g., a variant scoring algorithm for A/B testing).
- A custom clock (e.g., a monotonic test clock).

This makes the services open for extension but closed for modification (Open/Closed Principle).

---

## 25. Current Limitations

This section documents the current scope boundaries and known limitations of the Decision Intelligence Layer as implemented (M2.1–M2.5, version 1.0.0).

### Scope Boundaries

The layer deliberately excludes concerns owned by other subsystems:

- **No persistence** — the engines produce immutable reports but do not store them. Persistence is owned by the blockchain ledger (M3.1–M3.3) and the backend data layer (out of scope for this document).
- **No blockchain** — the passport core (M2.3) deliberately implements no blockchain, QR code, CBOR encoding, digital signature, ownership history, or lifecycle-event concern. Those are M3.x concerns.
- **No HTTP surface** — all five engines are internal-only, consumed in-process. There is no REST API, no request/response schema, no authentication.
- **No economic valuation** — the decision-knowledge engine (M2.1) produces a normalized `material_value_score` (a unit index), not a monetary value. Economic valuation is out of scope.

### Policy Limitations

- **Untuned priors** — the shipped catalogue weights (M2.1 dimension weights, M2.2 rule precedences, M2.5 axis weights) are deliberate, transparent priors meant to be tuned against real triage data before external reporting. They are reasonable defaults, not validated production values.
- **Single-catalogue versions** — each engine ships exactly one catalogue version (1.0.0). There is no catalogue A/B testing, no per-region catalogues, and no runtime catalogue switching (though the injectable design would support all three).

### Algorithmic Limitations

- **Linear scoring** — all scoring is linear (weighted averages). The engines do not capture non-linear interactions between signals (e.g., "high hazard AND low identity is worse than the sum of its parts"). Such interactions would require code changes.
- **Fixed vocabulary** — the canonical signals, dimensions, axes, and levels are fixed in code. The catalogue can re-weight but not extend the vocabulary.
- **Static rules** — the circular decision rules (M2.2) are static policy; there is no learned or adaptive rule generation.

### Determinism Constraints

- **Timestamp non-determinism** — when a real clock is injected (production default), the `created_at` field makes reports non-byte-identical across runs. Byte-identical output requires `clock=None`. The content-addressed passport ID and integrity hash are unaffected (they exclude the timestamp).

### Trust Model Limitations

- **No cryptographic provenance** — the trust engine (M2.5) assesses trustworthiness from internal consistency and confidence signals, not from cryptographic signatures or external attestation. Cryptographic provenance (digital signatures on passports) is an M3.x concern.
- **No historical trust** — trust is computed per-passport from current evidence; there is no notion of a device's or operator's trust history.

---

## 26. Future Decision Platform Evolution

This section outlines potential evolution paths for the Decision Intelligence Layer, consistent with the platform's roadmap and the layer's extensible architecture. These are forward-looking possibilities, not committed features.

### Policy Tuning & Validation

The most immediate evolution is tuning the shipped catalogue priors against real triage data:
- **Data-driven reweighting** — calibrate M2.1 dimension weights, M2.2 rule precedences, and M2.5 axis weights against labeled outcomes from actual e-waste processing.
- **Catalogue versioning workflow** — establish a review process for catalogue changes, with version bumps, changelogs, and regression tests against a golden dataset.
- **Per-region catalogues** — support region-specific policy (different regulations, material values, hazard classifications) via injectable catalogues selected by locale.

### Enhanced Trust & Provenance

- **Cryptographic provenance** — integrate digital signatures so a passport's trust verdict can be cryptographically anchored (bridging to the M3.x blockchain layer).
- **Historical trust** — incorporate a device's or operator's processing history into the trust computation, enabling reputation-based trust.
- **External attestation** — allow third-party attestations (certified recyclers, auditors) to contribute to the trust score.

### Richer Decision Models

- **Non-linear scoring** — capture signal interactions (e.g., hazard × identity) via configurable interaction terms in the catalogue.
- **Learned rules** — augment the static circular rules with learned decision boundaries trained on outcome data, while preserving the auditable rule structure.
- **Multi-objective optimization** — extend the circular engine from single-action recommendation to multi-objective trade-off (e.g., environmental benefit vs. economic value vs. processing cost).

### Economic Intelligence

- **Monetary valuation** — add an economic layer that converts the M2.1 `material_value_score` into monetary estimates using market prices and recovery costs.
- **Cost-benefit analysis** — extend the circular decision to weigh processing costs against recovery value.

### Platform Integration

- **Passport lifecycle events** — as the M3.x blockchain layer matures, the passport core could emit lifecycle events (created, verified, transferred, retired) that anchor to the ledger.
- **Streaming/batch modes** — support high-throughput batch processing of device fleets, leveraging the stateless, I/O-free engine design for trivial parallelization.
- **Explainability dashboards** — surface the ordered reasoning and evidence breakdowns in operator-facing dashboards for review and correction.

### Architectural Continuity

Any future evolution will preserve the layer's foundational guarantees:
- **Determinism** — same inputs → same outputs.
- **Auditability** — every decision carries ordered reasoning and evidence.
- **External policy** — weights, thresholds, and contracts stay in versioned catalogues.
- **Injectability** — every collaborator remains substitutable.
- **Internal-only purity** — the engines stay free of transport and persistence concerns.

These principles are what make the Decision Intelligence Layer a durable foundation: new capabilities are added by extending catalogues and following the established engine pattern, not by compromising the core design.

---

## Architecture Evolution Principles

The Decision Intelligence Layer embodies principles that should guide all future changes:

1. **Policy in catalogues, logic in code** — never hardcode a weight, threshold, or contract that could reasonably be tuned. If it is policy, it belongs in an external, versioned catalogue.

2. **Raise for engine faults, report for data faults** — a malformed catalogue is a bug (raise); a low-trust device is a verdict (report). Never conflate the two.

3. **Deterministic and content-addressed** — the same inputs must always produce the same output. Timestamps are the only permitted non-determinism, and they are excluded from content-addressed hashes.

4. **Explain everything** — every score, action, and verdict must carry ordered, human-readable reasoning and its supporting evidence.

5. **Inject every collaborator** — production wires nothing; tests inject everything. This keeps the engines open for extension and closed for modification.

6. **Version every catalogue** — stamp the catalogue version onto every report so any output can be traced to the exact policy that produced it.

7. **Internal-only purity** — the decision engines stay free of HTTP, persistence, and blockchain concerns. Those belong to other subsystems.

---

## Appendix A — Source Inspection Commands

The following commands (run from the repository root) inspect the implementation this document reverse-engineers:

```bash
# List all five Decision Intelligence engine packages
ls intelligence/device_ai/decision/    # M2.1 Decision Knowledge
ls intelligence/device_ai/circular/     # M2.2 Circular Decision
ls intelligence/device_ai/passport/     # M2.3 Device Passport Core
ls intelligence/device_ai/integrity/    # M2.4 Passport Integrity
ls intelligence/device_ai/trust/         # M2.5 Trust & Provenance

# Inspect the five external catalogues
cat intelligence/device_ai/decision/data/knowledge.yaml
cat intelligence/device_ai/circular/data/rules.yaml
cat intelligence/device_ai/passport/data/schema.yaml
cat intelligence/device_ai/integrity/data/rules.yaml
cat intelligence/device_ai/trust/data/rules.yaml

# Inspect the typed exception hierarchy (M2.1–M2.5 sections)
grep -n "class.*Error" intelligence/device_ai/exceptions.py

# Inspect the environment-driven settings knobs
grep -nE "decision_|circular_|passport_|integrity_|trust_" \
    intelligence/device_ai/configs/settings.py

# Verify no HTTP surface exists for any decision engine
grep -rl "APIRouter\|@router\|FastAPI" \
    intelligence/device_ai/decision/ \
    intelligence/device_ai/circular/ \
    intelligence/device_ai/passport/ \
    intelligence/device_ai/integrity/ \
    intelligence/device_ai/trust/    # returns nothing — internal-only
```

---

## Appendix B — Decision Intelligence Package Reference

| Milestone | Package | Engine Version | External Catalogue | Catalogue Version | HTTP Surface |
|-----------|---------|----------------|-------------------|-------------------|--------------|
| M2.1 | `decision/` | 1.0.0 | `decision/data/knowledge.yaml` | 1.0.0 | None (internal-only) |
| M2.2 | `circular/` | 1.0.0 | `circular/data/rules.yaml` | 1.0.0 | None (internal-only) |
| M2.3 | `passport/` | 1.0.0 | `passport/data/schema.yaml` | 1.0.0 | None (internal-only) |
| M2.4 | `integrity/` | 1.0.0 | `integrity/data/rules.yaml` | 1.0.0 | None (internal-only) |
| M2.5 | `trust/` | 1.0.0 | `trust/data/rules.yaml` | 1.0.0 | None (internal-only) |

### Package Internal Structure (uniform across all five)

| Module | Responsibility |
|--------|----------------|
| `models.py` | Frozen, slotted domain models (reports + value objects + enums) |
| `config.py` | Immutable config (catalogue locator + projection knobs + `from_settings`) |
| `knowledge.py` / `rules.py` / `schema.py` | Strict catalogue loader + immutable catalogue value object |
| `inference.py` / `engine.py` / `builder.py` / `validator.py` | Pure, deterministic engine (no I/O) |
| `service.py` | Injectable façade (loads catalogue once, stamps provenance, optional clock) |
| `__init__.py` | Public `__all__` exports + authoritative internal-only docstring |
| `data/*.yaml` | External versioned catalogue (policy/contract) |

### Cross-References

- **[01 — System Architecture]** — overall platform architecture, subsystem boundaries.
- **[02 — AI Platform Architecture]** — settings pattern (`@lru_cache` singletons), `/predict` contract, error envelope.
- **[03 — Device Intelligence Architecture]** — upstream engines M1.1–M1.11 (fusion, recoverability, components, materials, environmental) whose reports this layer consumes; the M1.11 external-catalogue pattern this layer mirrors.

---

*End of document. Generated from reverse-engineered implementation source of truth at `intelligence/device_ai/` (packages `decision/`, `circular/`, `passport/`, `integrity/`, `trust/`, plus shared `exceptions.py`, `configs/settings.py`, and `utils/hashing.py`). Every architectural claim in this document is grounded in the implementation as it exists; no functionality has been invented. This document covers the Decision Intelligence Layer (M2.1–M2.5) only; the Device Intelligence Layer (M1.x) is documented in [03 — Device Intelligence Architecture], and the blockchain/ledger layer (M3.x) is out of scope.*

