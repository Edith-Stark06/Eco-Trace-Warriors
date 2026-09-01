#!/usr/bin/env python3
"""P8.6 — minimal, dependency-free (beyond `requests`, already used by
scripts/demo/run_demo.py) concurrent load-test harness.

Fires N total requests at a target URL using up to C concurrent worker
threads, measuring real wall-clock latency per request against the live
docker-compose stack. No mocking, no simulated timings — every number here
is a real, measured HTTP round trip.

Usage:
    python loadtest.py --name health --url http://localhost:3000/api/v1/health \
        --concurrency 1,10,25,50 --requests-per-level 100
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests


def _one_request(method: str, url: str, headers: dict[str, str] | None, body: Any) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        resp = requests.request(method, url, headers=headers, json=body, timeout=30)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return {"ok": resp.status_code < 500, "status": resp.status_code, "latency_ms": elapsed_ms}
    except requests.exceptions.RequestException as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return {"ok": False, "status": None, "latency_ms": elapsed_ms, "error": str(exc)}


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


def run_level(
    method: str,
    url: str,
    concurrency: int,
    total_requests: int,
    headers: dict[str, str] | None,
    body: Any,
) -> dict[str, Any]:
    latencies: list[float] = []
    statuses: dict[str, int] = {}
    errors = 0

    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(_one_request, method, url, headers, body) for _ in range(total_requests)
        ]
        for fut in as_completed(futures):
            result = fut.result()
            latencies.append(result["latency_ms"])
            key = str(result["status"])
            statuses[key] = statuses.get(key, 0) + 1
            if not result["ok"]:
                errors += 1
    wall_elapsed_s = time.perf_counter() - wall_start

    return {
        "concurrency": concurrency,
        "total_requests": total_requests,
        "wall_elapsed_s": round(wall_elapsed_s, 4),
        "throughput_rps": round(total_requests / wall_elapsed_s, 2) if wall_elapsed_s > 0 else None,
        "error_count": errors,
        "error_rate_pct": round(100.0 * errors / total_requests, 2) if total_requests else 0.0,
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--method", default="GET")
    parser.add_argument("--concurrency", default="1,10,25,50", help="comma-separated levels")
    parser.add_argument("--requests-per-level", type=int, default=100)
    parser.add_argument("--header", action="append", default=[], help="Header: 'Key: Value', repeatable")
    parser.add_argument("--body", default=None, help="JSON body string for POST/PATCH")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    headers: dict[str, str] = {}
    for h in args.header:
        k, _, v = h.partition(":")
        headers[k.strip()] = v.strip()

    body = json.loads(args.body) if args.body else None
    levels = [int(x) for x in args.concurrency.split(",")]

    print(f"=== Load test: {args.name} -> {args.method} {args.url} ===")
    results = []
    for c in levels:
        n = max(args.requests_per_level, c)  # at least one request per worker
        print(f"  concurrency={c} requests={n} ...")
        level_result = run_level(args.method, args.url, c, n, headers or None, body)
        results.append(level_result)
        print(
            f"    p50={level_result['latency_ms']['p50']}ms "
            f"p95={level_result['latency_ms']['p95']}ms "
            f"p99={level_result['latency_ms']['p99']}ms "
            f"throughput={level_result['throughput_rps']}rps "
            f"errors={level_result['error_count']}/{n}"
        )

    output = {"name": args.name, "url": args.url, "method": args.method, "levels": results}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"Saved: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
