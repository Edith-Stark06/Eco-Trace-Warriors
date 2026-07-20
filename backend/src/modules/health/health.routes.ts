import { Router } from 'express';
import type { HealthController } from './health.controller';

/** Mounts the health module routes. Public endpoint — no authentication. */
export function createHealthRouter(controller: HealthController): Router {
  const router = Router();
  router.get('/health', (req, res) => controller.getHealth(req, res));
  return router;
}
