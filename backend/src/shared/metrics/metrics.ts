/**
 * Minimal, dependency-free in-process metrics registry (P7.3).
 *
 * Deliberately not a Prometheus client: no scrape target (Prometheus/
 * Grafana) exists anywhere in this repository or environment, so pulling in
 * `prom-client` for a text-exposition format nothing consumes would be an
 * unused dependency. This exposes the same underlying counts as a small
 * JSON summary instead (`GET /metrics`), which is enough to answer "how
 * many requests, how fast, how many blockchain health checks failed" —
 * the actual questions this phase's brief asks for — without inventing
 * infrastructure this project doesn't otherwise have.
 */

interface RouteStats {
  count: number;
  totalDurationMs: number;
  statusCounts: Record<string, number>;
}

interface BlockchainStats {
  checks: number;
  connected: number;
  unavailable: number;
  proxyUnreachable: number;
}

export interface MetricsRegistry {
  recordRequest(method: string, route: string, statusCode: number, durationMs: number): void;
  recordBlockchainCheck(status: string): void;
  snapshot(): MetricsSnapshot;
  reset(): void;
}

export interface MetricsSnapshot {
  uptimeSeconds: number;
  requests: {
    total: number;
    byRoute: Array<{
      method: string;
      route: string;
      count: number;
      avgDurationMs: number;
      statusCounts: Record<string, number>;
    }>;
  };
  blockchain: BlockchainStats;
}

/** Creates a fresh, process-local metrics registry. Not persisted, not shared across instances. */
export function createMetricsRegistry(now: () => number = Date.now): MetricsRegistry {
  const routeStats = new Map<string, RouteStats>();
  const blockchain: BlockchainStats = {
    checks: 0,
    connected: 0,
    unavailable: 0,
    proxyUnreachable: 0,
  };
  const startedAt = now();

  return {
    recordRequest(method, route, statusCode, durationMs): void {
      const key = `${method} ${route}`;
      const existing = routeStats.get(key) ?? { count: 0, totalDurationMs: 0, statusCounts: {} };
      existing.count += 1;
      existing.totalDurationMs += durationMs;
      const statusKey = String(statusCode);
      existing.statusCounts[statusKey] = (existing.statusCounts[statusKey] ?? 0) + 1;
      routeStats.set(key, existing);
    },

    recordBlockchainCheck(status): void {
      blockchain.checks += 1;
      if (status === 'connected') {
        blockchain.connected += 1;
      } else if (status === 'proxy_unreachable') {
        blockchain.proxyUnreachable += 1;
      } else {
        blockchain.unavailable += 1;
      }
    },

    snapshot(): MetricsSnapshot {
      const byRoute = [...routeStats.entries()].map(([key, stats]) => {
        const [method, ...routeParts] = key.split(' ');
        return {
          method: method ?? '',
          route: routeParts.join(' '),
          count: stats.count,
          avgDurationMs: stats.count > 0 ? stats.totalDurationMs / stats.count : 0,
          statusCounts: { ...stats.statusCounts },
        };
      });
      const total = byRoute.reduce((sum, r) => sum + r.count, 0);

      return {
        uptimeSeconds: (now() - startedAt) / 1000,
        requests: { total, byRoute },
        blockchain: { ...blockchain },
      };
    },

    reset(): void {
      routeStats.clear();
      blockchain.checks = 0;
      blockchain.connected = 0;
      blockchain.unavailable = 0;
      blockchain.proxyUnreachable = 0;
    },
  };
}
