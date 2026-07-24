import { Router } from 'express';
import type { RequestHandler } from 'express';
import { validate } from '@shared/middleware';
import { rewardSubmissionIdSchema } from './reward.schemas';
import type { RewardController } from './reward.controller';

/** Middleware injected into the reward router. */
export interface RewardRouterDeps {
  /** Verifies the Bearer access token and attaches req.user. */
  readonly authenticate: RequestHandler;
}

/**
 * Mounts the reward module routes. All routes require authentication.
 * Async handlers forward rejections to the global error middleware.
 */
export function createRewardRouter(controller: RewardController, deps: RewardRouterDeps): Router {
  const router = Router();
  const { authenticate } = deps;

  router.post(
    '/rewards/issue/:submissionId',
    authenticate,
    validate({ params: rewardSubmissionIdSchema }),
    (req, res, next) => {
      controller.issueReward(req, res).catch(next);
    },
  );

  router.get('/rewards/history', authenticate, (req, res, next) => {
    controller.getRewardHistory(req, res).catch(next);
  });

  router.get('/rewards/balance', authenticate, (req, res, next) => {
    controller.getBalance(req, res).catch(next);
  });

  return router;
}
