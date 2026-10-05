import type { Request, Response } from 'express';
import type { ApiInfoService } from './api-info.service';

export interface ApiInfoController {
  getInfo(req: Request, res: Response): void;
}

/** Thin controller: delegates to the service and shapes the HTTP response. */
export function createApiInfoController(apiInfoService: ApiInfoService): ApiInfoController {
  return {
    getInfo(_req: Request, res: Response): void {
      res.status(200).json(apiInfoService.getInfo());
    },
  };
}
