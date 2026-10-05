import type { Request, Response } from 'express';
import type { SuccessResponse } from '../../types';
import type { ForecastQuery } from './analytics.schemas';
import type {
  AnalyticsService,
  DemandForecast,
  EnvironmentalImpact,
  NationalOverview,
  RegionalBreakdown,
} from './analytics.service';

export interface AnalyticsController {
  getOverview(req: Request, res: Response): Promise<void>;
  getRegions(req: Request, res: Response): Promise<void>;
  getEnvironmentalImpact(req: Request, res: Response): Promise<void>;
  getForecast(req: Request, res: Response): Promise<void>;
}

/** Thin controller: delegates to the service and shapes the HTTP response. */
export function createAnalyticsController(service: AnalyticsService): AnalyticsController {
  return {
    async getOverview(_req: Request, res: Response): Promise<void> {
      const result = await service.getOverview();
      const body: SuccessResponse<NationalOverview> = { success: true, data: result };
      res.status(200).json(body);
    },

    async getRegions(_req: Request, res: Response): Promise<void> {
      const result = await service.getRegionalBreakdown();
      const body: SuccessResponse<RegionalBreakdown> = { success: true, data: result };
      res.status(200).json(body);
    },

    async getEnvironmentalImpact(_req: Request, res: Response): Promise<void> {
      const result = await service.getEnvironmentalImpact();
      const body: SuccessResponse<EnvironmentalImpact> = { success: true, data: result };
      res.status(200).json(body);
    },

    async getForecast(req: Request, res: Response): Promise<void> {
      const { horizon } = req.query as unknown as ForecastQuery;
      const result = await service.getForecast(horizon);
      const body: SuccessResponse<DemandForecast> = { success: true, data: result };
      res.status(200).json(body);
    },
  };
}
