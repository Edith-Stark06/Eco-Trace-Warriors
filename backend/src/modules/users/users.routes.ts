import { Router } from 'express';
import type { RequestHandler } from 'express';
import { UserRole } from '@prisma/client';
import { validate } from '@shared/middleware';
import { listUsersQuerySchema } from './users.schemas';
import type { UsersController } from './users.controller';

/** Middleware injected into the users router. */
export interface UsersRouterDeps {
  /** Verifies the Bearer access token and attaches req.user. */
  readonly authenticate: RequestHandler;
  /** Builds a role guard — reuses the shared authorize() middleware. */
  readonly authorize: (...roles: readonly UserRole[]) => RequestHandler;
}

/**
 * Mounts the users module routes. GET /users?role= is a directory lookup for
 * assignment workflows: admins and government users resolve eligible collectors
 * and recyclers. No other user-listing capability is exposed. Async handlers
 * forward rejections to the global error middleware.
 */
export function createUsersRouter(controller: UsersController, deps: UsersRouterDeps): Router {
  const router = Router();
  const { authenticate, authorize } = deps;

  router.get(
    '/users',
    authenticate,
    authorize(UserRole.ADMIN, UserRole.GOVERNMENT),
    validate({ query: listUsersQuerySchema }),
    (req, res, next) => {
      controller.list(req, res).catch(next);
    },
  );

  return router;
}
