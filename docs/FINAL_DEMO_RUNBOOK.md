# EcoTrace India — Final Demo Runbook

Target duration: 5–10 minutes. Verified against the live running stack during finalization (2026-09-06).

## Required environment

- Docker Desktop running, this repository checked out at `D:\Documents\Projects\Eco-Trace-Warriors`, branch `develop`.
- Ports free: 3000 (backend), 8080/8443 (frontend), 8100 (device-ai), 5432 (postgres).
- No cloud/Fabric-live-network dependency required — the demo runs entirely against the documented `disabled` Fabric degradation state, which is itself part of what the demo proves (see step 8).

## Startup

```
docker compose up -d
docker compose ps          # confirm postgres, backend, device-ai, frontend all "healthy"
```

If this is the first run, seed demo accounts and sample submissions:
```
cd backend
npm run build && npx prisma migrate deploy
npx tsx prisma/seed.ts
```
(Seeding is a manual, one-time step — it is not part of `docker compose up` and will not run automatically or repeatedly.)

## Test accounts (seed data only — not real credentials, already committed as dev fixtures)

| Role | Email | Password |
|---|---|---|
| Admin | `admin@ecotrace.com` | `Admin@123` |
| Government | `government@ecotrace.com` | `Admin@123` |
| Collector | `collector@ecotrace.com` | `Admin@123` |
| Recycler | `recycler@ecotrace.com` | `Admin@123` |
| Consumer | `consumer@ecotrace.com` | `Admin@123` |

All five share the same seed password. This is acceptable for a local demo only — see `docs/FINAL_RELEASE_READINESS.md` for the associated security note.

## Demo flow

1. **Login** — open the frontend at `http://localhost:8080`, log in as `admin@ecotrace.com`. Expected: dashboard loads, JWT issued, session persists across a page refresh (refresh-token rotation verified working).
2. **Collector captures a device** — on the Collector mobile app (`cd mobile/collector_app && npx expo start --web`, or a real device via Expo Go), log in as `collector@ecotrace.com`, use Capture screen to take 1–5 photos of an electronic device.
3. **Device AI identifies the device** — the capture flow calls `POST http://localhost:8100/devices/register` with the photos; the frozen production YOLO11n detector (8-class: laptop, smartphone, tablet, monitor, printer, mouse, camera, headphones) returns a detection. Expected output shape confirmed live via `GET http://localhost:8100/model`.
4. **EcoID created** — the collector app's confirm/finalize flow registers the device and receives a device ID (EcoID) back from device-ai.
5. **Transaction submitted toward Fabric** — device-ai's Fabric Gateway client attempts the chaincode call. In this environment `FABRIC_ENABLED=false`, so this **honestly degrades** rather than failing hard — confirmed live: `curl http://localhost:3000/api/v1/system/blockchain/health` → `{"status":"disabled","fabricEnabled":false,...}`. This is the documented, correct behavior, not a broken step — the chaincode itself (`RegisterDevice`, `UpdateLifecycle`, `AnchorDevicePassport`) is real and independently tested (47/47 passing) but the live network is not part of this compose stack (see known limitations).
6. **Backend persists/returns the record** — a submission is created via `POST /api/v1/submissions` and is immediately visible via `GET /api/v1/submissions` (verified live with real historical demo data already present: collected → assigned → recycled, with material-recovery figures).
7. **Consumer views the resulting information** — on the Consumer app, log in as `consumer@ecotrace.com`, use the Scan screen (or manual device-ID entry) to open the Device Passport screen: lifecycle state, trust/anchor status (`UNANCHORED` when Fabric is disabled — an honest, documented status, not an error).
8. **Admin observes system state** — back on the Admin dashboard: submission list (search/filter), assignment tools, reward issuance, and the Blockchain Health card showing the real, live "disabled" proxy status pulled from device-ai — this card is exactly what proves the graceful-degradation architecture end-to-end.

## Expected outputs (what "working" looks like)

- Login returns a JWT pair for every role; unauthenticated API calls get 401.
- `GET /api/v1/health` → `{"status":"ok",...}`; `GET /api/v1/ready` → `{"database":"connected","ready":true}`.
- `GET http://localhost:8100/health` → all 5 components (`detector, condition, ocr, material, clip`) report `ready: true`.
- `GET http://localhost:8100/model` → the exact 8-class map above.
- Submission lifecycle transitions are visible in the admin dashboard immediately after each step (no manual refresh needed beyond normal page navigation).

## Known limitations (state honestly during the demo, do not hide)

- **Fabric is in its documented `disabled` state** in this environment — no live blockchain network is running as part of `docker compose up`. The chaincode and Gateway client are real and independently tested, but demonstrating a *live* chain transaction requires a separate, manual Fabric network bootstrap not included in this runbook (see `reports/P9_2_LIVE_FABRIC.md` for how that was previously done).
- **Device AI detector is an 8-class subset** of the 19-class authoritative taxonomy (laptop, smartphone, tablet, monitor, printer, mouse, camera, headphones only) — the other 11 classes are not detectable by the current production model. A known model-quality limitation also exists: confusion between visually similar screen-device classes (smartphone/laptop/tablet) — do not claim perfect detection accuracy during the demo.
- **Admin dashboard's analytics, full user-management, and system-activity feed are not implemented** (honestly labeled "unavailable" in the UI) — do not promise these live.
- **No automated E2E test suite exists** — this runbook's flow has been verified via direct live API/service checks (documented in `FINALIZATION_AUDIT.md`) plus each app's own unit tests, not a scripted end-to-end browser test.

## Recovery steps if a service fails

- **A container isn't healthy**: `docker compose logs <service> --tail=50`, then `docker compose restart <service>`.
- **Backend can't reach Postgres**: confirm `ecotrace-postgres` is healthy first; the backend readiness check (`/api/v1/ready`) will report `database: disconnected` clearly rather than crashing.
- **Device-ai reports a component not ready**: check `GET http://localhost:8100/health` for which component; this does not require restarting the whole stack — the service degrades per-component honestly.
- **Frontend shows a stale build**: `docker compose build frontend && docker compose up -d frontend`.
- **Mobile app can't reach the backend/device-ai from a physical device**: set `EXPO_PUBLIC_API_BASE_URL` / `EXPO_PUBLIC_DEVICE_AI_BASE_URL` to your machine's LAN IP (not `localhost`) before `expo start`.
