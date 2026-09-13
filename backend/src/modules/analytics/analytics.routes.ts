import { Router } from 'express';
import type { RequestHandler } from 'express';
import { UserRole } from '@prisma/client';
import { validate } from '@shared/middleware';
import type { AnalyticsController } from './analytics.controller';
import { forecastQuerySchema } from './analytics.schemas';

/** Middleware injected into the analytics router. */
export interface AnalyticsRouterDeps {
  /** Verifies the Bearer access token and attaches req.user. */
  readonly authenticate: RequestHandler;
  /** Builds a role guard — reuses the shared authorize() middleware. */
  readonly authorize: (...roles: readonly UserRole[]) => RequestHandler;
}

/**
 * Mounts the Government Analytics module routes (docs/engineering/05_API.md
 * "Analytics"). All four routes are read-only and restricted to GOVERNMENT
 * and ADMIN, matching the documented "G, A" role column.
 *
 * `/analytics/forecast` (P10.1) proxies real predictions from
 * intelligence/device_ai's LSTM forecasting engine (see
 * device_ai/forecasting/) — it aggregates real Submission.recycledAt
 * /recoveredWeight history and forwards it for training/inference. It never
 * returns fabricated values: when there is too little history or the
 * model backend is unavailable, the response says so explicitly via
 * `status`/`reason` rather than inventing a prediction.
 */
export function createAnalyticsRouter(
  controller: AnalyticsController,
  deps: AnalyticsRouterDeps,
): Router {
  const router = Router();
  const { authenticate, authorize } = deps;
  const allowGovernmentOrAdmin = authorize(UserRole.GOVERNMENT, UserRole.ADMIN);

  router.get('/analytics/overview', authenticate, allowGovernmentOrAdmin, (req, res, next) => {
    controller.getOverview(req, res).catch(next);
  });

  router.get('/analytics/regions', authenticate, allowGovernmentOrAdmin, (req, res, next) => {
    controller.getRegions(req, res).catch(next);
  });

  router.get(
    '/analytics/environmental-impact',
    authenticate,
    allowGovernmentOrAdmin,
    (req, res, next) => {
      controller.getEnvironmentalImpact(req, res).catch(next);
    },
  );

  router.get(
    '/analytics/forecast',
    authenticate,
    allowGovernmentOrAdmin,
    validate({ query: forecastQuerySchema }),
    (req, res, next) => {
      controller.getForecast(req, res).catch(next);
    },
  );

  return router;
}
