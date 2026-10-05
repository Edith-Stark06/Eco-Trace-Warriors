import { Router } from 'express';
import type { RequestHandler } from 'express';
import { UserRole } from '@prisma/client';
import { validate } from '@shared/middleware';
import { paginationQuerySchema } from '@shared/pagination';
import {
  assignCollectorSchema,
  assignRecyclerSchema,
  completeRecyclingSchema,
  createSubmissionSchema,
  deviceIdentifierParamSchema,
  linkDeviceSchema,
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

  router.get(
    '/submissions',
    authenticate,
    validate({ query: paginationQuerySchema }),
    (req, res, next) => {
      controller.list(req, res).catch(next);
    },
  );

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

  // --- Collector workflow (Phase 6) -----------------------------------------
  // Status transitions live on the submission resource as sub-actions. Route
  // guards enforce the coarse role; the service enforces ownership + transition.

  // Admin / Government assign a collector: PENDING → ASSIGNED.
  router.patch(
    '/submissions/:id/assign',
    authenticate,
    authorize(UserRole.ADMIN, UserRole.GOVERNMENT),
    validate({ params: submissionIdSchema, body: assignCollectorSchema }),
    (req, res, next) => {
      controller.assignCollector(req, res).catch(next);
    },
  );

  // Collector accepts the assignment: ASSIGNED → ACCEPTED.
  router.patch(
    '/submissions/:id/accept',
    authenticate,
    authorize(UserRole.COLLECTOR),
    validate({ params: submissionIdSchema }),
    (req, res, next) => {
      controller.acceptAssignment(req, res).catch(next);
    },
  );

  // Collector starts the pickup: ACCEPTED → IN_PROGRESS.
  router.patch(
    '/submissions/:id/start',
    authenticate,
    authorize(UserRole.COLLECTOR),
    validate({ params: submissionIdSchema }),
    (req, res, next) => {
      controller.startPickup(req, res).catch(next);
    },
  );

  // Collector completes the pickup: IN_PROGRESS → COLLECTED.
  router.patch(
    '/submissions/:id/complete',
    authenticate,
    authorize(UserRole.COLLECTOR),
    validate({ params: submissionIdSchema }),
    (req, res, next) => {
      controller.completePickup(req, res).catch(next);
    },
  );

  // Collector dashboard: active assignments for the authenticated collector.
  router.get(
    '/collector/submissions',
    authenticate,
    authorize(UserRole.COLLECTOR),
    validate({ query: paginationQuerySchema }),
    (req, res, next) => {
      controller.collectorDashboard(req, res).catch(next);
    },
  );

  // --- Recycler workflow (Phase 7) ------------------------------------------
  // Recycling continues the lifecycle after COLLECTED. Route guards enforce the
  // coarse role; the service enforces recycler ownership + transition legality.

  // Admin / Government assign a recycler to a collected submission.
  router.patch(
    '/submissions/:id/assign-recycler',
    authenticate,
    authorize(UserRole.ADMIN, UserRole.GOVERNMENT),
    validate({ params: submissionIdSchema, body: assignRecyclerSchema }),
    (req, res, next) => {
      controller.assignRecycler(req, res).catch(next);
    },
  );

  // Recycler starts processing: COLLECTED → RECYCLING.
  router.patch(
    '/submissions/:id/recycle/start',
    authenticate,
    authorize(UserRole.RECYCLER),
    validate({ params: submissionIdSchema }),
    (req, res, next) => {
      controller.startRecycling(req, res).catch(next);
    },
  );

  // Recycler completes processing and records recovery: RECYCLING → RECYCLED.
  router.patch(
    '/submissions/:id/recycle/complete',
    authenticate,
    authorize(UserRole.RECYCLER),
    validate({ params: submissionIdSchema, body: completeRecyclingSchema }),
    (req, res, next) => {
      controller.completeRecycling(req, res).catch(next);
    },
  );

  // Recycler dashboard: active assignments for the authenticated recycler.
  router.get(
    '/recycler/submissions',
    authenticate,
    authorize(UserRole.RECYCLER),
    validate({ query: paginationQuerySchema }),
    (req, res, next) => {
      controller.recyclerDashboard(req, res).catch(next);
    },
  );

  // Recycler history: the authenticated recycler's own completed (RECYCLED)
  // jobs, newest first. Scoped to the caller's own id from the verified
  // access token only — the route takes no recyclerId parameter, so there is
  // no client-suppliable value that could target another recycler's history.
  router.get(
    '/recycler/submissions/history',
    authenticate,
    authorize(UserRole.RECYCLER),
    validate({ query: paginationQuerySchema }),
    (req, res, next) => {
      controller.recyclerHistory(req, res).catch(next);
    },
  );

  // --- Device Intelligence linkage (P10.1) -----------------------------------
  // Cross-references a Submission with intelligence/device_ai's Device
  // record so the Consumer Device Passport can show the real pickup/recycling
  // lifecycle. See docs/engineering/03_ARCHITECTURE.md (two-system split).

  // Collector (or admin override) records the device_id/eco_id for a
  // submission they are handling — mirrors the existing register→confirm→
  // finalize device_ai flow, run against the submission already in hand.
  router.patch(
    '/submissions/:id/device-link',
    authenticate,
    authorize(UserRole.COLLECTOR, UserRole.ADMIN),
    validate({ params: submissionIdSchema, body: linkDeviceSchema }),
    (req, res, next) => {
      controller.linkDevice(req, res).catch(next);
    },
  );

  // Resolves the submission lifecycle for a device_id or eco_id. Two path
  // segments after '/submissions/' so this never collides with
  // '/submissions/:id' above. Open to any authenticated role — the service
  // enforces the same visibility rule as getById().
  router.get(
    '/submissions/by-device/:identifier',
    authenticate,
    validate({ params: deviceIdentifierParamSchema }),
    (req, res, next) => {
      controller.getByDevice(req, res).catch(next);
    },
  );

  return router;
}
