#!/usr/bin/env python3
"""P8.6 — ML inference latency benchmark: real multipart POST /devices/register
against the live device-ai container. Each request runs the actual detector
pipeline (single_model inference mode, confirmed via /health) on a freshly
generated, distinct PNG so no request-level caching can mask true latency.
"""
from __future__ import annotations

import argparse
import io
import json
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from PIL import Image


def _make_image_bytes(seed: int) -> bytes:
    buf = io.BytesIO()
    color = (seed % 200 + 20, (seed * 7) % 200 + 20, (seed * 13) % 200 + 20)
    Image.new("RGB", (256, 256), color=color).save(buf, format="PNG")
    return buf.getvalue()


def _one_register(base_url: str, seed: int) -> dict:
    capture_id = f"p86-loadtest-{uuid.uuid4().hex[:10]}"
    files = [("images", (f"lt_{seed}.png", _make_image_bytes(seed), "image/png"))]
    start = time.perf_counter()
    try:
        resp = requests.post(
            f"{base_url}/devices/register", files=files, data={"capture_id": capture_id}, timeout=60
        )
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


def run_level(base_url: str, concurrency: int, total: int) -> dict:
    latencies: list[float] = []
    statuses: dict[str, int] = {}
    errors = 0
    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_one_register, base_url, i) for i in range(total)]
        for fut in as_completed(futures):
            r = fut.result()
            latencies.append(r["latency_ms"])
            key = str(r["status"])
            statuses[key] = statuses.get(key, 0) + 1
            if not r["ok"]:
                errors += 1
    wall_elapsed_s = time.perf_counter() - wall_start
    return {
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8100")
    parser.add_argument("--concurrency", default="1,10,25,50")
    parser.add_argument("--requests-per-level", type=int, default=20)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    levels = [int(x) for x in args.concurrency.split(",")]
    print(f"=== ML inference load test: POST {args.base_url}/devices/register ===")
    results = []
    for c in levels:
        n = max(args.requests_per_level, c)
        print(f"  concurrency={c} requests={n} ...")
        lvl = run_level(args.base_url, c, n)
        results.append(lvl)
        print(
            f"    p50={lvl['latency_ms']['p50']}ms p95={lvl['latency_ms']['p95']}ms "
            f"p99={lvl['latency_ms']['p99']}ms throughput={lvl['throughput_rps']}rps "
            f"errors={lvl['error_count']}/{n}"
        )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"name": "device_ai_register_ml_inference", "levels": results}, f, indent=2)
    print(f"Saved: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
