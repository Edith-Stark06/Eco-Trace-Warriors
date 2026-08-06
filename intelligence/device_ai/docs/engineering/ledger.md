# Blockchain Ledger Core & Backend Abstraction (M3.1, M3.2)

> The **first two components of milestone M3**. **M3.1** is an internal-only,
> **deterministic immutable-ledger builder** that consumes the three upstream
> artefacts the passport pipeline already produced (the immutable
> **`DevicePassport`** from M2.3, its **`PassportIntegrityReport`** from M2.4 and
> its **`PassportTrustReport`** from M2.5) and emits a tamper-evident
> **`Blockchain`**: an ordered chain of **`Block`** objects, each carrying one
> **`LedgerRecord`** payload and one **`BlockHeader`** that links it to the
> previous block via a deterministic SHA-256 hash. Unlike M2.3 (which
> *assembles* the passport), M2.4 (which *checks* it) and M2.5 (which *scores*
> it), the ledger core carries **no inference and no evidence collection of its
> own**: it snapshots the three reports' key outcomes into a record, hashes it,
> and chains it. Its operational knobs (hash algorithm, versions, genesis
> sentinel) live in an **external, versioned** YAML/JSON file behind a strict
> validating loader; its hashing and block generation are deterministic and its
> serialization is canonical, so the same inputs always yield byte-identical
> output (modulo optional timestamps). It ships **no new endpoint** and leaves
> the `/predict` API contract **unchanged and backward-compatible**.
>
> **M3.2** adds the **ledger backend abstraction layer**: a technology-agnostic
> **`LedgerBackend`** protocol and three deterministic, in-memory implementations
> (**`MemoryLedgerBackend`**, **`MockFabricLedgerBackend`**,
> **`MockEthereumLedgerBackend`**). The **`LedgerService`** persists chains
> through an *injected* backend, depending only on the protocol — so the ledger
> technology can change without touching the domain or service layers. Every
> write returns a **`LedgerReceipt`** carrying the chain id and backend-specific
> metadata. Like M3.1, it implements **no** real Fabric SDK, Ethereum RPC,
> consensus, networking or persistence — the mocks emit technology-flavored
> metadata only, to prove the abstraction.

**Module:** `intelligence/device_ai`
**Milestone:** M3.1 — Blockchain Ledger Core · M3.2 — Ledger Backend Abstraction Layer
**Status:** implemented; internal-only (no router, no HTTP surface)

---

## Table of contents

1. [Scope](#scope)
2. [Architecture](#architecture)
3. [Domain models](#domain-models)
4. [The external ledger config](#the-external-ledger-config)
5. [Config loader](#config-loader)
6. [The deterministic builder](#the-deterministic-builder)
7. [Hash-chaining and tamper evidence](#hash-chaining-and-tamper-evidence)
8. [Chain verification](#chain-verification)
9. [Deterministic serialization](#deterministic-serialization)
10. [The backend abstraction (M3.2)](#the-backend-abstraction-m32)
11. [The `LedgerBackend` protocol](#the-ledgerbackend-protocol)
12. [The `LedgerReceipt`](#the-ledgerreceipt)
13. [The three backends](#the-three-backends)
14. [Chain identity and the service refactor](#chain-identity-and-the-service-refactor)
15. [Configuration](#configuration)
16. [Testing](#testing)
17. [Integration guide](#integration-guide)
18. [Worked examples](#worked-examples)
19. [Backward compatibility](#backward-compatibility)
20. [Design rationale](#design-rationale)

---

## Scope

M3.1 is the **first** component of milestone M3 and the first to build a
**tamper-evident history** over the pipeline's output rather than producing a new
analysis, composition, structural check or trust verdict. The passport core
(M2.3) assembles the upstream reports into an immutable `DevicePassport`; the
integrity engine (M2.4) confirms it is structurally sound and hashes it; the
trust engine (M2.5) grades how much it can be trusted; the ledger core answers
the next question: *"how do we record this passport in an append-only,
independently verifiable audit trail?"* It consumes **three** inputs and reads
only their existing aggregate outcomes — never any raw image or model:

| # | Input | Source (M) | What the builder reads from it |
|---|---|---|---|
| 1 | **Device passport** | M2.3 | `passport_id` (device anchor) + `passport_version` |
| 2 | **Integrity report** | M2.4 | `canonical_hash` (integrity anchor) + `engine_version` |
| 3 | **Trust report** | M2.5 | `trust_score` + `trust_level` + `engine_version` |

Each `LedgerRecord` is a **snapshot** of those key outcomes; the builder hashes
it, and chains the resulting `Block` to its predecessor by embedding the SHA-256
digest of the previous block's header. Any later mutation of a block's contents
or the chain's order breaks the recomputed hashes and is detected on
verification.

**Explicitly in scope**

- Four frozen, slotted domain models — `LedgerRecord`, `BlockHeader`, `Block`,
  `Blockchain` — each with deterministic `to_dict`/`to_json`.
- An **external, versioned** ledger config (YAML/JSON) with a strict loader that
  validates aggressively and fails with a typed error.
- A pure `LedgerBuilder` (create record → create block → create/append chain →
  verify chain) with deterministic SHA-256 hashing and previous-hash linking.
- An injected `LedgerService` orchestration façade.
- **(M3.2)** A technology-agnostic `LedgerBackend` **protocol**, a frozen
  `LedgerReceipt`, three deterministic in-memory backends (`MemoryLedgerBackend`,
  `MockFabricLedgerBackend`, `MockEthereumLedgerBackend`), and the service
  refactor that persists chains through the *injected* backend by a
  content-addressed `chain_id`.

**Explicitly out of scope** (do **not** implement in M3.1/M3.2): **Hyperledger
Fabric**, **Ethereum**, **consensus**, **proof-of-work**, **smart contracts**,
**chaincode**, **wallets**, **certificates**, **digital signatures**, **REST
endpoints**, **networking** and **persistence**. The core is a **local,
in-memory data structure**, not a distributed ledger — it provides
tamper-evident, independently verifiable history via hash-chaining behind a
**pluggable backend abstraction**, and nothing more. The two M3.2 mocks emit
Fabric-/Ethereum-*shaped* metadata but hold no SDK, RPC, chaincode or wire
concern whatsoever — they exist purely to prove the abstraction. The core is
**internal only** — no router is mounted, `application.py` is untouched, and the
`/predict` response schema is **unchanged**. The future *real* Hyperledger Fabric
backend described in `docs/engineering/09_BLOCKCHAIN.md` is a **separate**
concern and is not built here.

**Key asymmetry.** A malformed **config** *raises* (a `LedgerConfigError` at load
time — it is an engine fault), and an unsupported hash algorithm *raises* (a
`LedgerError` — also an engine fault). Tampering with the *data* — a mutated
block or a re-ordered chain — is never raised; it is *reported* as
`is_valid == False` on the produced chain (and by `verify()` returning `False`),
because detecting that tampering is exactly the job the core was asked to do.
This mirrors the M2.4/M2.5 checker asymmetry: only the engine's own policy file
(or an engine fault) can crash the core.

## Architecture

The core is a **pure domain layer** with the same shape as `trust/`,
`integrity/`, `circular/` and `passport/`: frozen slotted dataclasses, a
stateless builder, and an injected service. It imports its three input types
**only under `TYPE_CHECKING`**, so there is no heavyweight runtime coupling and
no import cycle — the three reports are passed in, never reached into past their
public surface.

```
   passport core (M2.3) ─► DevicePassport ───────────────┐
   integrity engine (M2.4) ─► PassportIntegrityReport ───┤
   trust engine (M2.5) ─► PassportTrustReport ───────────┤
                                                         │
   ┌──────────────── ledger/ (internal) ──────────────────▼──────────┐
   │  service.py   LedgerService.genesis / append /                  │
   │        │            build_chain / verify                        │
   │        ▼             ▼              ▼                            │
   │  config.py       builder.py    (utils/hashing.py)               │
   │  load_config     LedgerBuilder  hash_bytes(sha256)              │
   │  LedgerConfig    (create_record → create_block →                │
   │  (external        create_chain / append_block /                 │
   │   YAML/JSON,       verify_chain)                                 │
   │   validated)         │                                          │
   │   models.py  Blockchain (frozen) · Block · BlockHeader ·        │
   │              LedgerRecord                                       │
   │   backend.py LedgerBackend (Protocol) · LedgerReceipt ·         │
   │              Memory / MockFabric / MockEthereum backends (M3.2) │
   └───────────────────────────────────────────────────────────────────┘
                                ▼
       injected LedgerBackend (memory / mock Fabric / mock Ethereum;
       future real anchor) — never /predict
```

Layering (dependencies point downward, never upward):

```
passport/ · integrity/ · trust/   (produce the three inputs)
   ↓  (TYPE_CHECKING only; the three reports are passed in)
ledger/  (models.py + config.py + builder.py + backend.py + service.py)
   ↓
utils/hashing · exceptions · configs   (cross-cutting foundations)
```

The package contains **no HTTP imports, no FastAPI, and its only I/O is reading
the config file once at service construction.** After that, every builder method
is a pure function of its inputs except for the injected clock (which defaults to
UTC `now` and can be replaced or disabled for determinism).

## Domain models

`ledger/models.py` defines the vocabulary of the ledger. Each is a small, frozen,
slotted dataclass with its own `to_dict()`/`to_json()` so the chain serializes
deterministically.

### `LedgerRecord`

The **payload** a `Block` carries — a snapshot of the three upstream reports'
key outcomes:

| Field | Meaning |
|---|---|
| `passport_id` | The id of the device passport this record anchors. |
| `integrity_hash` | The canonical SHA-256 hex digest from the integrity report. |
| `trust_score` | The normalized `[0, 1]` trust score from the trust report. |
| `trust_level` | The trust level wire value (`high`/`medium`/`low`/`untrusted`). |
| `passport_version` | The passport's structural version, echoed for the consumer. |
| `integrity_engine_version` | Version of the integrity engine that validated the passport. |
| `trust_engine_version` | Version of the trust engine that assessed it. |
| `created_at` | UTC timestamp (or `None` when built without a clock). |

### `BlockHeader`

The deterministic metadata of one block — what links blocks together:

| Field | Meaning |
|---|---|
| `index` | The zero-based position of this block (genesis is `0`). |
| `timestamp` | UTC timestamp (or `None` when built without a clock). |
| `previous_hash` | SHA-256 hex digest of the previous block's header, or the genesis sentinel (`"0" * 64`) for the genesis block. |
| `record_hash` | SHA-256 hex digest of this block's ledger record. |

### `Block`

One immutable block: its `header` and its single `record`. Convenience
properties `index`, `previous_hash` and `record_hash` delegate to the header, so
callers read the chain link without reaching into the header.

### `Blockchain`

The final artefact the service produces — the immutable, ordered chain:

| Field | Meaning |
|---|---|
| `blocks` | The ordered blocks, from genesis (index `0`) to the most recent. |
| `version` | Semantic version of the blockchain structure. |
| `is_valid` | Whether the chain passed structural validation at build time. |
| `block_count` | Number of blocks in the chain. |
| `created_at` | UTC timestamp (or `None` when built without a clock). |

Every object's `to_dict()` renders a fully JSON-serializable payload in a
**fixed** key order; `to_json()` renders a **canonical** serialization (see
[Deterministic serialization](#deterministic-serialization)).

## The external ledger config

The builder's operational knobs live **outside the code** in
`ledger/data/ledger.yaml` — a versioned file that is **policy, not logic**, so
*which hash algorithm anchors blocks, which version tag brands the chain, and the
genesis sentinel* can be reviewed, tuned or corrected without touching or
redeploying the builder.

Top-level keys:

| Key | Meaning |
|---|---|
| `version` | Semantic version string of the config document (required, non-empty). |
| `hash_algorithm` | Hash algorithm for block/record anchors; must be recognized by Python's `hashlib`. Defaults to `sha256`. |
| `blockchain_version` | Semantic version stamped onto every produced `Blockchain`. Defaults to `1.0.0`. |
| `genesis_previous_hash` | The `previous_hash` sentinel for the genesis block; must be a hex string. Defaults to 64 zero characters. |

The shipped config uses `hash_algorithm: sha256`, `blockchain_version: 1.0.0`
and a 64-zero `genesis_previous_hash`. It holds **no chaining logic** — only the
knobs.

## Config loader

`ledger/config.py` turns the config file into a validated, immutable
`LedgerConfig` value object. `load_config(path)` reads YAML (or JSON, by suffix),
then **validates aggressively**, raising a typed `LedgerConfigError` on any
structural problem:

- file missing / unparseable / not a mapping / empty;
- missing or empty `version`;
- an empty or non-string `hash_algorithm`, or one not in
  `hashlib.algorithms_available`;
- an empty or non-string `blockchain_version`;
- a `genesis_previous_hash` that is not a valid hex string.

`LedgerConfig.resolved_config_path(package_root=…)` resolves a relative
`config_path` against the `device_ai` package root, so the packaged config is
found regardless of the process working directory.
`LedgerConfig.from_settings(settings)` returns the default config (M3.1 has no
env-driven knobs — its policy lives in the external file) and exists to mirror
the trust/integrity/passport pattern and provide a hook for future env-driven
configuration.

## The deterministic builder

`ledger/builder.py` holds the deterministic construction. There is **no model and
no new inference** — given the same three reports and config it always produces
the same chain (modulo the optional timestamp). Its API:

| Method | What it does |
|---|---|
| `create_record(passport, integrity, trust, *, created_at=None)` | Snapshots the three reports' key outcomes into an immutable `LedgerRecord`. |
| `create_block(record, previous_block=None, *, timestamp=None)` | Builds a `Block`: index `0` + genesis sentinel when `previous_block` is `None`, else `previous.index + 1` + the previous header's hash; the header also carries this record's hash. |
| `create_chain(blocks, *, created_at=None)` | Verifies the ordered blocks and wraps them in an immutable `Blockchain` with its validation status and block count. |
| `append_block(chain, record, *, timestamp=None, created_at=None)` | Builds a block chaining to the last block of `chain` and returns a fresh, re-verified `Blockchain`. |
| `verify_chain(blocks)` | Recomputes every link and payload hash and checks ordering (see [Chain verification](#chain-verification)). |

Private helpers isolate the hashing: `_hash(canonical_json)` is the **single
point** that maps an unsupported algorithm onto a typed `LedgerError`;
`_compute_previous_hash(previous_block)` returns the genesis sentinel or the
prior header's hash; `_hash_record(record)` hashes the record's canonical JSON.

## Hash-chaining and tamper evidence

Each block is linked to its predecessor by embedding the SHA-256 digest of the
predecessor's **header** (its canonical JSON) in this block's `previous_hash`,
and each block anchors its own payload by embedding the SHA-256 digest of its
**record** (its canonical JSON) in `record_hash`:

```
previous_hash(blockₙ) = SHA-256( canonical_json( blockₙ₋₁.header ) )     # n ≥ 1
previous_hash(block₀) = genesis_previous_hash                            # sentinel
record_hash(blockₙ)   = SHA-256( canonical_json( blockₙ.record ) )
```

Because the header includes the record hash **and** the previous header's hash,
the digests form a chain: mutating any record changes its `record_hash`, which
changes that block's header, which changes the `previous_hash` every subsequent
block expects — so a single mutation cascades and is detectable anywhere
downstream. This is exactly the tamper-evidence property a blockchain provides,
achieved locally with hashing alone — no consensus, proof-of-work or networking.

## Chain verification

`verify_chain(blocks)` recomputes the chain from scratch and returns whether it
passes **every** check (an empty chain is trivially valid):

1. **Sequential indices** — block `i` must have index `i`, starting from `0`.
2. **Previous-hash linking** — block `0`'s `previous_hash` must equal the genesis
   sentinel; every later block's `previous_hash` must equal the recomputed hash
   of the prior block's header.
3. **Record-hash matching** — every block's `record_hash` must equal the
   recomputed hash of its own record.

Any failure returns `False` — detecting a mutated record, a broken previous-hash
link, a wrong index or a re-ordered chain. `create_chain`/`append_block` call
this at build time and store the result in `Blockchain.is_valid`; the service's
`verify(chain)` re-runs it on demand.

## Deterministic serialization

Every model's `to_json()` renders a **canonical** JSON serialization: keys are
sorted (`sort_keys=True`), non-ASCII is preserved (`ensure_ascii=False`) and
separators are fixed, so the same object always serializes to the exact same
bytes — which is precisely what makes the hashes reproducible. Because each
`to_dict()` is a pure function of the inputs, the **only** source of variation is
the optional timestamp. Passing `indent=` pretty-prints while staying canonical;
the default emits the most compact canonical form. Building the same records
twice with `clock=None` yields two byte-identical chains.

## The backend abstraction (M3.2)

M3.1 produces a `Blockchain` as an in-memory value; it never says **where a chain
lives** or **how it is written**. M3.2 answers that without committing to a
technology. Following `CLAUDE.md` ("dependency injection where appropriate";
"persistence abstraction; do not tightly couple to storage") and mirroring the
`FingerprintRepository` abstraction already in the codebase, it introduces a
**technology-agnostic persistence contract** — the `LedgerBackend` protocol — and
makes the `LedgerService` depend on that protocol alone. The concrete store
(in-memory dict, a mock Fabric channel, a mock Ethereum contract, or a future
*real* anchor) is **constructor-injected**, so the ledger technology can change
without editing the service or any domain model.

```
   LedgerService.save(chain) / load / exists / list_ids
        │  depends only on the protocol ↓
   ┌────────────── LedgerBackend (Protocol, @runtime_checkable) ──────────────┐
   │   write(chain_id, chain) → LedgerReceipt · read · exists · list_ids       │
   └───────────▲───────────────────▲───────────────────────▲──────────────────┘
               │                   │                        │
    MemoryLedgerBackend   MockFabricLedgerBackend   MockEthereumLedgerBackend
    (dict; block_count)   (tx_id, channel,          (tx_hash, nonce, gas_used,
                           block_number)             contract)
```

The design keeps a strict **separation of concerns**: the *service* owns chain
**identity** (it derives a stable `chain_id` from the chain's genesis block and
passes it in), so every backend is a pure, technology-flavored **key-value
store** and never re-implements identity logic. This is the single most important
boundary in M3.2 — it is why all three backends share one test contract and why a
fourth (real) backend could be added by implementing four methods and nothing
else.

## The `LedgerBackend` protocol

`ledger/backend.py` defines `LedgerBackend` as a `typing.Protocol` decorated
`@runtime_checkable`, so conformance is **structural** (duck-typed) — a class is a
`LedgerBackend` if it has the four methods, with no explicit base class or
registration, and `isinstance(obj, LedgerBackend)` confirms it at runtime. The
contract is four methods:

| Method | Contract |
|---|---|
| `write(chain_id, chain) → LedgerReceipt` | Persist `chain` under `chain_id`, replacing any existing chain (last-write-wins). Returns a `LedgerReceipt` carrying the id and backend metadata. |
| `read(chain_id) → Blockchain \| None` | Return the stored chain, or **`None`** when the id is unknown — implementations must be safe to call with unknown ids and never raise for a miss. |
| `exists(chain_id) → bool` | Whether a chain is stored under `chain_id`. |
| `list_ids() → list[str]` | Every stored chain id (order is not guaranteed). |

The protocol is deliberately minimal — write, read, existence, enumeration —
matching what the service needs and nothing a real ledger could not also provide.
It says nothing about durability, transactions or networking, leaving each
implementation free to be a dict, a channel simulation or (later) a real anchor.

## The `LedgerReceipt`

Every `write` returns a `LedgerReceipt` — a frozen, slotted value object so a
caller can **correlate a chain with the backend's write** without reaching into
the backend:

| Field | Meaning |
|---|---|
| `chain_id` | The service-assigned id the chain was stored under. |
| `backend` | The backend identifier that produced the receipt (`memory` / `mock_fabric` / `mock_ethereum`). |
| `metadata` | Backend-specific write details (a Fabric transaction id and channel, an Ethereum transaction hash and gas, …); an empty mapping when a backend records none. |

`to_dict()` renders a JSON-serializable view (`chain_id`, `backend`, a copy of
`metadata`). The receipt is the abstraction's *seam*: callers read a uniform
shape, while each backend fills `metadata` with whatever its technology would
naturally emit.

## The three backends

All three ship in M3.2, are **deterministic** and **in-memory**, and hold chains
in a process-local dict for the instance's lifetime. They differ **only** in the
metadata each records — the service drives all three identically. None contains
any real SDK, RPC, chaincode, smart contract, wallet, certificate, digital
signature, consensus, networking or persistence.

### `MemoryLedgerBackend` — `name = "memory"`

The default backend (the service constructs one when none is injected) and the
one used throughout the test suite. It records only `{"block_count": …}` as
metadata — it emulates no particular ledger technology. Chains are lost when the
process exits.

### `MockFabricLedgerBackend` — `name = "mock_fabric"`

A stand-in for a Hyperledger Fabric channel. Its receipt metadata is
Fabric-*shaped*: a **monotonic transaction id** (`fabric-tx-00000001`, …), the
**channel name** (`ecotrace-ledger` by default, exposed via the `channel`
property and injectable) and a **block number** that advances with each write —
mirroring an append-only channel, deterministic given the write order. It holds
**no** Fabric SDK, chaincode, certificates, MSP, orderer or gossip — only the
metadata shape.

### `MockEthereumLedgerBackend` — `name = "mock_ethereum"`

A stand-in for an Ethereum smart contract. Its receipt metadata is
Ethereum-*shaped*: a **content-addressed transaction hash** —
`"0x" + SHA-256(chain.to_json())`, so it is deterministic and unique per chain
*state* (writing an unchanged chain twice yields the same hash; appending a block
changes it) — a **monotonic nonce/block number**, the simulated **gas used**
(`21000` by default, injectable via `gas_per_write`) and the **contract address**
(`0xEcoTraceLedger` by default, exposed via the `contract` property and
injectable). It holds **no** Ethereum RPC, EVM, smart contract, wallet, private
key or digital signature — only the metadata shape.

> **Why deterministic mocks (no `sleep`/`random`)?** A real ledger's latency and
> transaction ids are non-deterministic, but modelling that here would make the
> shared test contract slow and flaky for **zero** design value — the abstraction
> is what M3.2 proves, not wire behaviour. Monotonic counters and a
> content-addressed hash give realistic-*shaped* metadata that is exactly
> reproducible, so the contract tests are fast and stable. When a *real* backend
> lands, its non-determinism lives behind the same protocol and the same receipt
> shape.

## Chain identity and the service refactor

The `LedgerService` gains a persistence surface (M3.2) built entirely on the
protocol. Identity is derived **once, in one place**: the builder's
content-addressed `chain_id(chain)` hashes the chain's **genesis block** — a
stable anchor that identifies a chain by its origin (it does not change as blocks
are appended, because the genesis block is immutable) and that goes through the
same single `_hash` helper that maps an unsupported algorithm onto a typed
`LedgerError`. The service exposes it and the four persistence methods:

| Method | What it does |
|---|---|
| `chain_id(chain) → str` | Delegates to the builder's content-addressed id (the genesis-block hash) — the key the backend stores under. Raises `LedgerError` on an empty chain. |
| `save(chain) → LedgerReceipt` | Derives the id and calls the injected backend's `write(chain_id, chain)`, returning its receipt. |
| `load(chain_id) → Blockchain \| None` | Delegates to the backend's `read`. |
| `exists(chain_id) → bool` | Delegates to the backend's `exists`. |
| `list_ids() → list[str]` | Delegates to the backend's `list_ids`. |

The backend is injected exactly like the config, builder and clock before it:
`LedgerService(*, config=None, builder=None, backend=None, clock=_utc_now)`,
defaulting to a `MemoryLedgerBackend()` and exposed read-only via the `backend`
property. Because the service references only the `LedgerBackend` protocol, the
same `save`/`load`/`exists`/`list_ids` calls work byte-for-byte identically
across the memory, mock-Fabric and mock-Ethereum backends — the **only**
observable difference is the metadata on the returned receipt. The M3.1 methods
(`create_record`, `genesis`, `append`, `append_record`, `build_chain`, `verify`)
are **unchanged**.

## Configuration

`LedgerConfig` (frozen slotted) holds the four operational knobs; everything that
shapes the ledger's policy lives in the external file:

| Field | Default | Meaning |
|---|---|---|
| `hash_algorithm` | `sha256` | Hash algorithm for block/record anchors; must be a `hashlib` name. |
| `blockchain_version` | `1.0.0` | Semantic version stamped onto every produced chain. |
| `genesis_previous_hash` | `"0" * 64` | The genesis block's `previous_hash` sentinel. |
| `config_path` | `ledger/data/ledger.yaml` | Config locator, resolved against the package root when relative. |

M3.1 adds **no** environment variables — the ledger's policy lives entirely in
the external YAML file, and `from_settings()` returns the default config. The
typed exceptions added for this core are `LedgerError` (`LEDGER_ERROR`, 500 — an
unsupported hash algorithm) and its loader subclass `LedgerConfigError`
(`LEDGER_CONFIG_ERROR`, 422 — a malformed config file).

## Testing

Five test modules under `tests/`, all offline (no images, no models; only the
external config is read from disk):

- **`test_ledger_models.py`** (**16** tests) — the four frozen value objects:
  fixed `to_dict` key order and values, `created_at`/`timestamp` `None`
  serialization, canonical sorted-compact `to_json`, the `Block` convenience
  properties delegating to the header, the nested `Block`/`Blockchain`
  serialization, immutability, and the **no networking/consensus/monetary
  surface** invariant.
- **`test_ledger_config.py`** (**14** tests) — the shipped config loads and
  validates, defaults match the module constants, relative/absolute path
  resolution, custom YAML/JSON loading with default fallback, and the loader's
  validation on hand-written good/bad files in `tmp_path` (missing file, empty,
  non-mapping root, missing version, unsupported/empty hash algorithm, non-hex
  genesis), plus the `from_settings` mapping.
- **`test_ledger_builder.py`** (**16** tests) — record/block/chain creation
  against hand-built reports, the genesis sentinel, previous-hash linking (the
  computed hash of the prior header), deterministic record hashing, distinct
  records hashing differently, empty/single/three-block chain validation, tamper
  detection (wrong index, mutated record, broken previous link), the
  unsupported-algorithm engine fault, a `sha3_256` alternate, and determinism
  (byte-identical chains, canonical JSON).
- **`test_ledger_service.py`** (**14** tests) — end-to-end against the **shipped**
  config, with the three inputs built by actually running the recoverability,
  component, material, environmental, decision-knowledge, circular, passport,
  integrity and trust engines over a hand-built `DeviceContext` plus a real
  `DeviceFingerprint`: record creation from real artefacts, `genesis`/`append`/
  `append_record`/`build_chain`, intact-chain verification and tamper detection,
  determinism across service instances, the injected clock, the default config
  load, the **no networking/consensus/monetary surface** invariant and
  immutability.
- **`test_ledger_backend.py`** (**29** tests, M3.2) — the **shared backend
  contract**. A parametrized `backend` fixture yields each of the three
  implementations in turn, and one body of contract tests runs against **all** of
  them: `@runtime_checkable` protocol satisfaction (`isinstance`), write/read
  round-trip, `read` returning `None` for an unknown id, `exists`, `list_ids`,
  overwrite (last-write-wins), and the receipt's `chain_id`/`backend`. Alongside
  the shared contract, per-backend tests assert each implementation's metadata
  specifics (memory `block_count`; Fabric `tx_id`/`channel`/`block_number` and the
  monotonic transaction counter; Ethereum `tx_hash`/`nonce`/`gas_used`/`contract`,
  the advancing nonce and the **deterministic** content-addressed `tx_hash`), and
  the service-level `save`/`load`/`exists`/`list_ids` driving an injected backend.
  Inputs are built **offline** by a `_sample_artifacts` helper that hand-crafts a
  `DevicePassport`/`PassportIntegrityReport`/`PassportTrustReport` (no upstream
  engines), so the contract runs fast and never flakes.

The five modules add **89** tests (60 from M3.1 + 29 from M3.2), all passing; the
module is `ruff`-, `black`- and `isort`-clean and adds **zero** `mypy` errors.
The shared contract is the mechanism that keeps every backend — and any future
one — honest against a single specification.

## Integration guide

The core is consumed **directly** (no HTTP). Orchestrating code assembles the
passport (M2.3), validates it (M2.4), scores it (M2.5), and hands the three
artefacts to the `LedgerService`:

```python
from device_ai.passport import PassportService
from device_ai.integrity import IntegrityService
from device_ai.trust import TrustService
from device_ai.ledger import LedgerService

# 1. Compose, validate and score the passport (M2.3 + M2.4 + M2.5).
passport = PassportService().build(context, decision, materials, environmental, fingerprint)
integrity = IntegrityService().validate(passport)
trust = TrustService().assess(passport, integrity, knowledge, decision)

# 2. Record it on the ledger (M3.1). Every collaborator is injected, so the
#    service is constructible as-is or with a fixed clock / custom config /
#    pre-loaded builder. The external config is loaded once at construction.
ledger = LedgerService()
chain = ledger.genesis(passport, integrity, trust)          # first device
chain = ledger.append(chain, passport2, integrity2, trust2) # subsequent devices

assert chain.is_valid
assert ledger.verify(chain)                                 # re-verify on demand

payload = chain.to_dict()                                    # JSON-serializable ledger
canonical = chain.to_json()                                  # deterministic bytes
```

For the **lower-level** API, `create_record(...)` builds a `LedgerRecord` a caller
can hold (e.g. to control its timestamp) and `append_record(chain, record)` /
`build_chain(records)` chain pre-built records. For **deterministic** use (tests,
reproducible pipelines) construct the service with `clock=None` (drops the
timestamp, making the chain a pure function of its inputs) and/or inject a
hand-built `LedgerConfig` or a custom `LedgerBuilder`.

### Persisting through a backend (M3.2)

Once a chain exists, persistence is four protocol-level calls — identical across
every backend. The backend is injected at construction and defaults to
`MemoryLedgerBackend`; swap it for either mock (or a future real anchor) without
touching the calls:

```python
from device_ai.ledger import (
    LedgerService,
    MemoryLedgerBackend,
    MockFabricLedgerBackend,
    MockEthereumLedgerBackend,
)

# Default (in-memory) backend — nothing to wire.
ledger = LedgerService()

# …or inject a specific backend; the service depends only on the protocol.
ledger = LedgerService(backend=MockFabricLedgerBackend())     # or MockEthereumLedgerBackend()

chain = ledger.genesis(passport, integrity, trust)
receipt = ledger.save(chain)                    # → LedgerReceipt(chain_id, backend, metadata)
assert ledger.exists(receipt.chain_id)
assert ledger.load(receipt.chain_id) == chain
assert ledger.list_ids() == [receipt.chain_id]

# The receipt carries backend-flavored metadata:
#   memory        → {"block_count": 1}
#   mock_fabric   → {"tx_id": "fabric-tx-00000001", "channel": "ecotrace-ledger", ...}
#   mock_ethereum → {"tx_hash": "0x…", "nonce": 1, "gas_used": 21000, "contract": "0xEcoTraceLedger", ...}
```

Because the service holds only a `LedgerBackend`, the **only** line that ever
changes when the ledger technology changes is the `backend=` argument at
construction — the `save`/`load`/`exists`/`list_ids` surface is invariant.

## Worked examples

### A genesis chain — one device

`ledger.genesis(passport, integrity, trust)` snapshots the three reports into a
`LedgerRecord`, wraps it in a genesis `Block` (index `0`, `previous_hash` = the
sentinel, `record_hash` = the record's SHA-256), and returns a single-block
`Blockchain` with `block_count == 1` and `is_valid == True`.

### Appending a second device — the chain links

`ledger.append(chain, passport2, integrity2, trust2)` builds a second block whose
`previous_hash` is the SHA-256 of the genesis block's header (no longer the
sentinel) and whose index is `1`. The returned chain has `block_count == 2` and
re-verifies clean, because each block's recomputed hashes match.

### A tampered record — detected, not raised

If a consumer mutates a block's `record` (say, to raise a `trust_score`) after
the chain was built, the record's canonical JSON no longer hashes to the stored
`record_hash`. `verify_chain` recomputes the hash, finds the mismatch and returns
`False`; a freshly built `Blockchain` over the tampered blocks carries
`is_valid == False`. The core does **not** raise — reporting the broken chain is
the tamper-evidence guarantee it exists to provide.

### One chain, three backends — same drive, different receipts (M3.2)

Persisting the *same* genesis chain through each backend shows the abstraction:
`save` runs identically, and only the receipt's `metadata` differs. `list_ids`
returns the same single content-addressed id in every case, because identity is
the *service's* job, not the backend's:

```python
chain = LedgerService(clock=None).genesis(passport, integrity, trust)

for backend in (MemoryLedgerBackend(), MockFabricLedgerBackend(), MockEthereumLedgerBackend()):
    svc = LedgerService(clock=None, backend=backend)
    receipt = svc.save(chain)
    # receipt.chain_id is identical across all three (derived from the genesis block);
    # receipt.backend and receipt.metadata differ per technology.
```

Writing the *same* chain twice through `MockEthereumLedgerBackend` yields the
**same** `tx_hash` (it is the SHA-256 of the chain's canonical JSON), while the
nonce still advances — the deterministic, content-addressed property that makes
the mock's metadata reproducible in tests.

## Backward compatibility

M3.1 and M3.2 are **purely additive** and **internal-only**:

- **No endpoint, no router, no schema change.** `application.py` and the
  `/predict` request/response contract are untouched; the only new symbols are the
  `ledger/` package (now including `backend.py`) and two typed exceptions.
- **No change to any upstream engine.** The core consumes the existing public
  surface of the M2.3 passport and the M2.4/M2.5 reports and adds nothing to them.
- **No new environment variables.** The ledger's policy is data in
  `ledger/data/ledger.yaml`, versioned independently of the code.
- **(M3.2) No breaking change to the M3.1 service.** The `backend=` parameter is
  keyword-only with a `MemoryLedgerBackend` default, so every existing
  construction and every M3.1 method (`genesis`/`append`/`build_chain`/`verify`/…)
  behaves exactly as before; the persistence surface (`chain_id`/`save`/`load`/
  `exists`/`list_ids`) is *new* API, not a change to old API. All 60 M3.1 tests
  pass unchanged.

## Design rationale

- **A recorder, not a distributed ledger.** The core's job is to make the
  pipeline's output tamper-evident and independently verifiable. Achieving that
  with **local hash-chaining** — no consensus, proof-of-work, networking or
  persistence — keeps M3.1 small, deterministic and fully unit-testable, and
  leaves the heavyweight Hyperledger Fabric backend (`09_BLOCKCHAIN.md`) as a
  separate, later concern that can anchor these hashes.
- **Report tampering, raise engine faults.** A mutated block or re-ordered chain
  is the core's *input* to judge, so it is reported as `is_valid == False` — never
  a crash. Only a malformed *config* or an unsupported hash algorithm (engine
  faults) raise. This asymmetry mirrors the M2.4/M2.5 checkers.
- **Determinism is the point.** Canonical serialization and pure hashing mean the
  same inputs always yield byte-identical blocks — which is what lets any party
  independently recompute and verify the chain, and what makes the tests exact.
- **Policy is data, not logic.** The hash algorithm, versions and genesis
  sentinel are operational knobs that get tuned; keeping them in an external,
  versioned, strictly-validated file lets the policy evolve independently and fail
  loudly on a malformed file.
- **Deterministic and injectable.** Like every engine before it, the builder is a
  pure function and every collaborator is constructor-injected with a sensible
  default, so production wires nothing while tests inject a config, clock or
  builder at will.
- **Depend on a protocol, not a store (M3.2).** The service references only the
  `LedgerBackend` protocol, so the ledger *technology* is a swappable
  implementation detail — the domain and service never learn whether a chain
  lives in a dict, a Fabric channel or an Ethereum contract. A future *real*
  backend is four methods behind the same seam, and the shared test contract
  already specifies its behaviour.
- **The service owns identity; backends are pure stores (M3.2).** Deriving
  `chain_id` once, in the service (via the builder's content-addressed genesis
  hash), keeps every backend a trivial key-value store with no duplicated logic —
  which is exactly why one test contract can bind all three (and any future)
  implementations, and why last-write-wins semantics are uniform.
- **Realistic-shaped, deterministic mocks (M3.2).** The Fabric/Ethereum mocks emit
  technology-flavored metadata (transaction ids, block numbers, a
  content-addressed tx hash, gas, nonce) but use monotonic counters and pure
  hashing instead of `sleep`/`random`, so they *look* like their target without
  making the test contract slow or flaky — the abstraction is what M3.2 proves,
  not wire behaviour.
