import { Router } from 'express';
import type { RequestHandler } from 'express';
import { UserRole } from '@prisma/client';
import { validate } from '@shared/middleware';
import { rewardSubmissionIdSchema } from './reward.schemas';
import type { RewardController } from './reward.controller';

/** Middleware injected into the reward router. */
export interface RewardRouterDeps {
  /** Verifies the Bearer access token and attaches req.user. */
  readonly authenticate: RequestHandler;
  /** Builds a role guard — reuses the shared authorize() middleware. */
  readonly authorize: (...roles: readonly UserRole[]) => RequestHandler;
}

/**
 * Mounts the reward module routes. All routes require authentication.
 * Manual reward issuance is an administrative override (rewards are issued
 * automatically when recycling completes), so it is restricted to ADMIN.
 * History and balance read the caller's own data and need no role guard.
 * Async handlers forward rejections to the global error middleware.
 */
export function createRewardRouter(controller: RewardController, deps: RewardRouterDeps): Router {
  const router = Router();
  const { authenticate, authorize } = deps;

  router.post(
    '/rewards/issue/:submissionId',
    authenticate,
    authorize(UserRole.ADMIN),
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
