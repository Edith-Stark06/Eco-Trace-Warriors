import { Router } from 'express';
import type { ApiInfoController } from './api-info.controller';

/** Mounts the API info route at the API root. Public endpoint — no authentication. */
export function createApiInfoRouter(controller: ApiInfoController): Router {
  const router = Router();
  router.get('/', (req, res) => controller.getInfo(req, res));
  return router;
}
