import type { RequestHandler } from 'express';
import type { MetricsRegistry } from './metrics';

/**
 * Records request count/latency into the given registry on every response.
 * Uses the matched route pattern (`req.baseUrl` + `req.route.path`), not the
 * raw URL, so per-path parameters (e.g. `/submissions/:id`) don't explode
 * cardinality. Falls back to `req.path` for requests that never matched a
 * route (404s), labeled once under a fixed "unmatched" route.
 */
export function metricsMiddleware(registry: MetricsRegistry): RequestHandler {
  return (req, res, next) => {
    const start = process.hrtime.bigint();

    res.on('finish', () => {
      const durationMs = Number(process.hrtime.bigint() - start) / 1_000_000;
      const routePath = (req.route as { path?: string } | undefined)?.path;
      const route = routePath ? `${req.baseUrl}${routePath}` : 'unmatched';
      registry.recordRequest(req.method, route, res.statusCode, durationMs);
    });

    next();
  };
}
