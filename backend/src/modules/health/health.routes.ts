import { Router } from 'express';
import type { HealthController } from './health.controller';

/** Mounts the health module routes. Public endpoints — no authentication. */
export function createHealthRouter(controller: HealthController): Router {
  const router = Router();
  router.get('/health', (req, res) => controller.getHealth(req, res));
  // Async handler: forward any rejection to the global error middleware.
  router.get('/ready', (req, res, next) => {
    controller.getReadiness(req, res).catch(next);
  });
  return router;
}
