import type { Request, Response } from 'express';
import type { MetricsRegistry } from '@shared/metrics';

export interface MetricsController {
  getMetrics(req: Request, res: Response): void;
}

/** Thin controller: reads the registry snapshot and shapes the HTTP response. */
export function createMetricsController(registry: MetricsRegistry): MetricsController {
  return {
    getMetrics(_req: Request, res: Response): void {
      res.status(200).json({ success: true, data: registry.snapshot() });
    },
  };
}
