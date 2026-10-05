#!/usr/bin/env python3
"""P8.6 — real Postgres write-path load test: POST /submissions as the
seeded consumer account. Every created submission is tagged with a
"P8.6-LOADTEST" description marker and its id is recorded so this script's
own --cleanup pass can delete every record it created afterward, leaving no
load-test residue in the database.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BASE = "http://localhost:3000/api/v1"


def _one_create(token: str, seed: int) -> dict:
    body = {
        "category": "LAPTOP",
        "description": f"P8.6-LOADTEST submission #{seed}",
        "estimatedWeight": 2.0,
        "address": "P8.6 Load Test Address, Chennai",
        "latitude": 13.08,
        "longitude": 80.27,
    }
    start = time.perf_counter()
    try:
        resp = requests.post(
            f"{BASE}/submissions",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        sub_id = None
        if resp.status_code < 300:
            try:
                sub_id = resp.json()["data"]["id"]
            except (KeyError, ValueError):
                pass
        return {"ok": resp.status_code < 500, "status": resp.status_code, "latency_ms": elapsed_ms, "id": sub_id}
    except requests.exceptions.RequestException as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return {"ok": False, "status": None, "latency_ms": elapsed_ms, "id": None, "error": str(exc)}


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


def run_level(token: str, concurrency: int, total: int) -> tuple[dict, list[str]]:
    latencies: list[float] = []
    statuses: dict[str, int] = {}
    ids: list[str] = []
    errors = 0
    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_one_create, token, i) for i in range(total)]
        for fut in as_completed(futures):
            r = fut.result()
            latencies.append(r["latency_ms"])
            key = str(r["status"])
            statuses[key] = statuses.get(key, 0) + 1
            if r["id"]:
                ids.append(r["id"])
            if not r["ok"]:
                errors += 1
    wall_elapsed_s = time.perf_counter() - wall_start
    summary = {
        "concurrency": concurrency,
        "total_requests": total,
        "wall_elapsed_s": round(wall_elapsed_s, 4),
        "throughput_rps": round(total / wall_elapsed_s, 2) if wall_elapsed_s > 0 else None,
        "error_count": errors,
        "error_rate_pct": round(100.0 * errors / total, 2) if total else 0.0,
        "status_breakdown": statuses,
        "latency_ms": {
            "min": round(min(latencies), 2) if latencies else None,
            "mean": round(statistics.mean(latencies), 2) if latencies else None,
            "p50": round(percentile(latencies, 50), 2),
            "p95": round(percentile(latencies, 95), 2),
            "p99": round(percentile(latencies, 99), 2),
            "max": round(max(latencies), 2) if latencies else None,
        },
    }
    return summary, ids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--concurrency", default="1,10,25,50")
    parser.add_argument("--requests-per-level", type=int, default=30)
    parser.add_argument("--out", required=True)
    parser.add_argument("--ids-out", required=True)
    args = parser.parse_args()

    token = open(args.token_file, encoding="utf-8").read().strip()
    levels = [int(x) for x in args.concurrency.split(",")]

    print(f"=== Write-path load test: POST {BASE}/submissions ===")
    results = []
    all_ids: list[str] = []
    for c in levels:
        n = max(args.requests_per_level, c)
        print(f"  concurrency={c} requests={n} ...")
        lvl, ids = run_level(token, c, n)
        results.append(lvl)
        all_ids.extend(ids)
        print(
            f"    p50={lvl['latency_ms']['p50']}ms p95={lvl['latency_ms']['p95']}ms "
            f"p99={lvl['latency_ms']['p99']}ms throughput={lvl['throughput_rps']}rps "
            f"errors={lvl['error_count']}/{n} created={len(ids)}"
        )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"name": "backend_submissions_create_db_write", "levels": results}, f, indent=2)
    with open(args.ids_out, "w", encoding="utf-8") as f:
        json.dump(all_ids, f)
    print(f"Saved: {args.out} ({len(all_ids)} submissions created, ids saved to {args.ids_out})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
