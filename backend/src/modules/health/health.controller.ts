import type { Request, Response } from 'express';
import type { HealthService } from './health.service';

export interface HealthController {
  getHealth(req: Request, res: Response): void;
  getReadiness(req: Request, res: Response): Promise<void>;
}

/** Thin controller: delegates to the service and shapes the HTTP response. */
export function createHealthController(healthService: HealthService): HealthController {
  return {
    getHealth(_req: Request, res: Response): void {
      res.status(200).json(healthService.getStatus());
    },

    async getReadiness(_req: Request, res: Response): Promise<void> {
      // A not-ready outcome is signalled by a thrown ServiceUnavailableError,
      // which the global error handler maps to a 503 error envelope.
      const readiness = await healthService.getReadiness();
      res.status(200).json(readiness);
    },
  };
}
