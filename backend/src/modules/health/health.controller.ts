import type { Request, Response } from 'express';
import type { HealthService } from './health.service';

export interface HealthController {
  getHealth(req: Request, res: Response): void;
}

/** Thin controller: delegates to the service and shapes the HTTP response. */
export function createHealthController(healthService: HealthService): HealthController {
  return {
    getHealth(_req: Request, res: Response): void {
      res.status(200).json(healthService.getStatus());
    },
  };
}
