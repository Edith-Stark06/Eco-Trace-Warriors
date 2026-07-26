import type { Request, Response } from 'express';
import { getAuthContext } from '@modules/auth';
import type { Pagination } from '@shared/pagination';
import type { SuccessResponse } from '../../types';
import type { RewardBalance, RewardService, RewardSummary } from './reward.service';
import type { RewardTransactionWithSubmission } from './reward.repository';

export interface RewardController {
  issueReward(req: Request, res: Response): Promise<void>;
  getRewardHistory(req: Request, res: Response): Promise<void>;
  getBalance(req: Request, res: Response): Promise<void>;
}

/** Reads validated pagination coerced onto the request query by `validate`. */
function paginationOf(req: Request): Pagination {
  return req.query as unknown as Pagination;
}

/** Thin controller: delegates to the service and shapes the HTTP response. */
export function createRewardController(service: RewardService): RewardController {
  return {
    async issueReward(req: Request, res: Response): Promise<void> {
      const { submissionId } = req.params as { submissionId: string };
      const result = await service.issueReward(submissionId);
      const body: SuccessResponse<RewardSummary> = { success: true, data: result };
      res.status(201).json(body);
    },

    async getRewardHistory(req: Request, res: Response): Promise<void> {
      const { userId } = getAuthContext(req);
      const result = await service.getRewardHistory(userId, paginationOf(req));
      const body: SuccessResponse<RewardTransactionWithSubmission[]> = {
        success: true,
        data: result,
      };
      res.status(200).json(body);
    },

    async getBalance(req: Request, res: Response): Promise<void> {
      const { userId } = getAuthContext(req);
      const result = await service.getBalance(userId);
      const body: SuccessResponse<RewardBalance> = { success: true, data: result };
      res.status(200).json(body);
    },
  };
}
