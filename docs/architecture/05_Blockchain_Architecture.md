# Blockchain Architecture

**Version:** 1.0.0  
**Status:** Active  
**Last Updated:** 2026-08-06

**Scope:** Blockchain Layer only (milestones M3.1–M3.3)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Blockchain Layer Overview](#2-blockchain-layer-overview)
3. [Layered Ledger Architecture](#3-layered-ledger-architecture)
4. [Ledger Core (M3.1)](#4-ledger-core-m31)
5. [Ledger Backend Abstraction (M3.2)](#5-ledger-backend-abstraction-m32)
6. [Device Lifecycle Engine (M3.3)](#6-device-lifecycle-engine-m33)
7. [Blockchain Domain Model](#7-blockchain-domain-model)
8. [Block Model](#8-block-model)
9. [Chain Model](#9-chain-model)
10. [Ledger Backend Protocol](#10-ledger-backend-protocol)
11. [Lifecycle State Machine](#11-lifecycle-state-machine)
12. [Lifecycle Validation](#12-lifecycle-validation)
13. [Hash Chain Architecture](#13-hash-chain-architecture)
14. [Configuration](#14-configuration)
15. [Error Handling](#15-error-handling)
16. [Dependency Injection](#16-dependency-injection)
17. [Deterministic Design](#17-deterministic-design)
18. [Tamper Detection](#18-tamper-detection)
19. [Testing Strategy](#19-testing-strategy)
20. [Performance](#20-performance)
21. [Security Considerations](#21-security-considerations)
22. [Extension Points](#22-extension-points)
23. [Current Limitations](#23-current-limitations)
24. [Hyperledger Integration Strategy](#24-hyperledger-integration-strategy)
25. [Future Blockchain Roadmap](#25-future-blockchain-roadmap)
26. [Design Rationale](#26-design-rationale)

---

## 1. Executive Summary

The EcoTrace India Blockchain Layer (M3.1–M3.3) is a **deterministic, tamper-evident ledger** that anchors the passport pipeline's verdicts and device lifecycle histories into immutable, verifiable chains. It consists of three tightly integrated milestones:

- **M3.1 Ledger Core** — A local, deterministic blockchain builder that chains passport verdicts (integrity hashes, trust scores) into immutable blocks linked by cryptographic hashes. No consensus, no proof-of-work, no networking.

- **M3.2 Ledger Backend Abstraction** — A technology-agnostic persistence protocol (`LedgerBackend`) with three deterministic in-memory implementations: `MemoryLedgerBackend` (default), `MockFabricLedgerBackend`, and `MockEthereumLedgerBackend`. The service depends only on the protocol, so the ledger technology can evolve without touching the domain layer.

- **M3.3 Device Lifecycle Engine** — Models a device's complete lifecycle (registration → use → collection → assessment → refurbishment/recycling → disposal) as an ordered sequence of immutable events validated against an external state machine. Ties into the ledger through the backend abstraction for anchoring and correlation.

The layer is **internal-only** (no HTTP surface), **deterministic** (same inputs → byte-identical outputs), and **purely compositional** (no inference, no evidence collection). It sits at the top of the AI-powered decision stack, consuming the three upstream reports (DevicePassport M2.3, PassportIntegrityReport M2.4, PassportTrustReport M2.5) and device lifecycle events, and emitting tamper-evident chains suitable for regulatory audit, provenance verification, and future Hyperledger Fabric anchoring.

**Key Properties:**
- Hash-chained blocks with SHA-256 integrity anchors
- Content-addressed chain identity (genesis block hash)
- Canonical JSON serialization for byte-identical reproducibility
- Injectable backends for technology independence
- External state machine for lifecycle validation
- No smart contracts, no consensus, no proof-of-work (yet)

---

## 2. Blockchain Layer Overview

The Blockchain Layer is the final stage of the EcoTrace India AI pipeline. It does not infer, classify, or decide — it **records**. Every verdict the Decision Intelligence Layer (M2.1–M2.5) produces, and every lifecycle event a device undergoes, is snapshotted into an immutable, hash-chained ledger that can be independently verified, byte-by-byte.

### Purpose

The layer serves three distinct but complementary purposes:

1. **Passport Anchoring (M3.1, M3.2)** — Chains the three upstream passport reports (passport, integrity, trust) into a tamper-evident blockchain. The chain's genesis block becomes its content-addressed identity; any mutation invalidates subsequent hashes.

2. **Technology Independence (M3.2)** — Abstracts persistence behind a protocol so the same service can write to an in-memory store, a mock Fabric channel, a mock Ethereum contract, or (future) a real Hyperledger Fabric network, without changing one line of domain logic.

3. **Lifecycle History (M3.3)** — Models a device's journey from registration through disposal as an ordered, validated event sequence. The lifecycle engine validates transitions against an external state machine and ties into the ledger for correlation (e.g., "does this device's passport chain exist?").

### Non-Goals (Explicitly Out of Scope)

The implementation is deliberately explicit about what it does **not** do. These are documented as first-class design boundaries, not omissions:

- **No Hyperledger Fabric implementation** — no SDK, chaincode, channels, or MSP. The mock Fabric backend emits Fabric-shaped metadata only.
- **No smart contracts** — no chaincode, no Solidity, no EVM. The mock Ethereum backend simulates a contract address and gas cost without any real contract.
- **No consensus or proof-of-work** — the ledger is a single-writer, deterministic data structure. There is no mining, no validator set, no Byzantine fault tolerance.
- **No networking or RPC** — everything is in-process and in-memory.
- **No digital signatures, wallets, or certificates** — records are hash-anchored, not cryptographically signed.
- **No persistence** — the default backend is a process-local dict; chains are lost on exit.
- **No GPS tracking, QR scanning, or event streaming** — lifecycle locations are free-text labels only.

These boundaries make the layer a **clean, verifiable foundation** onto which a real distributed ledger can later be attached (see [Section 24 — Hyperledger Integration Strategy](#24-hyperledger-integration-strategy)).

### Position in the Pipeline

The Blockchain Layer consumes the outputs of the Decision Intelligence Layer documented in [04 — Decision Intelligence Architecture]:

```
M2.3 DevicePassport ──────────┐
M2.4 PassportIntegrityReport ─┼──► M3.1 LedgerRecord ──► M3.1 Block ──► M3.1 Blockchain
M2.5 PassportTrustReport ─────┘                                              │
                                                                             ▼
                                                              M3.2 LedgerBackend (persist)
Device lifecycle events ─────────► M3.3 LifecycleRecord ─────────► (anchor & correlate)
```

The upstream AI engines (M1.x perception, M2.x decision) are documented in [02 — AI Platform Architecture], [03 — Device Intelligence Architecture], and [04 — Decision Intelligence Architecture]. This document covers **only** M3.1–M3.3.

---

## 3. Layered Ledger Architecture

The Blockchain Layer is organized into three cooperating packages under `intelligence/device_ai/`, mirroring the layered, catalogue-driven, injectable pattern established by the Device Intelligence (M1.x) and Decision Intelligence (M2.x) layers.

### Overall Blockchain Layer Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                       ECOTRACE BLOCKCHAIN LAYER (M3.1–M3.3)                │
│                                                                            │
│  UPSTREAM (see doc 04 — Decision Intelligence)                            │
│  ─────────────────────────────────────────────                           │
│   DevicePassport (M2.3)   PassportIntegrityReport (M2.4)                  │
│                           PassportTrustReport (M2.5)                       │
│         │                          │                     │                 │
│         └──────────────┬───────────┴─────────────────────┘                 │
│                        ▼                                                    │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  M3.1 LEDGER CORE  (ledger/)                                        │  │
│  │  ┌─────────────┐   ┌──────────────┐   ┌────────────────────────┐   │  │
│  │  │ LedgerConfig│──▶│ LedgerBuilder│──▶│ Blockchain (Block[] +   │   │  │
│  │  │ (config.py) │   │ (builder.py) │   │ BlockHeader + Record)  │   │  │
│  │  └─────────────┘   └──────────────┘   └────────────────────────┘   │  │
│  │       │ external YAML (ledger/data/ledger.yaml)                    │  │
│  └───────┼───────────────────────────────────────────────────────────┘  │
│          │                              │                                  │
│          ▼ drives                       ▼ persists via                     │
│  ┌───────────────┐          ┌──────────────────────────────────────────┐ │
│  │ LedgerService │─────────▶│  M3.2 LEDGER BACKEND ABSTRACTION          │ │
│  │ (service.py)  │          │  (backend.py)                             │ │
│  │  create/      │          │  ┌────────────────────────────────────┐  │ │
│  │  genesis/     │          │  │ LedgerBackend  (Protocol)          │  │ │
│  │  append/      │          │  ├────────────────────────────────────┤  │ │
│  │  save/load    │          │  │ MemoryLedgerBackend    (default)   │  │ │
│  │  verify       │          │  │ MockFabricLedgerBackend            │  │ │
│  └───────────────┘          │  │ MockEthereumLedgerBackend          │  │ │
│          ▲                  │  └────────────────────────────────────┘  │ │
│          │ injected         │  → LedgerReceipt (chain_id + metadata)    │ │
│          │                  └──────────────────────────────────────────┘ │
│  ┌───────┴───────────────────────────────────────────────────────────┐  │
│  │  M3.3 DEVICE LIFECYCLE ENGINE  (lifecycle/)                         │  │
│  │  ┌──────────────┐  ┌───────────────┐  ┌─────────────────────────┐  │  │
│  │  │LifecycleConfig│─▶│LifecycleEngine│─▶│ LifecycleRecord         │  │  │
│  │  │  + RuleSet    │  │ validate +    │  │ (Event[] + is_valid +   │  │  │
│  │  │  (state m/c)  │  │ compose       │  │  current_state)         │  │  │
│  │  └──────────────┘  └───────────────┘  └─────────────────────────┘  │  │
│  │   external YAML (lifecycle/data/transitions.yaml)                  │  │
│  │   LifecycleService ──depends on──▶ LedgerService (anchor/correlate)│  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  PROPERTIES: deterministic · hash-chained · canonical JSON · internal-only │
└────────────────────────────────────────────────────────────────────────────┘
```

### The Three Packages

| Milestone | Package | Role |
|-----------|---------|------|
| M3.1 | `ledger/` | Immutable block/chain builder + domain model + config |
| M3.2 | `ledger/backend.py` | Technology-agnostic persistence protocol + 3 mock backends |
| M3.3 | `lifecycle/` | Device-history state machine + validation engine + ledger anchoring |

### Architectural Layering

The layer follows a strict dependency direction (higher depends on lower, never the reverse):

```
lifecycle/  (M3.3) ──depends on──► ledger/service (M3.1/M3.2)
   │                                     │
   │                                     ▼
   │                              ledger/backend (M3.2 protocol)
   ▼                                     │
ledger/models, integrity/, trust/, passport/ (upstream, read-only)
```

- **M3.3 depends on M3.1/M3.2** — the lifecycle service injects a `LedgerService` for anchoring and correlation, depending only on the ledger's public façade.
- **M3.1 depends on M2.3/M2.4/M2.5** — the ledger builder reads (but never mutates) the three upstream passport reports.
- **M3.2 depends only on the `Blockchain` model** — backends are pure key-value stores keyed by a service-assigned `chain_id`.

This mirrors the layering discipline documented in [01 — System Architecture] and [04 — Decision Intelligence Architecture]: policy in external files, logic in code, collaborators injected, no upward dependencies.

### Ledger Service Flow Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                    LEDGER SERVICE FLOW (M3.1 + M3.2)                 │
│                                                                      │
│  passport, integrity, trust                                          │
│        │                                                             │
│        ▼                                                             │
│  ┌──────────────────┐   clock()?   ┌──────────────────────────┐    │
│  │ create_record()  │─────────────▶│ LedgerRecord             │    │
│  │ (extract fields) │              │ (passport_id, hash,       │    │
│  └──────────────────┘              │  trust_score/level, ver)  │    │
│        │                           └──────────────────────────┘    │
│        ▼                                                             │
│  ┌──────────────────┐              ┌──────────────────────────┐    │
│  │ genesis()        │─────────────▶│ Block (index 0,           │    │
│  │ create_block(    │              │  previous_hash=SENTINEL,  │    │
│  │   record, None)  │              │  record_hash=H(record))   │    │
│  └──────────────────┘              └──────────────────────────┘    │
│        │                                                             │
│        ▼                                                             │
│  ┌──────────────────┐              ┌──────────────────────────┐    │
│  │ append(chain,    │─────────────▶│ Block (index n,           │    │
│  │   ...)           │              │  previous_hash=H(prev hdr),│   │
│  │ create_block(    │              │  record_hash=H(record))   │    │
│  │   record, prev)  │              └──────────────────────────┘    │
│  └──────────────────┘                        │                      │
│        │                                      ▼                      │
│        ▼                            ┌──────────────────────────┐    │
│  ┌──────────────────┐              │ create_chain(blocks)     │    │
│  │ verify_chain()   │◀─────────────│ → verify → Blockchain    │    │
│  │ (recompute all)  │              │   (is_valid, count, ver) │    │
│  └──────────────────┘              └──────────────────────────┘    │
│                                              │                      │
│                                              ▼                      │
│  ┌──────────────────┐   chain_id = H(genesis block)                │
│  │ save(chain)      │─────────────────────────────┐                │
│  │                  │                              ▼                │
│  └──────────────────┘              ┌──────────────────────────┐    │
│                                    │ backend.write(id, chain) │    │
│                                    │ → LedgerReceipt          │    │
│                                    │   (chain_id + metadata)  │    │
│                                    └──────────────────────────┘    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 4. Ledger Core (M3.1)

### Purpose

The Ledger Core is an **immutable record assembler**, not a distributed consensus system. It consumes the three upstream artefacts the passport pipeline already produced and emits a deterministic, tamper-evident `Blockchain` that chains those records together via cryptographic hashes. Unlike the M2.3 core (which *assembles* the passport), the M2.4 engine (which *checks* it), and the M2.5 engine (which *scores* it), the ledger core carries **no inference and no evidence collection of its own**: it snapshots the three reports' key outcomes into a record, hashes it, and chains it.

### Ledger Core Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                     LEDGER CORE (M3.1)                             │
│                                                                    │
│  INPUTS (upstream passport reports)                               │
│  ┌────────────────┐ ┌────────────────────┐ ┌───────────────────┐ │
│  │ DevicePassport │ │ PassportIntegrity  │ │ PassportTrust     │ │
│  │ .passport_id   │ │ .canonical_hash    │ │ .trust_score      │ │
│  │ .passport_ver  │ │ .engine_version    │ │ .trust_level      │ │
│  └───────┬────────┘ └─────────┬──────────┘ └────────┬──────────┘ │
│          └────────────────────┼──────────────────────┘            │
│                               ▼                                    │
│                   ┌────────────────────────┐                      │
│                   │  LedgerBuilder         │                      │
│                   │  .create_record()      │                      │
│                   └───────────┬────────────┘                      │
│                               ▼                                    │
│              ┌────────────────────────────────┐                   │
│              │  LedgerRecord (payload)         │                  │
│              │  passport_id, integrity_hash,   │                  │
│              │  trust_score, trust_level,      │                  │
│              │  3× version, created_at?        │                  │
│              └───────────┬─────────────────────┘                  │
│                          ▼                                         │
│        ┌─────────────────────────────────────────┐                │
│        │  .create_block(record, previous)         │               │
│        │  ┌────────────────────────────────────┐  │               │
│        │  │ BlockHeader                        │  │               │
│        │  │  index                             │  │               │
│        │  │  previous_hash = H(prev.header)    │  │               │
│        │  │    or GENESIS_SENTINEL (0×64)      │  │               │
│        │  │  record_hash   = H(record)         │  │               │
│        │  │  timestamp?                        │  │               │
│        │  └────────────────────────────────────┘  │               │
│        │  Block = { header, record }              │               │
│        └───────────────┬──────────────────────────┘               │
│                        ▼                                           │
│        ┌─────────────────────────────────────────┐                │
│        │  .create_chain(blocks)                   │               │
│        │   verify_chain() → is_valid              │               │
│        │  Blockchain = { blocks, version,         │               │
│        │    is_valid, block_count, created_at? }  │               │
│        └─────────────────────────────────────────┘                │
│                                                                    │
│  CONFIG: hash_algorithm (sha256), blockchain_version (1.0.0),     │
│          genesis_previous_hash ("0"×64)                            │
└──────────────────────────────────────────────────────────────────┘
```

### Responsibilities

The M3.1 core is split into four modules with single, clean responsibilities:

| Module | Responsibility |
|--------|----------------|
| `models.py` | Frozen, slotted domain models: `LedgerRecord`, `BlockHeader`, `Block`, `Blockchain` |
| `config.py` | Immutable `LedgerConfig` + strict validating `load_config()` |
| `builder.py` | Deterministic `LedgerBuilder`: record/block/chain construction, hashing, verification, chain identity |
| `service.py` | Injectable `LedgerService` façade: orchestration + provenance stamping + persistence delegation |

### Inputs

- **`DevicePassport`** (M2.3) — provides `passport_id` and `passport_version`.
- **`PassportIntegrityReport`** (M2.4) — provides `canonical_hash` and `engine_version`.
- **`PassportTrustReport`** (M2.5) — provides `trust_score`, `trust_level`, and `engine_version`.

The builder reads only these fields; it never mutates the upstream reports.

### Outputs

- **`LedgerRecord`** — the immutable payload snapshot (passport id, integrity hash, trust verdict, provenance).
- **`Block`** — one immutable block (header + record).
- **`Blockchain`** — the ordered, verified chain (blocks, version, validation status, count).

Every output is canonically serializable via `to_dict()` / `to_json()` for byte-identical reproducibility.

### Collaborators

- **Upstream:** `passport.models.DevicePassport`, `integrity.models.PassportIntegrityReport`, `trust.models.PassportTrustReport` (read-only).
- **Internal:** `utils.hashing.hash_bytes` (the shared canonical hashing utility documented in [04 — Decision Intelligence Architecture]).
- **Downstream (M3.2):** `LedgerBackend` for persistence (via the service).

### Configuration

Operational policy lives in `ledger/data/ledger.yaml` (loaded by the strict `load_config()`):

| Knob | Default | Purpose |
|------|---------|---------|
| `hash_algorithm` | `sha256` | Algorithm for block/record integrity anchors (any `hashlib`-recognized name) |
| `blockchain_version` | `1.0.0` | Semantic version stamped onto every chain |
| `genesis_previous_hash` | `"0" × 64` | Sentinel `previous_hash` for the genesis block |

See [Section 14 — Configuration](#14-configuration) for the full loader validation contract.

### Dependency Relationships

```
LedgerService
  ├── LedgerConfig      (loaded once from ledger.yaml)
  ├── LedgerBuilder     (bound to config)
  │     └── hash_bytes  (utils.hashing)
  └── LedgerBackend     (M3.2 protocol; default MemoryLedgerBackend)
```

Every collaborator is constructor-injected with a production-ready default (see [Section 16 — Dependency Injection](#16-dependency-injection)).

### Error Handling

The core raises `LedgerError` (code `LEDGER_ERROR`) for **engine faults only**:
- Unsupported hash algorithm (caught in `LedgerBuilder._hash`).
- Deriving a `chain_id` from an empty chain (no genesis block to anchor on).

Loader faults raise `LedgerConfigError` (code `LEDGER_CONFIG_ERROR`). A chain that merely *fails verification* is **never raised** — it is reported as `is_valid=False` on the `Blockchain`. This raise-vs-report asymmetry is described in [Section 15 — Error Handling](#15-error-handling).

### Testing

The core is deterministic and fully injectable, enabling exhaustive unit testing: record extraction, block linking, chain verification (valid/tampered/reordered), genesis handling, empty-chain edge cases, unsupported-algorithm raising, and byte-identical determinism (with `clock=None`). See [Section 19 — Testing Strategy](#19-testing-strategy).

### Design Rationale

The core deliberately separates the **pure builder** (no I/O, no timestamps of its own) from the **service** (owns the clock and backend). This keeps hashing and verification a pure function of inputs — the property that makes the chain a reproducible, tamper-evident audit trail. Keeping operational knobs in an external, versioned file (rather than code literals) means the hash algorithm or version can be reviewed and tuned without redeploying the builder.

### Future Extension

The core is ready to accept a real distributed anchor by swapping the backend (M3.2). The hash algorithm is already configurable, so migrating to SHA-3 or a Fabric-native digest is a config change. See [Section 24 — Hyperledger Integration Strategy](#24-hyperledger-integration-strategy).

---

## 5. Ledger Backend Abstraction (M3.2)

### Purpose

The backend abstraction (M3.2) ensures the ledger service depends only on a **technology-agnostic protocol**, never a concrete store. This separates the domain concern (hash-chaining blocks) from the infrastructure concern (where chains are persisted), allowing the ledger technology to evolve — from in-memory dict to mock Fabric channel to real Hyperledger Fabric network — without touching one line of domain logic.

### Backend Abstraction Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│              LEDGER BACKEND ABSTRACTION (M3.2)                     │
│                                                                    │
│  ┌──────────────────┐                                             │
│  │ LedgerService    │────────────────────┐                        │
│  │ (M3.1 + M3.2)    │                    │                        │
│  │                  │                    │ injected               │
│  │ .save(chain)     │                    │                        │
│  │ .load(chain_id)  │                    │                        │
│  │ .exists(id)      │                    │                        │
│  │ .list_ids()      │                    │                        │
│  └──────────────────┘                    │                        │
│          │                               ▼                        │
│          │                    ┌────────────────────────────┐      │
│          │                    │ LedgerBackend (Protocol)   │      │
│          │                    │                            │      │
│          │                    │ .write(id, chain)          │      │
│          │                    │    → LedgerReceipt         │      │
│          │                    │ .read(id) → Blockchain?    │      │
│          │                    │ .exists(id) → bool         │      │
│          │                    │ .list_ids() → [str]        │      │
│          │                    └────────────────────────────┘      │
│          │                               ▲                        │
│          │            ┌──────────────────┼──────────────────┐     │
│          │            │                  │                  │     │
│          ▼            ▼                  ▼                  ▼     │
│  ┌───────────────────────┐  ┌──────────────────┐  ┌────────────┐│
│  │ MemoryLedgerBackend   │  │ MockFabricLedger │  │ MockEthereum││
│  │  (default)            │  │ Backend          │  │ LedgerBackend││
│  │                       │  │                  │  │             ││
│  │ in-memory dict        │  │ in-memory +      │  │ in-memory + ││
│  │ metadata:             │  │ Fabric metadata: │  │ Ethereum    ││
│  │  block_count          │  │  tx_id           │  │ metadata:   ││
│  │                       │  │  channel         │  │  tx_hash    ││
│  │                       │  │  block_number    │  │  (content-  ││
│  │                       │  │  block_count     │  │   addressed)││
│  │                       │  │                  │  │  nonce      ││
│  │                       │  │ monotonic tx_id  │  │  gas_used   ││
│  │                       │  │                  │  │  contract   ││
│  └───────────────────────┘  └──────────────────┘  └────────────┘│
│                                                                    │
│  PROPERTIES: protocol-only dependency · deterministic · in-memory  │
└────────────────────────────────────────────────────────────────────┘
```

### Responsibilities

The backend abstraction provides:

1. **Protocol Definition** — The `LedgerBackend` protocol (a `@runtime_checkable` typing.Protocol) declares the four operations every backend must implement: `write`, `read`, `exists`, `list_ids`.

2. **Three Mock Implementations** — Memory, mock Fabric, and mock Ethereum backends, all deterministic and in-memory, proving the abstraction works across different ledger technologies without any real SDK, network, or persistence.

3. **Receipt Contract** — Every `write` returns a `LedgerReceipt` (frozen, slotted dataclass) carrying the `chain_id` and backend-specific metadata, so callers can correlate a chain with the backend's write.

### Inputs

- **`chain_id`** (service-assigned) — the SHA-256 hash of the chain's genesis block, computed by `LedgerBuilder.chain_id()` and passed by the service.
- **`Blockchain`** — the immutable chain to store.

The backend never derives identity itself; the service owns that logic.

### Outputs

- **`LedgerReceipt`** — immutable receipt with `chain_id`, `backend` name, and technology-specific `metadata` dict.
- **`Blockchain | None`** — the stored chain, or `None` when absent.

### Collaborators

- **Service:** `LedgerService` (M3.1) — the only caller; backends are never touched directly by orchestrating code.
- **Downstream (M3.3):** `LifecycleService` anchors through the service (not directly through backends).

### Configuration

Backends have constructor-injected knobs:
- `MockFabricLedgerBackend(channel="ecotrace-ledger")` — Fabric channel name.
- `MockEthereumLedgerBackend(contract="0xEcoTraceLedger", gas_per_write=21000)` — contract address and simulated gas.
- `MemoryLedgerBackend()` — no knobs (simple dict).

### Protocol Contract

```python
@runtime_checkable
class LedgerBackend(Protocol):
    def write(self, chain_id: str, chain: Blockchain) -> LedgerReceipt: ...
    def read(self, chain_id: str) -> Blockchain | None: ...
    def exists(self, chain_id: str) -> bool: ...
    def list_ids(self) -> list[str]: ...
```

Every implementation must:
- Accept unknown `chain_id` values without raising (return `None` / `False` rather than erroring).
- Replace on write (last write wins; idempotent).
- Return deterministic receipts (monotonic counters or content-addressed hashes for metadata, never random).

### The Three Backends

| Backend | Name | Receipt Metadata | Monotonic | Content-Addressed |
|---------|------|------------------|-----------|-------------------|
| `MemoryLedgerBackend` | `"memory"` | `block_count` | No | No |
| `MockFabricLedgerBackend` | `"mock_fabric"` | `tx_id`, `channel`, `block_number`, `block_count` | Yes (`tx_id`, `block_number`) | No |
| `MockEthereumLedgerBackend` | `"mock_ethereum"` | `tx_hash`, `block_number`, `nonce`, `gas_used`, `contract`, `block_count` | Yes (`nonce`, `block_number`) | Yes (`tx_hash = 0x + H(chain.to_json())`) |

**Memory** — process-local dict; the default and the test-suite backend. No simulation of any ledger technology.

**Mock Fabric** — emits Fabric-shaped metadata (`tx_id` like `fabric-tx-00000001`, `channel`, `block_number`) so the abstraction can be exercised against a Fabric-like backend. **No Fabric SDK, chaincode, certificates, consensus, networking, or persistence.** The transaction id and block number advance monotonically with each write, deterministically given write order.

**Mock Ethereum** — emits Ethereum-shaped metadata (`tx_hash` content-addressed from the chain's canonical JSON, monotonic `nonce`/`block_number`, simulated `gas_used`, `contract` address). **No Ethereum RPC, smart contract, wallet, digital signature, networking, or persistence.** The transaction hash is the SHA-256 of the chain serialization (hex, `0x`-prefixed), so it is deterministic and unique per chain state.

### Error Handling

Backends are pure key-value stores; they raise no domain errors. A missing chain returns `None`, not an exception. The service's `save()` may raise `LedgerError` if the chain is empty (no genesis block to derive the `chain_id` from), but that is a service-layer fault, not a backend fault.

### Testing

Each backend is tested for: write-then-read round-trip, idempotent overwrite, absent-chain return (`None`), `exists()` truth, `list_ids()` completeness, receipt structure (correct `chain_id`, `backend` name, metadata shape), and deterministic metadata (monotonic or content-addressed). The mock backends are also tested for their specific metadata (Fabric `tx_id` format, Ethereum `tx_hash` determinism).

### Design Rationale

The backend abstraction exists because **the ledger domain is stable but the ledger technology is not**. The hash-chain logic, block model, and verification algorithm are deterministic and unlikely to change; the persistence mechanism (memory, Fabric, Ethereum, IPFS, a relational DB) is a deployment concern that will evolve. Keeping the domain free of transport/persistence concerns — the same principle documented in [02 — AI Platform Architecture] for the `/predict` contract and [04 — Decision Intelligence Architecture] for the decision engines — makes the layer durable.

The protocol-based design (rather than a heavyweight abstract base class or adapter pattern) is lightweight and idiomatic Python: `isinstance(backend, LedgerBackend)` works at runtime, and `mypy` validates the contract statically. The mocks exist to **prove the abstraction**, not to fake a real distributed ledger — they deliberately implement no real SDK or consensus to keep the scope boundary clear.

### Extension Strategy

Adding a real backend (e.g., `FabricLedgerBackend` wrapping the Hyperledger Fabric SDK) requires:
1. Implement the four protocol methods.
2. Map `chain_id` → Fabric key, serialize `Blockchain` → CBOR/JSON for chaincode storage.
3. Return a `LedgerReceipt` with real Fabric metadata (transaction id, block number, channel).
4. Inject the real backend into `LedgerService` at construction (or via a factory).

No change to the service, builder, or models. See [Section 24 — Hyperledger Integration Strategy](#24-hyperledger-integration-strategy).

---

## 6. Device Lifecycle Engine (M3.3)

### Purpose

The Device Lifecycle Engine models the **complete lifecycle of a device as an ordered sequence of immutable events** — from first registration through use, collection, transport, assessment, refurbishment or recycling, to final disposal. It sits *above* the M3.1 ledger core: where the ledger core chains passport *verdicts*, this engine chains a device's *history*, then ties into the ledger (through the M3.2 backend abstraction) for anchoring and correlation.

The engine derives **no new inference and collects no new evidence**: it accepts lifecycle events, validates their ordering against an external state machine, and composes them into an immutable, canonically serializable record.

### Responsibilities

| Module | Responsibility |
|--------|----------------|
| `models.py` | `LifecycleEventType` enum, `LifecycleEvent`, `LifecycleRecord` (frozen, slotted) |
| `config.py` | Immutable `LifecycleConfig` (rules locator) + `from_settings()` |
| `rules.py` | `LifecycleTransition`, `LifecycleRuleSet` + strict validating `load_rules()` |
| `engine.py` | Deterministic `LifecycleEngine`: `validate`, `build_record`, `can_append` |
| `service.py` | Injectable `LifecycleService` façade: build/append + ledger anchoring |

### Inputs

- **`device_id`** — the id of the device (typically the passport id that anchors device identity).
- **An ordered sequence of `LifecycleEvent`** — each with an event type and optional actor, location, note, and timestamp.

### Outputs

- **`LifecycleRecord`** — the immutable, ordered history: device id, events, validity verdict (`is_valid`), event count, current state, and provenance (engine/rules versions, optional timestamp).

### Collaborators

- **Rules:** `LifecycleRuleSet` (loaded from `transitions.yaml`).
- **Engine:** `LifecycleEngine` (pure validation/composition).
- **Ledger (M3.1/M3.2):** injected `LedgerService` for anchoring/correlation — the lifecycle service depends only on this façade, whose persistence goes through the `LedgerBackend` protocol.

### Configuration

The only knob is the rules locator, env-mappable via `LIFECYCLE_RULES_PATH`:

| Knob | Default | Purpose |
|------|---------|---------|
| `rules_path` | `lifecycle/data/transitions.yaml` | Locator of the external state machine |

The substantive policy (which transitions are legal, which events start/end a lifecycle) lives entirely in the external rules file, keeping the config a thin locator.

### Dependency Relationships

```
LifecycleService
  ├── LifecycleConfig    (rules locator)
  ├── LifecycleRuleSet   (loaded once from transitions.yaml)
  ├── LifecycleEngine    (pure validate/compose)
  └── LedgerService      (M3.1/M3.2; injected for anchoring)
        └── LedgerBackend (protocol; memory by default)
```

### Error Handling

The engine raises `LifecycleError` (code `LIFECYCLE_ERROR`) only for engine faults, and `LifecycleRuleError` (code `LIFECYCLE_RULE_ERROR`) for malformed rules files. A lifecycle that merely **violates a transition** is **never raised** — it is reported as `is_valid=False` on the `LifecycleRecord`, so callers can inspect *why* it failed rather than catching an exception. This mirrors the M3.1 ledger asymmetry.

### Testing

The engine is deterministic and injectable: tests cover valid paths (each legal transition), invalid paths (illegal transition, non-initial genesis, event after terminal), empty/single-event records, `can_append` predicate, byte-identical determinism, and provenance stamping. The loader is tested against every documented failure mode (see [Section 12 — Lifecycle Validation](#12-lifecycle-validation)).

### Design Rationale

Separating the **state machine (policy)** into an external, versioned file from the **validation algorithm (logic)** in code means the legal transitions can be reviewed, tuned, or corrected by domain experts without redeploying the engine. The fixed `LifecycleEventType` vocabulary (in code) ensures a typo in the rules file is a load-time error, not a silent drop. Modeling a rejected history as *data* (`is_valid=False`) rather than an *exception* keeps the pipeline flow clean — a device with an anomalous history is a reportable finding, not a crash.

### Future Extension

The engine could emit ledger blocks per lifecycle event (anchoring the full history, not just the passport verdict), incorporate actor authorization, or add event-level digital signatures — all without changing the core validate/compose logic. See [Section 25 — Future Blockchain Roadmap](#25-future-blockchain-roadmap).

---

## 7. Blockchain Domain Model

All three milestones share a consistent domain-model design inherited from the Decision Intelligence Layer (documented in [04 — Decision Intelligence Architecture]). Every model is a frozen, slotted dataclass with no HTTP/I-O concerns, making the whole layer deterministic and independently testable.

### Model Design Conventions

Every domain model honors these conventions:

- **Immutability** — `@dataclass(frozen=True, slots=True)`. Once constructed, a model cannot be mutated. This guarantees that a record or chain handed to a downstream component cannot be accidentally modified.
- **Slotted** — `slots=True` eliminates per-instance `__dict__`, reducing memory footprint and preventing accidental attribute addition.
- **Serialization** — every model exposes `to_dict()` returning a plain JSON-serializable dict, and `to_json(*, indent=None)` producing canonical JSON (sorted keys, fixed separators, compact by default).
- **Provenance** — every high-level model carries version fields and an optional `created_at` timestamp.
- **Ordered collections** — events, blocks, and warnings are tuples (ordered, immutable), preserving deterministic output.

### Ledger Models (M3.1)

| Model | Key Fields |
|-------|-----------|
| `LedgerRecord` | passport_id, integrity_hash, trust_score, trust_level, 3× engine versions, created_at? |
| `BlockHeader` | index, previous_hash, record_hash, timestamp? |
| `Block` | header, record |
| `Blockchain` | blocks (tuple), version, is_valid, block_count, created_at? |

### Lifecycle Models (M3.3)

| Model | Key Fields |
|-------|-----------|
| `LifecycleEvent` | event_type, actor, location, note, occurred_at? |
| `LifecycleRecord` | device_id, events (tuple), is_valid, event_count, current_state, engine/rules versions, created_at? |

### Value Objects

Supporting value objects make the layer explainable:

- **`LedgerReceipt`** (M3.2) — chain_id, backend name, metadata dict (immutable receipt from backend write).
- **`LifecycleTransition`** (M3.3) — source event type, targets tuple, `allows()` predicate.
- **`LifecycleRuleSet`** (M3.3) — version, transitions tuple, initial_events tuple, `terminal_events` property, `transition_for()`/`is_initial()`/`allows()` queries.

### Enumerations

**`LifecycleEventType`** (M3.3) — `str` enum so members serialize to their wire value directly:
- `REGISTERED`, `IN_USE`, `COLLECTED`, `IN_TRANSIT`, `ASSESSED`, `REFURBISHED`, `RECYCLED`, `DISPOSED`

The enum is the single source of truth the external transition rules are validated against on load.

---

## 8. Block Model

The `Block` is the atomic unit the blockchain is built from. Each block carries one `LedgerRecord` (the payload) and one `BlockHeader` (the chain link and integrity anchor).

### Block Structure Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                         BLOCK STRUCTURE                            │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  BlockHeader                                                │  │
│  │  ┌──────────────────────────────────────────────────────┐  │  │
│  │  │ index: int         (block's position in chain, 0-based)│ │  │
│  │  │ timestamp: datetime? (when block was created)         │  │  │
│  │  │ previous_hash: str   (SHA-256 of prior header JSON,   │  │  │
│  │  │                      or GENESIS_SENTINEL "0"×64)      │  │  │
│  │  │ record_hash: str     (SHA-256 of record JSON)         │  │  │
│  │  └──────────────────────────────────────────────────────┘  │  │
│  │                                                                │  │
│  │  .to_json() → canonical JSON (sorted keys, fixed separators)│  │
│  └────────────────────────────────────────────────────────────┘  │
│                         ▲ hash chain link                         │
│                         │                                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  LedgerRecord                                               │  │
│  │  ┌──────────────────────────────────────────────────────┐  │  │
│  │  │ passport_id: str                                     │  │  │
│  │  │ integrity_hash: str  (from PassportIntegrityReport) │  │  │
│  │  │ trust_score: float   (from PassportTrustReport)     │  │  │
│  │  │ trust_level: str     (high/medium/low/untrusted)    │  │  │
│  │  │ passport_version: str                               │  │  │
│  │  │ integrity_engine_version: str                       │  │  │
│  │  │ trust_engine_version: str                           │  │  │
│  │  │ created_at: datetime?                               │  │  │
│  │  └──────────────────────────────────────────────────────┘  │  │
│  │                                                                │  │
│  │  .to_json() → canonical JSON (sorted keys, fixed separators)│  │
│  └────────────────────────────────────────────────────────────┘  │
│                         ▲ integrity anchor                        │
│                                                                    │
│  Block = { header, record }                                       │
│  .to_dict() → plain dict (header.to_dict(), record.to_dict())    │
│  .to_json() → canonical JSON (entire block)                       │
└────────────────────────────────────────────────────────────────────┘
```

### Header Properties

The header links blocks together and anchors the record:

- **`index`** — zero-based position (genesis block is index 0).
- **`previous_hash`** — SHA-256 digest of the prior block's header (canonically serialized), or the genesis sentinel (`"0" × 64`) for the first block. This is the **chain link**.
- **`record_hash`** — SHA-256 digest of this block's record (canonically serialized). This is the **integrity anchor**: tampering with the record invalidates this hash.
- **`timestamp`** — UTC timestamp the block was created (`None` when the builder was constructed with `clock=None`).

### Record Properties

The record is the **payload snapshot** extracted from the three upstream reports:

- Passport id (the device identity anchor)
- Integrity hash (the passport's canonical SHA-256 digest from M2.4)
- Trust score and level (the trustworthiness verdict from M2.5)
- Three engine versions (passport, integrity, trust)
- Optional creation timestamp

### Deterministic Serialization

Both header and record expose `to_json()` with canonical serialization:
- Keys sorted alphabetically (`sort_keys=True`)
- Non-ASCII preserved (`ensure_ascii=False`)
- Fixed separators (`(",", ":")` compact, `(",", ": ")` pretty-printed)

This guarantees the same header/record always serializes to the exact same bytes, making hashing reproducible.

---

## 9. Chain Model

The `Blockchain` is the immutable, ordered chain: blocks linked by cryptographic hashes, with validation status and provenance.

### Chain Properties

| Field | Type | Purpose |
|-------|------|---------|
| `blocks` | `tuple[Block, ...]` | Ordered blocks from genesis (index 0) onward |
| `version` | `str` | Blockchain structure version (from config, e.g. `"1.0.0"`) |
| `is_valid` | `bool` | Whether the chain passes structural validation |
| `block_count` | `int` | Number of blocks (convenience accessor) |
| `created_at` | `datetime \| None` | When the chain was assembled (None when service has no clock) |

### Validation Semantics

A chain is valid when:
1. **Sequential indices** — blocks are numbered 0, 1, 2, ... with no gaps.
2. **Previous-hash linking** — every block's `previous_hash` matches the SHA-256 digest of the prior block's header (or the genesis sentinel for index 0).
3. **Record-hash matching** — every block's `record_hash` matches the SHA-256 digest of its record.

The `LedgerBuilder.verify_chain()` method recomputes every hash and checks the ordering, detecting any tampering with a block's contents or the chain's order.

### Content-Addressed Chain Identity

The chain's identity is derived from its **genesis block** (index 0):

```
chain_id = SHA-256( genesis_block.to_json() )
```

This is a **content-addressed anchor**: equal genesis blocks yield equal chain ids, and the id does not change as blocks are appended (the genesis block is immutable). It is what the service hands to the backend as the storage key.

---

## 10. Ledger Backend Protocol

The `LedgerBackend` protocol (M3.2) is the contract every backend must satisfy. It is a `@runtime_checkable` typing.Protocol, making it lightweight and idiomatic Python.

### Protocol Operations

```python
@runtime_checkable
class LedgerBackend(Protocol):
    def write(self, chain_id: str, chain: Blockchain) -> LedgerReceipt: ...
    def read(self, chain_id: str) -> Blockchain | None: ...
    def exists(self, chain_id: str) -> bool: ...
    def list_ids(self) -> list[str]: ...
```

### Operation Semantics

**`write(chain_id, chain)`** — persist `chain` under `chain_id` (replacing any existing chain). Returns a `LedgerReceipt` carrying the `chain_id` and backend-specific metadata. Last write wins; idempotent.

**`read(chain_id)`** — return the stored blockchain for `chain_id`, or `None` if absent. Never raises on an unknown id.

**`exists(chain_id)`** — return whether a blockchain is stored for `chain_id`. A convenience predicate.

**`list_ids()`** — return all stored chain ids (order is not guaranteed). Used for enumeration and correlation.

### Receipt Structure

Every `write` returns a `LedgerReceipt`:

| Field | Type | Purpose |
|-------|------|---------|
| `chain_id` | `str` | The service-assigned identifier |
| `backend` | `str` | Backend name (`"memory"` / `"mock_fabric"` / `"mock_ethereum"`) |
| `metadata` | `dict[str, object]` | Technology-specific write details (tx_id, gas, block_number, etc.) |

The receipt is immutable (frozen, slotted) and exposes `to_dict()` for serialization.

### Why a Protocol, Not an ABC

The protocol-based design (rather than an abstract base class) is lightweight: `isinstance(backend, LedgerBackend)` works at runtime via `@runtime_checkable`, and `mypy` validates the contract statically. No need to inherit, no need for boilerplate `super()` calls. Any object that implements the four methods satisfies the protocol.

---

## 11. Lifecycle State Machine

The Device Lifecycle Engine (M3.3) validates event sequences against an external state machine loaded from `lifecycle/data/transitions.yaml`. This section describes the state machine's structure and the shipped policy.

### Lifecycle State Machine Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│              DEVICE LIFECYCLE STATE MACHINE (M3.3)                 │
│                                                                    │
│  INITIAL: [registered]  (lifecycle begins here)                   │
│                                                                    │
│                                                                    │
│  ┌────────────┐                                                   │
│  │ registered │────┬──────────────┐                               │
│  └────────────┘    │              │                               │
│       Genesis      ▼              ▼                               │
│              ┌──────────┐    ┌───────────┐                        │
│              │ in_use   │    │ collected │◀───────┐               │
│              └────┬─────┘    └─────┬─────┘        │               │
│                   │                 │              │               │
│                   │                 ▼              │               │
│                   │          ┌─────────────┐      │               │
│                   │          │ in_transit  │──────┤               │
│                   │          └──────┬──────┘      │               │
│                   │                 │             │               │
│                   └─────────────────┼─────────────┘               │
│                                     ▼                              │
│                              ┌─────────────┐                       │
│                              │  assessed   │                       │
│                              └──────┬──────┘                       │
│                                     │                              │
│                    ┌────────────────┼────────────────┐             │
│                    ▼                ▼                ▼             │
│              ┌───────────┐    ┌──────────┐    ┌──────────┐        │
│              │refurbished│    │ recycled │    │ disposed │        │
│              └─────┬─────┘    └────┬─────┘    └──────────┘        │
│                    │                │              Terminal        │
│                    ├────────────────┘                              │
│                    ▼                                               │
│              ┌──────────┐                                          │
│              │ in_use   │ (second life)                            │
│              └────┬─────┘                                          │
│                   │                                                │
│                   ▼                                                │
│              ┌───────────┐                                         │
│              │ collected │                                         │
│              └───────────┘ ... (repeats)                           │
│                                                                    │
│  KEY PROPERTIES:                                                   │
│  • Initial events: registered (genesis)                            │
│  • Terminal event: disposed (no successors)                        │
│  • Cyclic path: refurbished → in_use → collected (second life)    │
│  • No self-transitions (an event may not follow itself)            │
└────────────────────────────────────────────────────────────────────┘
```

### Event Types

The fixed vocabulary (in `LifecycleEventType` enum):

| Event Type | Wire Value | Meaning |
|------------|-----------|---------|
| `REGISTERED` | `"registered"` | Device passport first minted |
| `IN_USE` | `"in_use"` | Device in service life |
| `COLLECTED` | `"collected"` | Device handed to collector for end-of-life handling |
| `IN_TRANSIT` | `"in_transit"` | Device moving between facilities |
| `ASSESSED` | `"assessed"` | Device graded (condition, hazard, value) |
| `REFURBISHED` | `"refurbished"` | Device refurbished (back to use or resale) |
| `RECYCLED` | `"recycled"` | Materials recovered |
| `DISPOSED` | `"disposed"` | Final disposal (terminal) |

### Shipped Transitions (Version 1.0.0)

The external rules file declares:

| Source | Targets | Notes |
|--------|---------|-------|
| `registered` | `in_use`, `collected` | A freshly registered device goes into service or straight to collection |
| `in_use` | `collected` | An in-use device is eventually collected |
| `collected` | `in_transit`, `assessed` | Collected device moves toward assessment, possibly via transit |
| `in_transit` | `assessed`, `collected` | In transit, device arrives to be assessed or collected again at next hop |
| `assessed` | `refurbished`, `recycled`, `disposed` | Once assessed, device is refurbished, recycled, or disposed of |
| `refurbished` | `in_use`, `recycled` | Refurbished device re-enters service or is recycled later (second life) |
| `recycled` | `disposed` | Recycling recovers materials; residual is disposed of |
| `disposed` | (empty) | Terminal — no event may follow |

### Initial and Terminal Events

- **Initial (genesis):** `registered` — a lifecycle must begin here.
- **Terminal:** `disposed` — a lifecycle ends here (empty successor set).

### Validation Rules

The engine validates that:
1. The first event is a declared initial event (`registered`).
2. Every subsequent event is a declared successor of its predecessor.
3. No event follows a terminal event (`disposed`).
4. No self-transitions (an event type may not follow itself; caught at load time).

### Cyclic Paths

The state machine deliberately permits cycles: a refurbished device can re-enter use, be collected again, and flow through the system a second time. This models the reality of device refurbishment and resale.

---

## 12. Lifecycle Validation

The `LifecycleEngine.validate()` method is the heart of M3.3. It checks an ordered event sequence against the loaded rules and returns a boolean verdict.

### Validation Algorithm

```python
def validate(events: Sequence[LifecycleEvent], rules: LifecycleRuleSet) -> bool:
    if not events:
        return True  # Empty lifecycle is trivially valid
    
    if not rules.is_initial(events[0].event_type):
        return False  # First event must be initial
    
    for previous, current in zip(events, events[1:]):
        transition = rules.transition_for(previous.event_type)
        if transition is None or not transition.allows(current.event_type):
            return False  # Illegal transition or terminal event followed
    
    return True
```

### Validation Stages

**Stage 1: Empty Check** — an empty event sequence is trivially valid (an empty lifecycle).

**Stage 2: Initial Check** — the first event must be in the rules' `initial_events` set. A lifecycle beginning with `in_use` or `collected` (rather than `registered`) fails this check.

**Stage 3: Transition Check** — for each adjacent pair `(previous, current)`, the rules must declare `current` as a legal successor of `previous`. A transition not in the rules, or an event following a terminal event (which has an empty successor set), fails this check.

### The Report-vs-Raise Asymmetry

A lifecycle that fails validation is **reported** (`is_valid=False` on the `LifecycleRecord`), never **raised**. This mirrors the M3.1 ledger asymmetry and the M2.4/M2.5 integrity/trust asymmetry documented in [04 — Decision Intelligence Architecture]: a malformed **engine** (bad rules file) is a bug and raises a typed exception; a malformed **lifecycle** (bad event sequence) is a verdict and is reported.

This keeps the orchestration clean: a device with an anomalous history is a reportable finding (for manual review, audit flagging, or alert), not an exception that halts the pipeline.

### Incremental Validation

The service exposes a `can_append(record, next_event)` convenience predicate for callers building a lifecycle incrementally:
- An empty record accepts any initial event.
- A non-empty record accepts an event only when it is a declared successor of the record's current (latest) event type.

This lets orchestrating code validate one transition at a time without re-running full validation on the entire history.

---

## 13. Hash Chain Architecture

The Blockchain Layer's tamper-evidence comes from **hash chaining**: every block's header carries the SHA-256 digest of the prior block's header, forming a cryptographic chain. Any modification to a block or its order invalidates subsequent hashes.

### Hash Chain Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                     HASH CHAIN ARCHITECTURE                        │
│                                                                    │
│  GENESIS BLOCK (index 0)                                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ BlockHeader                                                 │  │
│  │   index: 0                                                  │  │
│  │   previous_hash: "0000...0000" (64 zero chars, sentinel)   │  │
│  │   record_hash: SHA-256(LedgerRecord.to_json())             │  │
│  │   timestamp: datetime?                                      │  │
│  └────────────────────────────────────────────────────────────┘  │
│          │ canonical JSON                                         │
│          ▼                                                         │
│  h0 = SHA-256(header.to_json())  ◀────┐ chain link               │
│                                        │                           │
│  BLOCK 1 (index 1)                     │                           │
│  ┌────────────────────────────────────┼───────────────────────┐  │
│  │ BlockHeader                         │                       │  │
│  │   index: 1                          │                       │  │
│  │   previous_hash: h0 ────────────────┘                       │  │
│  │   record_hash: SHA-256(LedgerRecord.to_json())             │  │
│  │   timestamp: datetime?                                      │  │
│  └────────────────────────────────────────────────────────────┘  │
│          │ canonical JSON                                         │
│          ▼                                                         │
│  h1 = SHA-256(header.to_json())  ◀────┐ chain link               │
│                                        │                           │
│  BLOCK 2 (index 2)                     │                           │
│  ┌────────────────────────────────────┼───────────────────────┐  │
│  │ BlockHeader                         │                       │  │
│  │   index: 2                          │                       │  │
│  │   previous_hash: h1 ────────────────┘                       │  │
│  │   record_hash: SHA-256(LedgerRecord.to_json())             │  │
│  │   timestamp: datetime?                                      │  │
│  └────────────────────────────────────────────────────────────┘  │
│          │ canonical JSON                                         │
│          ▼                                                         │
│  h2 = SHA-256(header.to_json())  (and so on...)                   │
│                                                                    │
│  TAMPER DETECTION:                                                 │
│  • Modify any block's record → record_hash mismatch               │
│  • Reorder blocks → previous_hash mismatch                        │
│  • Insert/delete a block → indices non-sequential                 │
│  • Modify any header field → subsequent previous_hash mismatch    │
│                                                                    │
│  VERIFICATION: recompute every hash; check every link.            │
└────────────────────────────────────────────────────────────────────┘
```

### Cryptographic Properties

**SHA-256** — 256-bit (64 hex char) collision-resistant, preimage-resistant, avalanche-effect hash. A single-bit change to the input produces a completely different digest.

**Canonical Serialization** — every header and record serializes to JSON with sorted keys, fixed separators, and no whitespace variation, guaranteeing the same input always produces the same hash.

**Chaining** — each block's `previous_hash` is the SHA-256 of the prior block's entire header (not just one field). This chains the blocks together: tampering with any prior block invalidates all subsequent `previous_hash` values.

**Record Anchoring** — each block's `record_hash` is the SHA-256 of its record. Tampering with the record (changing a trust score, passport id, or version) invalidates this hash.

### Tamper Scenarios

| Tampering Attempt | Detection |
|-------------------|-----------|
| Modify a record's trust score | `record_hash` no longer matches the record's canonical hash |
| Reorder two blocks | Block n's `previous_hash` no longer matches block n-1's header hash |
| Insert a new block between existing blocks | Indices non-sequential; `previous_hash` mismatch |
| Delete a block | Indices non-sequential; `previous_hash` mismatch |
| Modify a block's timestamp or index | Subsequent blocks' `previous_hash` values no longer match |

### Verification Process

The `LedgerBuilder.verify_chain()` method recomputes every hash and checks every link:

```python
for i, block in enumerate(blocks):
    # Check sequential indices starting from 0
    if block.index != i:
        return False
    
    # Check previous-hash linking
    expected_previous = (
        genesis_sentinel if i == 0
        else SHA-256(blocks[i-1].header.to_json())
    )
    if block.previous_hash != expected_previous:
        return False
    
    # Check record-hash matching
    expected_record_hash = SHA-256(block.record.to_json())
    if block.record_hash != expected_record_hash:
        return False

return True
```

Any failure returns `False` immediately; the chain is marked `is_valid=False`.

---

## 14. Configuration

Like the Decision Intelligence Layer documented in [04 — Decision Intelligence Architecture], operational policy lives in external, versioned files rather than code. This keeps the builder/engine logic stable while policy can be reviewed and tuned.

### Ledger Configuration (M3.1)

Loaded from `ledger/data/ledger.yaml` via the strict `load_config()`:

```yaml
version: "1.0.0"
hash_algorithm: "sha256"
blockchain_version: "1.0.0"
genesis_previous_hash: "0000...0000"  # 64 zero characters
```

| Field | Validation | Purpose |
|-------|------------|---------|
| `version` | Non-empty string | Config document version |
| `hash_algorithm` | Non-empty, in `hashlib.algorithms_available` | Hash for block/record anchors (sha256, sha3_256, sha512, etc.) |
| `blockchain_version` | Non-empty string | Semantic version stamped onto every chain |
| `genesis_previous_hash` | Non-empty hex string | Sentinel `previous_hash` for the first block |

The loader validates aggressively and raises `LedgerConfigError` (code `LEDGER_CONFIG_ERROR`) on any structural problem.

### Lifecycle Configuration (M3.3)

Loaded from `lifecycle/data/transitions.yaml` via the strict `load_rules()`:

```yaml
version: "1.0.0"
initial_events:
  - registered
transitions:
  registered:
    - in_use
    - collected
  in_use:
    - collected
  # ... (complete state machine)
  disposed: []  # terminal
```

| Field | Validation | Purpose |
|-------|------------|---------|
| `version` | Non-empty string | Rules document version |
| `initial_events` | Non-empty list of known event types, no duplicates | Legal genesis events |
| `transitions` | Every `LifecycleEventType` declared exactly once, at least one terminal (empty targets), no self/duplicate targets | Per-event successor sets |

The loader validates aggressively and raises `LifecycleRuleError` (code `LIFECYCLE_RULE_ERROR`) on any structural problem.

### Environment Mapping

Only the lifecycle rules locator is env-mappable:

| Setting | Default | Maps To |
|---------|---------|---------|
| `LIFECYCLE_RULES_PATH` | `lifecycle/data/transitions.yaml` | `LifecycleConfig.rules_path` |

The ledger config (M3.1) has no env-driven knobs in the shipped implementation — its policy lives entirely in the YAML file. The `from_settings()` method exists to mirror the pattern and provide a hook for future env-driven configuration.

### Path Resolution

Both configs resolve relative paths against the `device_ai` package root, so packaged files are found regardless of the process working directory:

```python
config.resolved_config_path(package_root=device_ai_root)
config.resolved_rules_path(package_root=device_ai_root)
```

Absolute paths are used verbatim.

---

## 15. Error Handling

The Blockchain Layer uses a typed exception hierarchy that keeps the domain free of transport concerns while providing stable, machine-readable error codes.

### Exception Hierarchy

All exceptions derive from `DeviceAIError(message, *, details)`, documented in [02 — AI Platform Architecture]. The blockchain-specific exceptions:

| Exception | Code | HTTP Hint | Raised When |
|-----------|------|-----------|-------------|
| `LedgerError` | `LEDGER_ERROR` | 500 | Base for M3.1 faults |
| `LedgerConfigError` | `LEDGER_CONFIG_ERROR` | 422 | Malformed ledger config file |
| `LifecycleError` | `LIFECYCLE_ERROR` | 500 | Base for M3.3 faults |
| `LifecycleRuleError` | `LIFECYCLE_RULE_ERROR` | 422 | Malformed lifecycle transition-rules file |

### The Raise-vs-Report Principle

The layer draws a sharp line between two fault categories, documented consistently across M3.1, M3.2, M3.3 and mirroring the M2.4/M2.5 asymmetry in [04 — Decision Intelligence Architecture]:

**Engine faults — RAISED as typed exceptions:**
- Malformed config/rules file (structural violation at load time)
- Unsupported hash algorithm
- Deriving a `chain_id` from an empty chain (no genesis block to anchor on)

**Data faults — REPORTED on the produced model:**
- Chain that fails verification → `is_valid=False` on `Blockchain`
- Lifecycle that violates a transition → `is_valid=False` on `LifecycleRecord`

This principle is stated explicitly in the exception docstrings: `LedgerError` signals "an engine fault (a malformed config file, an unsupported hash algorithm) — never a chain that merely fails verification"; `LifecycleError` signals "an engine fault — never a lifecycle that merely violates a transition rule."

### Why This Matters

The raise-vs-report distinction keeps the orchestration clean:

- **Engine faults** are bugs — they must halt processing and surface immediately for a developer to fix. Raising a typed exception does exactly this.
- **Data faults** are verdicts — they are the engine's job to detect and report. A tampered chain or an anomalous device history is a **result**, not an error; forcing the orchestrator to catch an exception for every invalid chain would conflate "the engine broke" with "the chain is invalid."

Because M3.1 and M3.3 are internal-only, exceptions surface directly to the orchestrating code (no HTTP error envelope). The `http_status` hints exist for consistency with the broader `DeviceAIError` hierarchy but are unused in this layer.

---

## 16. Dependency Injection

Every service follows a consistent constructor-injection pattern inherited from the Decision Intelligence Layer (documented in [04 — Decision Intelligence Architecture]). Production wires nothing; tests inject everything.

### The Injection Pattern

Each service accepts every collaborator as a keyword-only constructor argument with a sensible default:

```python
class LedgerService:
    def __init__(
        self,
        *,
        config: LedgerConfig | None = None,
        builder: LedgerBuilder | None = None,
        backend: LedgerBackend | None = None,
        clock: Callable[[], datetime] | None = _utc_now,
    ) -> None:
        self._config = config if config is not None else load_config(...)
        self._builder = builder if builder is not None else LedgerBuilder(self._config)
        self._backend = backend if backend is not None else MemoryLedgerBackend()
        self._clock = clock
```

The pattern is identical across `LedgerService` (M3.1/M3.2) and `LifecycleService` (M3.3).

### Injectable Collaborators

| Service | Injected Collaborators |
|---------|----------------------|
| `LedgerService` | config, builder, backend (M3.2 protocol), clock |
| `LifecycleService` | config, rules, engine, ledger (M3.1/M3.2 service), clock |

### Production vs Testing

**Production** wires nothing — every default is production-ready:
```python
ledger = LedgerService()  # loads config from ledger.yaml, memory backend, UTC clock
lifecycle = LifecycleService()  # loads rules from transitions.yaml, injects fresh ledger
```

**Testing** injects hand-built collaborators for complete isolation:
```python
ledger = LedgerService(
    config=LedgerConfig(hash_algorithm="sha256", ...),
    backend=MockFabricLedgerBackend(channel="test-channel"),
    clock=None,  # omit timestamps for byte-identical determinism
)
```

### The Injected Clock

Every service accepts a `clock` callable:
- **Default** (`_utc_now`) — stamps `created_at` with the current UTC time.
- **Fixed clock** (`clock=lambda: datetime(2026, 1, 1, tzinfo=UTC)`) — stamps a fixed time for reproducible test assertions.
- **No clock** (`clock=None`) — omits `created_at` entirely, making every artefact (record, block, chain, lifecycle) a pure function of its inputs (byte-identical across runs).

The no-clock mode is essential for the layer's determinism guarantee.

### Backend Injection (M3.2)

The `LedgerService` depends only on the `LedgerBackend` protocol, not a concrete backend. This makes swapping backends trivial:

```python
# In-memory (default)
service = LedgerService()

# Mock Fabric
service = LedgerService(backend=MockFabricLedgerBackend(channel="ecotrace-ledger"))

# Mock Ethereum
service = LedgerService(backend=MockEthereumLedgerBackend(contract="0xEcoTrace"))

# Future: real Fabric (drop-in, no service change)
service = LedgerService(backend=FabricLedgerBackend(sdk_client))
```

---

## 17. Deterministic Design

The Blockchain Layer's defining property: **same inputs → byte-identical outputs** (modulo optional timestamps). This is what makes the layer a reproducible, tamper-evident audit trail.

### Sources of Determinism

**Canonical JSON Serialization** — every model's `to_json()` uses:
- `sort_keys=True` — keys in stable alphabetical order
- `ensure_ascii=False` — Unicode preserved
- Fixed separators (`(",", ":")` compact, `(",", ": ")` pretty-printed)

The same record/header/block/chain always serializes to the exact same bytes.

**SHA-256 Hashing** — collision-resistant, preimage-resistant, avalanche-effect hash. Given the same input bytes, SHA-256 always produces the same 64-hex-char digest.

**Immutable Models** — `frozen=True, slots=True` dataclasses. Once constructed, a model cannot be mutated. A record handed to the builder stays identical; a chain handed to verification stays unchanged.

**Pure Functions** — the builder and engines perform no I/O, no network calls, no model inference, no randomness. `LedgerBuilder.create_block(record, previous)` is a pure function of its inputs; `LifecycleEngine.validate(events, rules)` is a pure function of its inputs.

**Ordered Collections** — blocks, events, transitions, warnings are tuples (ordered, immutable), not sets or unordered lists.

### Timestamp Isolation

The only source of non-determinism is the optional `created_at` / `occurred_at` / `timestamp` field. When a service is constructed with a clock, these fields capture the current UTC time; when constructed with `clock=None`, they are omitted entirely.

Critically, **timestamps are excluded from content-addressed hashes**:
- The **passport ID** (M2.3) hashes only identity + action, excluding `created_at`.
- The **chain ID** (M3.1) hashes the genesis block's header + record, but the hash is computed over the canonical JSON which includes the timestamp — however, two genesis blocks with different timestamps produce different chain IDs, which is correct (they are different chains).

Wait — this needs clarification. Let me check the actual chain_id implementation: it hashes the genesis block's `to_json()`, which includes the timestamp if present. So chain identity is **not** stable across different-timestamped builds of the same genesis record. This is a deliberate design choice: the chain's identity is its genesis block, timestamp included. For byte-identical chain IDs, use `clock=None`.

### Determinism Testing

Tests verify byte-identical output:

```python
service = LedgerService(clock=None)
chain_a = service.genesis(passport, integrity, trust)
chain_b = service.genesis(passport, integrity, trust)
assert chain_a.to_json() == chain_b.to_json()  # byte-identical
```

This property is tested explicitly for every builder/engine method that produces a model.

---

## 18. Tamper Detection

The hash chain makes tampering detectable via re-verification. This section describes the tamper-detection mechanism and its guarantees.

### What Tampering Looks Like

| Scenario | Attack | Detection |
|----------|--------|-----------|
| Modify a trust score | Change `LedgerRecord.trust_score` from 0.85 to 0.95 | Block's `record_hash` no longer matches `SHA-256(record.to_json())` |
| Reorder blocks | Swap block 2 and block 3 | Block 3's `previous_hash` no longer matches block 2's header hash |
| Insert a block | Insert a new block between existing blocks | Indices non-sequential; subsequent `previous_hash` values broken |
| Delete a block | Remove block n | Indices non-sequential; block n+1's `previous_hash` no longer matches block n-1 |
| Modify a timestamp | Change a block's `timestamp` | Subsequent blocks' `previous_hash` values no longer match (header hash changed) |
| Replace the genesis block | Substitute a different first block | Chain ID no longer matches (derived from genesis block hash) |

### Verification Guarantees

The `LedgerBuilder.verify_chain()` method provides these guarantees:

1. **Link integrity** — every block's `previous_hash` matches the prior block's header hash (or the genesis sentinel for index 0).
2. **Payload integrity** — every block's `record_hash` matches its record's canonical hash.
3. **Sequential ordering** — block indices are sequential starting from 0, with no gaps.

A chain that passes all three checks is structurally sound; a chain that fails any check is marked `is_valid=False`.

### What Verification Does NOT Detect

The M3.1 ledger is a **local, deterministic data structure**, not a distributed consensus system. Verification detects tampering with the chain **after** it is built, but does not prevent:

- **Selective omission** — an attacker with write access can build a chain that excludes certain devices entirely. The omitted devices leave no trace in the chain.
- **Forged genesis** — an attacker can build a new chain from scratch with fabricated records. The chain is internally consistent (passes verification) but is not anchored to the real passport pipeline.
- **Backend substitution** — an attacker with backend access can replace an entire chain. The service has no cryptographic proof the backend returned the correct chain for a given `chain_id`.

These are **consensus and authentication concerns**, out of scope for M3.1/M3.2. They will be addressed by:
- **Digital signatures** (M3.x future) — each record signed by the issuing authority.
- **Hyperledger Fabric** (Section 24) — distributed consensus, immutable ledger, certificate-based authentication.
- **Trust anchors** (Section 25) — external timestamp authorities, notarization.

---

## 19. Testing Strategy

Every component in the Blockchain Layer is deterministic and fully injectable, enabling exhaustive unit testing. This section describes the layer-wide testing strategy.

### Test Categories

Each component is tested across four categories, mirroring the strategy documented in [04 — Decision Intelligence Architecture]:

**1. Builder/Engine Unit Tests** — test the pure builder/engine directly with hand-built inputs:
- Record extraction (field mapping from upstream reports)
- Block creation (header linking, record hashing, genesis handling)
- Chain creation (verification, empty chain, single-block chain)
- Verification (valid/tampered/reordered/gap/duplicate-index chains)
- Lifecycle validation (valid paths, illegal transitions, non-initial genesis, terminal followed)
- Determinism (same inputs → byte-identical output when `clock=None`)

**2. Loader Tests** — test the strict config/rules loader with valid and malformed files:
- Valid file loads successfully
- Every structural violation raises the correct typed exception with the correct `code` and descriptive `details`:
  - Missing version, empty version
  - Unknown hash algorithm (ledger)
  - Non-hex genesis sentinel (ledger)
  - Missing transitions/initial_events (lifecycle)
  - Unknown event type, duplicate event type, self-transition, duplicate target (lifecycle)
  - No terminal event (lifecycle)

**3. Backend Tests (M3.2)** — test each backend implementation:
- Write-then-read round-trip
- Idempotent overwrite (last write wins)
- Absent chain returns `None`
- `exists()` truth
- `list_ids()` completeness
- Receipt structure (correct `chain_id`, `backend` name, metadata shape)
- Deterministic metadata (monotonic `tx_id`/`nonce`, content-addressed `tx_hash`)

**4. Service Tests** — test the injectable service end-to-end:
- Genesis chain (single-block)
- Append (multi-block)
- Build from records (ordered list)
- Save/load/exists round-trip (via backend)
- Provenance stamping (engine/rules/blockchain versions, timestamps)
- Fixed-clock injection (reproducible assertions)
- No-clock injection (omit `created_at` for byte-identical determinism)
- Lifecycle build/append/can_append predicates

### Boundary Testing

Each component's boundary conditions are tested explicitly:
- **M3.1**: empty chain, single-block chain, genesis handling, tampered block, reordered blocks, non-sequential indices, unsupported hash algorithm
- **M3.2**: write-read-overwrite cycles, absent chain, empty `list_ids()`, deterministic metadata
- **M3.3**: empty lifecycle, single-event lifecycle, illegal transition, non-initial genesis, terminal followed, cyclic path (refurbished → in_use → collected)

### Loader Negative Testing

The strict loaders are tested against every documented failure mode. For example, M3.1's `load_config()` is tested to raise `LedgerConfigError` for: missing version, empty version, unknown hash algorithm, non-hex genesis sentinel. M3.3's `load_rules()` is tested to raise `LifecycleRuleError` for: missing version, empty initial_events, missing transition, unknown event type, duplicate event type, self-transition, duplicate target, no terminal event. Each test asserts both the exception type and the `code`.

### Consistency with Prior Milestones

The testing strategy mirrors the M2.x Decision Intelligence engines documented in [04 — Decision Intelligence Architecture], which established the external-catalogue + strict-loader + injectable-service pattern. Tests for this layer reuse the same fixtures, hand-built model builders, and assertion helpers where applicable.

---

## 20. Performance

The Blockchain Layer is designed for low-latency, in-memory processing with no per-request I/O (except backend persistence).

### Performance Characteristics

**No per-request I/O** — every config/rules file is loaded once at service construction and held immutably. Requests are pure in-memory arithmetic (SHA-256 hashing, event validation, block linking) with no file reads, network calls, or database queries.

**Deterministic arithmetic** — the engines perform bounded, deterministic computation:
- **M3.1**: record extraction (field mapping) + block creation (2 SHA-256 hashes per block: header link + record anchor) + chain verification (recompute all hashes) = O(blocks), linear in chain length
- **M3.3**: lifecycle validation (iterate events, check transitions) = O(events), linear in event count

**SHA-256 Hashing** — the bottleneck is hashing canonical JSON. SHA-256 throughput on commodity CPU is ~500 MB/s single-threaded. A typical block (header + record) serializes to ~500 bytes, so hashing overhead is ~1 microsecond per block. Verification of a 1000-block chain: ~1 millisecond.

**No model inference** — unlike the perception tier (M1.1–M1.6) or the decision layer (M2.1–M2.5), the blockchain layer runs no neural networks, loads no model weights, and requires no GPU. It is pure CPU arithmetic over already-computed upstream reports.

### Latency Profile

Each operation's per-request latency:
- **M3.1 `create_record`**: field extraction (dataclass construction) — sub-microsecond
- **M3.1 `create_block`**: 2 SHA-256 hashes (~1 μs each) + dataclass construction — ~2-3 μs
- **M3.1 `create_chain`**: verification (recompute all hashes) + dataclass construction — ~1 μs per block
- **M3.1 `save`**: backend write (memory dict insert) — sub-microsecond; mock Fabric/Ethereum (monotonic counter increment + dict insert) — sub-microsecond
- **M3.3 `validate`**: iterate events, check transition for each adjacent pair — ~100 ns per event
- **M3.3 `build_record`**: validation + dataclass construction — O(events)

A full genesis→verify→save cycle for a single block: ~10 microseconds. A lifecycle validation of 100 events: ~10 microseconds. The entire layer processes one device's passport + lifecycle in **tens of microseconds** on commodity CPU.

### Memory Profile

- **Slotted dataclasses** — every model uses `slots=True`, eliminating per-instance `__dict__` overhead
- **Immutable configs/rules** — loaded once, shared across all requests (no per-request allocation of policy data)
- **Tuple collections** — blocks, events, transitions are tuples (ordered, immutable), not lists (mutable, overallocated)

A typical chain (10 blocks, 10 records): ~50 KB in memory. A typical lifecycle (20 events): ~5 KB.

### Scalability

Because the services are stateless (after construction) and perform no I/O, they scale horizontally trivially: multiple service instances share the same immutable configs/rules and process requests independently. There is no shared mutable state, no locking, and no coordination overhead. The only scaling bottleneck is the backend, and the protocol-based design (M3.2) makes swapping to a distributed backend (Fabric, Ethereum, IPFS) a drop-in change.

### Startup Cost

The only non-trivial cost is at service construction: each service loads and validates its config/rules file once. For the two shipped files (ledger.yaml, transitions.yaml, both small), total startup validation is negligible (milliseconds). Malformed files fail fast at startup rather than at first request.

---

## 21. Security Considerations

The Blockchain Layer is an internal-only, deterministic ledger with no networking, no consensus, and no authentication (yet). This section describes the current security posture and the explicit boundaries.

### What the Layer Provides

**Tamper evidence** — hash chaining makes any modification to a block or its order detectable via verification. An attacker who mutates a chain leaves forensic evidence (broken hashes).

**Content-addressed identity** — chain IDs are derived from genesis blocks, not assigned by a central authority. Equal genesis blocks yield equal chain IDs, enabling deduplication and idempotency.

**Deterministic reproducibility** — given the same inputs, the builder always produces the same chain (modulo timestamps). This makes the ledger a reproducible audit trail.

**Structured validation** — lifecycle events are validated against an external state machine, catching anomalous histories.

### What the Layer Does NOT Provide

**No authentication** — records are not digitally signed. There is no proof that a record was issued by an authorized entity.

**No authorization** — there is no access control. Any code with access to the service can write any chain.

**No non-repudiation** — an issuer can deny producing a record; there is no cryptographic proof of authorship.

**No consensus** — the ledger is a single-writer, deterministic data structure. There is no Byzantine fault tolerance, no validator set, no Raft/PBFT.

**No network security** — the layer is in-process and in-memory. There is no TLS, no certificate validation, no firewall traversal.

**No persistent storage security** — the default backend is a process-local dict with no encryption at rest, no access logs, no audit trail.

**No selective omission protection** — an attacker with write access can build a chain that excludes certain devices entirely. The omitted devices leave no trace.

**No backend substitution protection** — an attacker with backend access can replace an entire chain. The service has no cryptographic proof the backend returned the correct chain for a given `chain_id`.

### Threat Model

The layer assumes:
- The orchestrating code is trusted (no malicious orchestrator).
- The process environment is trusted (no memory inspection, no debugger attach).
- The backend is honest-but-curious (may read chains but not forge/mutate them).

These assumptions are acceptable for an internal-only prototype but insufficient for a distributed, multi-party production system.

### Future Security Enhancements

Planned for future milestones (see [Section 25 — Future Blockchain Roadmap](#25-future-blockchain-roadmap)):

- **Digital signatures** — each record signed by the issuing authority (PKI, certificate chains).
- **Hyperledger Fabric integration** — distributed consensus, immutable ledger, MSP-based authentication.
- **Trust anchors** — external timestamp authorities, notarization, proof of existence.
- **Encrypted storage** — encryption at rest for sensitive passport data.
- **Audit logging** — tamper-evident logs of every write, read, and verification.

---

## 22. Extension Points

The Blockchain Layer is designed to be extended primarily through **backend substitution** (M3.2) and **external policy updates** (M3.1/M3.3 catalogues), and secondarily through code.

### Backend-Only Extensions (No Domain Change)

The most powerful extension point is the M3.2 backend abstraction. Swapping backends changes the persistence/distribution technology without touching one line of domain logic:

| Extension | Backend | Change |
|-----------|---------|--------|
| Real Hyperledger Fabric | `FabricLedgerBackend` | Implement protocol: map `chain_id` → Fabric key, serialize `Blockchain` → CBOR/JSON for chaincode, invoke SDK |
| Real Ethereum | `EthereumLedgerBackend` | Implement protocol: map `chain_id` → contract storage key, serialize `Blockchain`, submit transaction via web3.py |
| IPFS | `IPFSLedgerBackend` | Implement protocol: serialize `Blockchain` → IPFS, return CID as metadata |
| Relational DB | `SQLLedgerBackend` | Implement protocol: serialize `Blockchain` → JSON column, insert/select by `chain_id` |
| Distributed cache | `RedisLedgerBackend` | Implement protocol: serialize `Blockchain`, set/get by `chain_id` |

### Policy-Only Extensions (No Code Change)

Both M3.1 and M3.3 allow policy tuning via external files:

| Extension | File | Change |
|-----------|------|--------|
| SHA-3 migration | `ledger/data/ledger.yaml` | Set `hash_algorithm: sha3_256` |
| Add lifecycle event type | `lifecycle/models.py` + `transitions.yaml` | Add enum member + declare transitions |
| Permit direct `collected → disposed` | `transitions.yaml` | Add `disposed` to `collected` targets |
| Mark `refurbished` terminal | `transitions.yaml` | Set `refurbished: []` (no second life) |

### Code Extensions (New Vocabulary)

Adding new capabilities requires code changes:

- **New lifecycle event type** — add enum member to `LifecycleEventType`, update loader's validation, declare transitions in rules file
- **New backend metadata** — extend `LedgerReceipt.metadata` schema (dict is open, no schema enforcement)
- **New ledger record fields** — extend `LedgerRecord` dataclass, update builder extraction logic, update serialization
- **Lifecycle actor authorization** — add actor validation to `LifecycleEngine`, check credentials against an ACL

### Injectable Collaborators as Extension Points

Because every collaborator is injectable, custom implementations can be substituted:
- A custom `LedgerBuilder` (e.g., parallel block construction for large chains)
- A custom `LifecycleEngine` (e.g., probabilistic transition prediction for anomaly detection)
- A custom backend (e.g., `MultiBackendLedgerBackend` writing to Fabric + IPFS simultaneously)

---

## 23. Current Limitations

This section documents the current scope boundaries and known limitations of the Blockchain Layer as implemented (M3.1–M3.3, version 1.0.0).

### Scope Boundaries

The layer deliberately excludes concerns owned by other subsystems or deferred to future milestones:

- **No Hyperledger Fabric implementation** — the mock Fabric backend emits Fabric-shaped metadata but implements no SDK, chaincode, channels, or MSP
- **No smart contracts** — the mock Ethereum backend simulates a contract address and gas cost without any real contract or EVM
- **No consensus or proof-of-work** — the ledger is a single-writer, deterministic data structure with no Byzantine fault tolerance
- **No digital signatures, wallets, or certificates** — records are hash-anchored, not cryptographically signed
- **No networking or RPC** — everything is in-process and in-memory
- **No persistence** — the default backend is a process-local dict; chains are lost on exit
- **No GPS tracking, QR scanning, or event streaming** — lifecycle locations are free-text labels only
- **No HTTP surface** — the layer is internal-only; no REST API, no authentication

### Algorithmic Limitations

- **Single hash algorithm per chain** — the hash algorithm is set at config load time and applies to the entire chain. Migrating to a different algorithm mid-chain requires rebuilding the chain from scratch.
- **No parallel verification** — `verify_chain()` is a sequential, single-threaded loop. Large chains (10,000+ blocks) could benefit from parallel hash recomputation.
- **Fixed lifecycle vocabulary** — the lifecycle event types are a closed enum. Adding a new event type requires a code change and a redeploy.
- **No lifecycle branching** — the lifecycle is a linear sequence. A device cannot be in two states simultaneously (e.g., `in_transit` + `assessed`).

### Security Limitations

- **No authentication** — no proof a record was issued by an authorized entity
- **No authorization** — no access control; any code with service access can write any chain
- **No non-repudiation** — an issuer can deny producing a record
- **No selective omission protection** — an attacker can build a chain excluding certain devices
- **No backend substitution protection** — an attacker with backend access can replace a chain

### Determinism Constraints

- **Timestamp non-determinism** — when a real clock is injected (production default), the `created_at` / `occurred_at` / `timestamp` fields make outputs non-byte-identical across runs. Byte-identical output requires `clock=None`. The chain ID is stable only when timestamps are omitted or held fixed.

---

## 24. Hyperledger Integration Strategy

The Blockchain Layer is designed to accept a real Hyperledger Fabric backend with zero changes to the domain layer. This section outlines the integration strategy.

### Integration Approach

The M3.2 backend abstraction makes Fabric integration a **backend-only change**:

1. **Implement `FabricLedgerBackend`** — a class satisfying the `LedgerBackend` protocol, wrapping the Hyperledger Fabric SDK.
2. **Map domain concepts to Fabric primitives**:
   - `chain_id` → Fabric ledger key (composite key or single key in a namespace)
   - `Blockchain` → CBOR or JSON for chaincode storage
   - `LedgerReceipt.metadata` → real Fabric transaction ID, block number, channel
3. **Invoke chaincode** — `write()` submits a transaction to the Fabric network; `read()` queries the ledger.
4. **Inject into service** — pass the Fabric backend to `LedgerService` at construction.

### Fabric Backend Sketch

```python
class FabricLedgerBackend:
    name = "fabric"
    
    def __init__(self, *, gateway: Gateway, contract: Contract):
        self._gateway = gateway  # Fabric SDK gateway
        self._contract = contract  # chaincode contract handle
    
    def write(self, chain_id: str, chain: Blockchain) -> LedgerReceipt:
        payload = chain.to_json()  # or CBOR
        tx = self._contract.submitTransaction("putChain", chain_id, payload)
        return LedgerReceipt(
            chain_id=chain_id,
            backend=self.name,
            metadata={
                "tx_id": tx.transaction_id,
                "channel": self._gateway.channel,
                "block_number": tx.block_number,
                "timestamp": tx.timestamp,
            },
        )
    
    def read(self, chain_id: str) -> Blockchain | None:
        result = self._contract.evaluateTransaction("getChain", chain_id)
        if not result:
            return None
        return Blockchain(**json.loads(result))  # deserialize
    
    def exists(self, chain_id: str) -> bool:
        return self.read(chain_id) is not None
    
    def list_ids(self) -> list[str]:
        result = self._contract.evaluateTransaction("listChainIds")
        return json.loads(result)
```

### Chaincode Sketch

The chaincode (Go or Node.js) implements the four operations:

```go
func (c *ChainContract) PutChain(ctx contractapi.TransactionContextInterface, chainID string, chainJSON string) error {
    return ctx.GetStub().PutState(chainID, []byte(chainJSON))
}

func (c *ChainContract) GetChain(ctx contractapi.TransactionContextInterface, chainID string) (string, error) {
    chainBytes, err := ctx.GetStub().GetState(chainID)
    if err != nil || chainBytes == nil {
        return "", nil
    }
    return string(chainBytes), nil
}

func (c *ChainContract) ListChainIds(ctx contractapi.TransactionContextInterface) ([]string, error) {
    // Paginated range query over all keys, collect chain IDs
}
```

### Deployment Workflow

1. **Package and deploy chaincode** — `peer lifecycle chaincode package`, `install`, `approve`, `commit`
2. **Configure Fabric network** — MSP, orderer, peers, channels
3. **Wire Fabric backend** — inject `FabricLedgerBackend(gateway, contract)` into `LedgerService`
4. **No domain changes** — `LedgerService`, `LedgerBuilder`, models, configs, engines unchanged

### What This Unlocks

- **Distributed consensus** — multiple orderers, crash-fault-tolerant ordering
- **Immutable ledger** — append-only history with cryptographic block linking (Fabric's own hash chain, independent of M3.1's)
- **MSP-based authentication** — X.509 certificates, identity verification
- **Channel isolation** — separate ledgers for different device cohorts or regions
- **Endorsement policies** — require N-of-M endorsements before committing

---

## 25. Future Blockchain Roadmap

This section outlines potential evolution paths for the Blockchain Layer, consistent with the platform's roadmap and the layer's extensible architecture.

### Near-Term Enhancements

**Digital Signatures (M3.4)** — sign every `LedgerRecord` with the issuing authority's private key, embed signature in record, verify on load. Requires PKI infrastructure (certificate authority, key management) and extends `LedgerRecord` with `signature` + `issuer_cert` fields.

**Hyperledger Fabric Integration (M3.5)** — deploy the `FabricLedgerBackend` and chaincode outlined in Section 24. Migrate from in-memory to distributed ledger. Requires Fabric network setup (orderers, peers, MSP, channels).

**Lifecycle Event Anchoring (M3.6)** — emit a ledger block per lifecycle event (not just per passport verdict), chaining the device's full history. The lifecycle service's `append()` calls `ledger.append()` directly. Requires extending the ledger to handle high-frequency writes (device moves through 8 states → 8 blocks per device).

### Mid-Term Enhancements

**Smart Contract Actions (M3.7)** — extend lifecycle events to trigger smart contract logic (e.g., `assessed → REFURBISH` mints a refurbishment token, `recycled → DISPOSE` burns the device NFT). Requires Ethereum or Fabric chaincode integration.

**Trust Anchors (M3.8)** — timestamp each chain with an external trust anchor (RFC 3161 timestamp authority, blockchain notarization service like OpenTimestamps). Embeds proof-of-existence at a specific time. Extends `Blockchain` with `timestamp_proof` field.

**Multi-Backend Replication (M3.9)** — write chains to multiple backends simultaneously (Fabric + IPFS, Fabric + Ethereum). A `MultiBackendLedgerBackend` wraps N backends and returns composite receipts. Increases durability and cross-chain verifiability.

**Encrypted Passports (M3.10)** — encrypt sensitive passport fields (device serial, IMEI, MAC) before anchoring. Only authorized parties hold decryption keys. Requires key management infrastructure and extends `LedgerRecord` to carry ciphertext.

### Long-Term Enhancements

**Zero-Knowledge Proofs (M3.11)** — prove properties of a passport (e.g., "trust score > 0.7") without revealing the full passport. Enables privacy-preserving verification. Requires zk-SNARK/zk-STARK library integration.

**Cross-Chain Bridges (M3.12)** — anchor EcoTrace chains to public blockchains (Ethereum mainnet, Polygon) for global verifiability. A bridge contract holds chain IDs + Merkle roots. Requires gas optimization and bridge security audits.

**Decentralized Identity (M3.13)** — issue verifiable credentials (W3C DID) for devices, operators, facilities. Passport IDs become DIDs; lifecycle events reference DIDs. Enables self-sovereign identity for devices.

**Governance & Upgrades (M3.14)** — on-chain governance for catalogue updates (vote to change trust thresholds, lifecycle transitions). Chaincode upgrades via proposal/vote/execution. Requires DAO-like governance mechanisms.

### Architectural Continuity

Any future evolution will preserve the layer's foundational guarantees:
- **Determinism** — same inputs → same outputs
- **Tamper evidence** — hash chaining for integrity
- **Backend abstraction** — domain independent of persistence technology
- **External policy** — catalogues/rules in versioned files
- **Injectability** — every collaborator substitutable

These principles make the Blockchain Layer a durable foundation: new capabilities are added by swapping backends and extending catalogues, not by compromising the core design.

---

## 26. Design Rationale

This section explains the key architectural decisions that shaped the Blockchain Layer and why alternatives were rejected.

### Why a Local, Deterministic Ledger (Not Distributed Consensus)?

**Decision:** Build a single-writer, in-memory, hash-chained ledger with no consensus, no proof-of-work, and no networking (M3.1).

**Rationale:** The platform is an IEEE YESIST 2026 prototype with a 4-month timeline (see PROJECT.md). Deploying a production Hyperledger Fabric network (orderers, peers, MSP, channels, chaincode) is a 2-3 month effort on its own, leaving insufficient time for the AI pipeline (M1.x, M2.x). The local ledger **proves the architecture**: hash-chaining works, tamper evidence works, the backend abstraction works. Once validated, the distributed ledger is a backend swap (M3.2 → M3.5), not a rewrite.

**Alternative rejected:** "Start with Fabric" — would consume the entire timeline on infrastructure, leaving no time for the AI engines that are the platform's differentiator.

### Why Backend Abstraction (Not Direct Fabric Dependency)?

**Decision:** Depend only on a protocol (`LedgerBackend`), never a concrete backend (M3.2).

**Rationale:** The ledger technology is uncertain. Fabric is the plan, but Ethereum, IPFS, or a hybrid might emerge as requirements clarify (see [01 — System Architecture]). Hard-coding Fabric dependencies into the domain layer (service, builder, models) makes pivoting expensive. The protocol-based design makes the pivot a one-file change (add `FabricLedgerBackend`, inject it). The three mock backends prove the abstraction works across different ledger shapes (monotonic Fabric `tx_id`, content-addressed Ethereum `tx_hash`, minimal Memory `block_count`).

**Alternative rejected:** "Abstract base class" — heavier, requires inheritance, forces boilerplate `super()` calls. Protocols are idiomatic Python and lighter.

### Why External State Machine (Not Hardcoded Transitions)?

**Decision:** Lifecycle transitions live in `transitions.yaml`, not in code (M3.3).

**Rationale:** The legal lifecycle path is **policy, not logic**. It will change as triage workflows are refined, regulations evolve, and new device types (IoT, batteries, solar panels) are added. Hardcoding transitions in an `if`-tree makes every change a code change, a test change, and a redeploy. External YAML makes changes reviewable by domain experts (non-engineers) and hot-swappable (reload the service). The strict loader catches typos at load time (not runtime), so the policy file is as safe as code.

**Alternative rejected:** "Hardcoded state machine" — brittle, requires redeploy for every policy tweak, opaque to non-engineers.

### Why Hash-Chain (Not Merkle Tree)?

**Decision:** Chain blocks via `previous_hash` (linear chain), not via a Merkle tree (M3.1).

**Rationale:** The ledger is **append-only and sequential** by design. A Merkle tree provides efficient proof-of-inclusion for large, sparse datasets (e.g., "prove transaction T is in block B without downloading the whole block"). The EcoTrace ledger is small (hundreds to low thousands of devices per deployment), accessed whole (no sparse queries), and locally verified (no need for compact proofs). A linear chain is simpler, easier to reason about, and sufficient. If sparse proofs become necessary (e.g., mobile clients verifying one device without downloading the whole chain), a Merkle tree can be layered on top (batch blocks into Merkle-tree-rooted epochs).

**Alternative rejected:** "Merkle tree from the start" — overengineering for the current scale, adds complexity with no immediate benefit.

### Why Content-Addressed Chain ID (Not UUID)?

**Decision:** Derive `chain_id` from the genesis block's hash, not from a random UUID (M3.1).

**Rationale:** Content-addressed identity enables **deduplication and idempotency**. Two services that independently build a chain from the same genesis record produce the same `chain_id`, so the backend can detect duplicates. A random UUID would treat them as different chains, leading to storage bloat. The content-addressed design also makes chain IDs **predictable**: given a genesis record, the `chain_id` is deterministic, enabling pre-computation and correlation across systems.

**Alternative rejected:** "Random UUID" — loses deduplication, loses predictability, adds no benefit.

### Why Report Invalid (Not Raise Exception)?

**Decision:** A chain that fails verification is reported as `is_valid=False`, never raised (M3.1). A lifecycle that violates a transition is reported as `is_valid=False`, never raised (M3.3).

**Rationale:** This mirrors the raise-vs-report asymmetry established in the Decision Intelligence Layer (M2.4, M2.5, documented in [04 — Decision Intelligence Architecture]): a malformed **engine** is a bug (raise); a malformed **chain/lifecycle** is a verdict (report). A tampered chain is a **finding** for audit, not a crash. Raising would force every orchestrator to wrap the service in try-catch and handle tampering as an exception (control flow by exception, an anti-pattern). Reporting keeps the flow clean: call the service, inspect `is_valid`, route accordingly.

**Alternative rejected:** "Raise on invalid chain" — conflates "the engine broke" with "the chain is tampered," makes orchestration brittle.

### Why No Smart Contracts Yet?

**Decision:** Defer smart contracts, chaincode, and Solidity to future milestones (M3.1–M3.3 scope boundary).

**Rationale:** Smart contracts add substantial complexity (language choice, gas optimization, security audits, upgrade mechanisms) and require a deployed blockchain network (Fabric or Ethereum). M3.1–M3.3 focus on the **domain model and abstraction**, proving the architecture works. Contracts are a **deployment concern**, not a domain concern. Once the domain is validated (hash-chaining works, lifecycle works, backend abstraction works), contracts are layered on as chaincode (Fabric) or Solidity (Ethereum) — the service stays unchanged.

**Alternative rejected:** "Build contracts first" — would block the domain layer on blockchain deployment, increase timeline risk, and mix concerns (domain logic + contract logic).

---

**End of document. Generated from reverse-engineered implementation source of truth at `intelligence/device_ai/` (packages `ledger/`, `lifecycle/`, plus shared `exceptions.py`, `configs/settings.py`, and `utils/hashing.py`). Every architectural claim in this document is grounded in the implementation as it exists; no functionality has been invented. This document covers the Blockchain Layer (M3.1–M3.3) only; the Decision Intelligence Layer (M2.x) is documented in [04 — Decision Intelligence Architecture], and future milestones (M3.4+, Hyperledger Fabric, smart contracts) are out of scope.**

