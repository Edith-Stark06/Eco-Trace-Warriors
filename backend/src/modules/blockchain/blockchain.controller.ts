import type { Request, Response } from 'express';
import type { BlockchainService } from './blockchain.service';
import type { BlockchainHealthResponse } from './blockchain.types';

export interface BlockchainController {
  getHealth(req: Request, res: Response): Promise<void>;
}

/** Thin controller: delegates to the service and shapes the HTTP response. */
export function createBlockchainController(service: BlockchainService): BlockchainController {
  return {
    async getHealth(_req: Request, res: Response): Promise<void> {
      const health = await service.getHealth();
      const body: BlockchainHealthResponse = { success: true, data: health };
      res.status(200).json(body);
    },
  };
}
