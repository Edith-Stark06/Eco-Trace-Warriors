import { Router } from 'express';
import type { RequestHandler } from 'express';
import { UserRole } from '@prisma/client';
import { validate } from '@shared/middleware';
import {
  createSubmissionSchema,
  submissionIdSchema,
  updateSubmissionSchema,
} from './submission.schemas';
import type { SubmissionController } from './submission.controller';

/** Middleware injected into the submission router. */
export interface SubmissionRouterDeps {
  /** Verifies the Bearer access token and attaches req.user. */
  readonly authenticate: RequestHandler;
  /** Builds a role guard — reuses the shared authorize() middleware. */
  readonly authorize: (...roles: readonly UserRole[]) => RequestHandler;
}

/**
 * Mounts the submission module routes. All routes require authentication.
 * Creation is restricted to consumers; read/update/delete are open to any
 * authenticated user, with ownership and admin rules enforced in the service.
 * Async handlers forward rejections to the global error middleware.
 */
export function createSubmissionRouter(
  controller: SubmissionController,
  deps: SubmissionRouterDeps,
): Router {
  const router = Router();
  const { authenticate, authorize } = deps;

  router.post(
    '/submissions',
    authenticate,
    authorize(UserRole.CONSUMER),
    validate({ body: createSubmissionSchema }),
    (req, res, next) => {
      controller.create(req, res).catch(next);
    },
  );

  router.get('/submissions', authenticate, (req, res, next) => {
    controller.list(req, res).catch(next);
  });

  router.get(
    '/submissions/:id',
    authenticate,
    validate({ params: submissionIdSchema }),
    (req, res, next) => {
      controller.getById(req, res).catch(next);
    },
  );

  router.patch(
    '/submissions/:id',
    authenticate,
    validate({ params: submissionIdSchema, body: updateSubmissionSchema }),
    (req, res, next) => {
      controller.update(req, res).catch(next);
    },
  );

  router.delete(
    '/submissions/:id',
    authenticate,
    validate({ params: submissionIdSchema }),
    (req, res, next) => {
      controller.delete(req, res).catch(next);
    },
  );

  return router;
}
