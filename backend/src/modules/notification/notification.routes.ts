import { Router } from 'express';
import type { RequestHandler } from 'express';
import { UserRole } from '@prisma/client';
import { validate } from '@shared/middleware';
import { paginationQuerySchema } from '@shared/pagination';
import { notificationIdSchema } from './notification.schemas';
import type { NotificationController } from './notification.controller';

/** Middleware injected into the notification router. */
export interface NotificationRouterDeps {
  /** Verifies the Bearer access token and attaches req.user. */
  readonly authenticate: RequestHandler;
  /** Builds a role guard — reuses the shared authorize() middleware. */
  readonly authorize: (...roles: readonly UserRole[]) => RequestHandler;
}

/**
 * Mounts the notification module routes. Consumer-only (P10.3's approved
 * scope) — Collector/Recycler/Government/Admin have no notification feed in
 * this feature. `userId` is never a route parameter; both handlers derive it
 * exclusively from the authenticated access token (see
 * notification.controller.ts). Async handlers forward rejections to the
 * global error middleware.
 */
export function createNotificationRouter(
  controller: NotificationController,
  deps: NotificationRouterDeps,
): Router {
  const router = Router();
  const { authenticate, authorize } = deps;

  router.get(
    '/notifications',
    authenticate,
    authorize(UserRole.CONSUMER),
    validate({ query: paginationQuerySchema }),
    (req, res, next) => {
      controller.list(req, res).catch(next);
    },
  );

  router.patch(
    '/notifications/:id/read',
    authenticate,
    authorize(UserRole.CONSUMER),
    validate({ params: notificationIdSchema }),
    (req, res, next) => {
      controller.markRead(req, res).catch(next);
    },
  );

  return router;
}
