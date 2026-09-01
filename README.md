# ♻️ EcoTrace India

> **AI-Powered, Blockchain-Ready E-Waste Lifecycle Management Platform**

[![IEEE YESIST 2026](https://img.shields.io/badge/IEEE-YESIST%202026-blue)](#)
[![Status](https://img.shields.io/badge/Status-Pilot%20Validated-success)](#)
[![License](https://img.shields.io/badge/License-MIT-green)](#)

---

## 🌍 Overview

EcoTrace India is an e-waste lifecycle management platform: a real Node
backend, a real trained AI device-detection service, a real (chaincode +
Gateway-client) Hyperledger Fabric integration, two React Native (Expo)
mobile apps, and a React operator dashboard, connecting Consumers, Collectors,
Recyclers, and Government/Admin oversight around one transparent
submission-to-recycling workflow.

Developed for **IEEE YESIST 2026**.

**New here? Start with [`QUICKSTART.md`](QUICKSTART.md)** — running demo
in under 10 minutes.

---

## ✅ Project Status

This repository has gone through 8 structured engineering phases (P1–P8),
each producing a real, evidence-backed report under [`reports/`](reports/)
— every claimed result in this README is backed by one of those reports,
not asserted on its own.

| | |
|---|---|
| Regression suite | 1,500+ passing tests across backend (Jest), chaincode (Jest), the AI service (pytest), and both mobile apps (Jest + React Native Testing Library) — see `reports/P8_7_SECURITY_AUDIT.md` §12 and `reports/P9_3_MOBILE_REACT_NATIVE.md` for the current breakdown |
| Live-verified | Full Docker Compose stack, real Postgres migrations, real AI inference, real chaincode tests, real E2E stakeholder scenarios, and (P9.2) a real local Hyperledger Fabric network with real transactions — `reports/P8_1_REAL_DEPLOYMENT.md`, `reports/P8_5_COMPLETE_E2E.md`, `reports/P9_2_LIVE_FABRIC.md` |
| Security-audited | `reports/P8_7_SECURITY_AUDIT.md` — full threat model, 2 real gaps found and fixed |
| Demo-ready | `python scripts/demo/run_scenarios.py all` — `reports/P8_8_DEMO_ENVIRONMENT.md` |
| Mobile architecture | React Native + Expo SDK 57 + TypeScript (migrated from Flutter/Dart in P9.3 — see `reports/P9_3_MOBILE_REACT_NATIVE.md`) |

---

## 🚀 What actually works today

### Consumer app (React Native + Expo)

Registration/login (role-checked), reporting e-waste for pickup, QR-code
device passport/trust/blockchain-verification lookup, GreenCoin reward
balance and history, recycling history, educational content — offline-first
(AsyncStorage-backed sync queue).

### Collector app (React Native + Expo)

Role-checked login, assigned-pickup queue, accept → start → complete
workflow, camera capture + AI device classification/confirmation,
offline sync queue (AsyncStorage-backed, tested against real
disconnect/reconnect scenarios).

### Recycler workflow (via the API — no dedicated app yet)

Assigned-submission queue, start/complete processing with recorded
material recovery, which auto-issues the consumer's reward.

### Admin & Government (React dashboard)

Full submission audit trail (every user's submissions, not just their
own — see `reports/P8_5_COMPLETE_E2E.md` for the authorization fix that
guarantees this), collector/recycler assignment, blockchain connectivity
status.

### AI device intelligence (`intelligence/device_ai/`, Python)

A real trained detector (register → confirm → finalize → enrich →
Device Passport → local Trust Anchor → external/blockchain-abstraction
Trust Anchor), reachable both through the backend's read-only proxy and
directly for evaluation — see `scripts/demo/run_demo.py`.

### Blockchain layer (`blockchain/chaincode/`)

A real Hyperledger Fabric chaincode (device registration, lifecycle
events, passport anchoring, fingerprint verification) and a real gRPC
Gateway client, both fully tested (47/47 chaincode tests) — against a
protocol-conformant fake Gateway server, since no live Fabric network
exists in this environment (disclosed, not hidden — see `reports/
P8_2_LIVE_BLOCKCHAIN.md`).

### What is **not** built yet (disclosed, not silently dropped)

- A live Hyperledger Fabric network (peer/orderer/CA) — the integration
  code is real, the network to run it against is not.
- Government analytics endpoints (national overview, demand forecast) —
  the frontend already handles this "module not deployed" state
  gracefully rather than faking data.
- A dedicated Recycler mobile app (the workflow is fully functional via
  the API, exercised in `scripts/demo/run_backend_demo.py`).
- A unified view spanning both the AI device-intelligence lifecycle and
  the backend's Submission lifecycle — they are two architecturally
  separate systems today (see `docs/engineering/03_ARCHITECTURE.md`).

---

## 🏗 Architecture

```
React Native Mobile Apps (Collector, Consumer)     React Dashboard (Admin/Gov)
              │                                        │
              └──────────────┬─────────────────────────┘
                              ▼
                  Node.js Backend (Express + Prisma)
                    │                        │
                    ▼                        ▼
               PostgreSQL          Python AI Service (device_ai)
                                         │
                                         ▼
                          Blockchain abstraction (chaincode +
                          Fabric Gateway client — real; validated
                          against both a fake server and a real
                          local Hyperledger Fabric network, P9.2)
```

See `docs/engineering/03_ARCHITECTURE.md` for the full, current
architecture, and `docs/engineering/08_AI.md`/`09_BLOCKCHAIN.md` for the
AI and blockchain subsystems specifically (both corrected in P8.9 to
match what actually shipped, not an earlier plan).

---

## 🛠 Technology Stack

| Layer | Stack |
|---|---|
| Mobile | React Native, Expo SDK 57, TypeScript, `@react-navigation`, `expo-secure-store` |
| Dashboard | React, TypeScript, Vite, Tailwind CSS |
| Backend | Node.js, Express, TypeScript, Prisma ORM |
| Database | PostgreSQL |
| AI service | Python, FastAPI, a trained YOLO-family detector, OCR, CLIP embeddings |
| Blockchain | Hyperledger Fabric chaincode (TypeScript) + a real gRPC Gateway client (Python) |
| DevOps | Docker / Docker Compose; GitHub Actions CI for the backend (`.github/workflows/backend-ci.yml`) |

---

## 📂 Repository Structure

Real, working code lives here:

```
backend/                  Node/Express/Prisma API — the real product backend
frontend/                 React admin/government dashboard
intelligence/device_ai/   Python AI service — device lifecycle, passport, trust
mobile/collector_app/     React Native (Expo) Collector app
mobile/consumer_app/      React Native (Expo) Consumer app
blockchain/chaincode/     Hyperledger Fabric chaincode (TypeScript, tested)
scripts/demo/             Demo/pilot environment scripts (see QUICKSTART.md)
docs/engineering/         Engineering standards & current architecture docs
reports/                  Every phase's real, evidence-backed report
```

`ai/`, `dashboard/`, `database/`, `deployment/`, `testing/` at the repo
root are early pre-implementation scaffolding from the project's first
commit — never built out, superseded by the directories above. Left in
place rather than silently deleted during a documentation phase; not
part of the working system.

---

## 📚 Documentation

- **[`QUICKSTART.md`](QUICKSTART.md)** — get the full stack running and
  see it work, in under 10 minutes.
- `docs/engineering/` — current architecture, API contract, database
  schema, deployment, testing, and AI/blockchain subsystem docs.
- `reports/` — one real, evidence-backed report per engineering phase
  (P4 dataset work through P8 pilot validation).
- `PROJECT.md` — the project charter.
- `CLAUDE.md` — repository instructions for AI coding agents.

---

## 🚀 Development Workflow

```
feature/<name> → Pull Request → develop → main
```

Never committed directly to `main`; history is never rewritten (see
`CLAUDE.md` → Git Workflow).

---

## 👥 Team

**EcoTrace India Team** — IEEE YESIST 2026

## 📄 License

MIT License
