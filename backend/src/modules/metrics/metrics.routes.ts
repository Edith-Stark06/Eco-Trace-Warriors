import { Router } from 'express';
import type { MetricsController } from './metrics.controller';

/**
 * Mounts the metrics route. Public, read-only, no request body, no
 * authentication — the JSON summary contains only aggregate counts/timings
 * per route (method + matched path template, never raw URLs or bodies), so
 * it carries no more sensitive information than the existing `/health`
 * endpoint.
 */
export function createMetricsRouter(controller: MetricsController): Router {
  const router = Router();
  router.get('/metrics', (req, res) => controller.getMetrics(req, res));
  return router;
}
