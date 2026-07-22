import { UserRole } from '@prisma/client';
import type { SubmissionStatus } from '@prisma/client';
import { ConflictError, ForbiddenError, NotFoundError } from '@shared/errors';
import type { Logger } from '@shared/logging';
import type { SubmissionRecord, SubmissionRepository } from './submission.repository';
import type { CreateSubmissionInput, UpdateSubmissionInput } from './submission.schemas';
import type { PublicSubmission } from './submission.types';

/**
 * The single source of truth for the collector workflow state machine.
 * Every status change flows through validateTransition() — transition rules
 * are never duplicated or checked inline elsewhere.
 *
 *   PENDING → ASSIGNED → ACCEPTED → IN_PROGRESS → COLLECTED
 *
 * Statuses beyond COLLECTED belong to later lifecycle phases and expose no
 * onward transitions here; any move not listed is rejected.
 */
export const allowedTransitions: Readonly<Record<SubmissionStatus, readonly SubmissionStatus[]>> = {
  PENDING: ['ASSIGNED'],
  ASSIGNED: ['ACCEPTED'],
  ACCEPTED: ['IN_PROGRESS'],
  IN_PROGRESS: ['COLLECTED'],
  COLLECTED: [],
  RECYCLED: [],
  COMPLETED: [],
  REJECTED: [],
};

/** The authenticated principal acting on submissions (from req.user). */
export interface SubmissionActor {
  readonly userId: string;
  readonly role: UserRole;
}

/** Dependencies injected into the submission service. */
export interface SubmissionServiceDeps {
  readonly submissions: SubmissionRepository;
  readonly logger: Logger;
  /** Clock provider — injectable for deterministic tests. Defaults to wall-clock. */
  readonly now?: () => Date;
}

export interface SubmissionService {
  /** Creates a submission owned by the actor. Status is always PENDING. */
  create(actor: SubmissionActor, input: CreateSubmissionInput): Promise<PublicSubmission>;
  /** Lists submissions: an admin sees all; anyone else sees only their own. */
  list(actor: SubmissionActor): Promise<PublicSubmission[]>;
  /** Returns one submission if the actor owns it or is an admin. */
  getById(actor: SubmissionActor, id: string): Promise<PublicSubmission>;
  /** Updates a submission. Owner only while PENDING; admin always. */
  update(
    actor: SubmissionActor,
    id: string,
    input: UpdateSubmissionInput,
  ): Promise<PublicSubmission>;
  /** Deletes a submission. Owner only while PENDING; admin always. */
  delete(actor: SubmissionActor, id: string): Promise<void>;

  // --- Collector workflow (Phase 6) -----------------------------------------

  /** Admin/Government assigns a collector: PENDING → ASSIGNED. */
  assignCollector(
    actor: SubmissionActor,
    id: string,
    collectorId: string,
  ): Promise<PublicSubmission>;
  /** Assigned collector accepts the job: ASSIGNED → ACCEPTED. */
  acceptAssignment(actor: SubmissionActor, id: string): Promise<PublicSubmission>;
  /** Assigned collector starts the pickup: ACCEPTED → IN_PROGRESS. */
  startPickup(actor: SubmissionActor, id: string): Promise<PublicSubmission>;
  /** Assigned collector completes the pickup: IN_PROGRESS → COLLECTED. */
  completePickup(actor: SubmissionActor, id: string): Promise<PublicSubmission>;
  /** The collector's active queue: ASSIGNED/ACCEPTED/IN_PROGRESS assigned to them, newest first. */
  getCollectorDashboard(actor: SubmissionActor): Promise<PublicSubmission[]>;
}

function isAdmin(actor: SubmissionActor): boolean {
  return actor.role === UserRole.ADMIN;
}

/** Roles permitted to assign a collector to a submission. */
function canAssign(actor: SubmissionActor): boolean {
  return actor.role === UserRole.ADMIN || actor.role === UserRole.GOVERNMENT;
}

/**
 * Centralized transition guard. Throws ConflictError when `to` is not a legal
 * successor of `from` per allowedTransitions. The one place a transition is
 * ever judged — callers never compare statuses themselves.
 */
export function validateTransition(from: SubmissionStatus, to: SubmissionStatus): void {
  if (!allowedTransitions[from].includes(to)) {
    throw new ConflictError(`Cannot change status from ${from} to ${to}.`);
  }
}

function toPublicSubmission(record: SubmissionRecord): PublicSubmission {
  return {
    id: record.id,
    userId: record.userId,
    category: record.category,
    description: record.description,
    estimatedWeight: record.estimatedWeight,
    address: record.address,
    latitude: record.latitude,
    longitude: record.longitude,
    imageUrls: record.imageUrls,
    status: record.status,
    assignedCollectorId: record.assignedCollectorId,
    assignedRecyclerId: record.assignedRecyclerId,
    pickupScheduledAt: record.pickupScheduledAt?.toISOString() ?? null,
    completedAt: record.completedAt?.toISOString() ?? null,
    createdAt: record.createdAt.toISOString(),
    updatedAt: record.updatedAt.toISOString(),
  };
}

/** Creates the submission service. Framework-agnostic and fully unit-testable. */
export function createSubmissionService(deps: SubmissionServiceDeps): SubmissionService {
  const now = deps.now ?? ((): Date => new Date());

  /**
   * Loads a submission the actor is allowed to see, or throws.
   * NotFound is returned both for missing rows and for rows the actor may not
   * access — a non-owner must not learn that someone else's submission exists.
   */
  async function loadAccessible(actor: SubmissionActor, id: string): Promise<SubmissionRecord> {
    const record = await deps.submissions.findById(id);
    if (!record) {
      throw new NotFoundError('Submission not found.');
    }
    if (!isAdmin(actor) && record.userId !== actor.userId) {
      throw new NotFoundError('Submission not found.');
    }
    return record;
  }

  /**
   * Loads a submission for a collector workflow action and asserts the actor is
   * the assigned collector. A collector must not learn about submissions that
   * are not theirs, so an unknown id and someone else's submission both surface
   * as NotFound rather than Forbidden.
   */
  async function ensureCollectorOwnsSubmission(
    actor: SubmissionActor,
    id: string,
  ): Promise<SubmissionRecord> {
    const record = await deps.submissions.findById(id);
    if (!record || record.assignedCollectorId !== actor.userId) {
      throw new NotFoundError('Submission not found.');
    }
    return record;
  }

  /**
   * Runs one collector-driven status transition end to end: verify ownership,
   * validate the transition centrally, persist, and log. Keeps the four
   * workflow endpoints free of duplicated guard logic.
   */
  async function advanceAsCollector(
    actor: SubmissionActor,
    id: string,
    to: SubmissionStatus,
    event: string,
  ): Promise<PublicSubmission> {
    const record = await ensureCollectorOwnsSubmission(actor, id);
    validateTransition(record.status, to);
    const updated = await deps.submissions.updateStatus(id, to);
    deps.logger.info({ submissionId: id, collectorId: actor.userId, actorId: actor.userId }, event);
    return toPublicSubmission(updated);
  }

  return {
    async create(actor: SubmissionActor, input: CreateSubmissionInput): Promise<PublicSubmission> {
      const record = await deps.submissions.create({ ...input, userId: actor.userId });
      deps.logger.info({ submissionId: record.id, userId: actor.userId }, 'Submission created');
      return toPublicSubmission(record);
    },

    async list(actor: SubmissionActor): Promise<PublicSubmission[]> {
      const records = isAdmin(actor)
        ? await deps.submissions.findAll()
        : await deps.submissions.findByUser(actor.userId);
      return records.map(toPublicSubmission);
    },

    async getById(actor: SubmissionActor, id: string): Promise<PublicSubmission> {
      const record = await loadAccessible(actor, id);
      return toPublicSubmission(record);
    },

    async update(
      actor: SubmissionActor,
      id: string,
      input: UpdateSubmissionInput,
    ): Promise<PublicSubmission> {
      const record = await loadAccessible(actor, id);

      // Owners may only edit before the submission enters the assignment flow.
      if (!isAdmin(actor) && record.status !== 'PENDING') {
        throw new ForbiddenError('Submission can no longer be edited.');
      }

      const updated = await deps.submissions.update(id, input);
      deps.logger.info({ submissionId: id, userId: actor.userId }, 'Submission updated');
      return toPublicSubmission(updated);
    },

    async delete(actor: SubmissionActor, id: string): Promise<void> {
      const record = await loadAccessible(actor, id);

      if (!isAdmin(actor) && record.status !== 'PENDING') {
        throw new ForbiddenError('Submission can no longer be deleted.');
      }

      await deps.submissions.delete(id);
      deps.logger.info({ submissionId: id, userId: actor.userId }, 'Submission deleted');
    },

    async assignCollector(
      actor: SubmissionActor,
      id: string,
      collectorId: string,
    ): Promise<PublicSubmission> {
      // Only Admin/Government may assign; a collector can never assign anyone
      // (including themselves). Route guards enforce this too — defence in depth.
      if (!canAssign(actor)) {
        throw new ForbiddenError('You are not allowed to assign collectors.');
      }

      const record = await deps.submissions.findById(id);
      if (!record) {
        throw new NotFoundError('Submission not found.');
      }

      // The assignee must exist and actually be an active collector.
      const collector = await deps.submissions.findCollectorById(collectorId);
      if (!collector || collector.role !== UserRole.COLLECTOR || !collector.isActive) {
        throw new NotFoundError('Collector not found.');
      }

      // Admin may re-assign at any point (override); Government follows the
      // strict state machine (PENDING → ASSIGNED only).
      if (!isAdmin(actor)) {
        validateTransition(record.status, 'ASSIGNED');
      }

      const updated = await deps.submissions.assignCollector(id, collectorId);
      deps.logger.info(
        { submissionId: id, collectorId, actorId: actor.userId },
        'Collector assigned',
      );
      return toPublicSubmission(updated);
    },

    async acceptAssignment(actor: SubmissionActor, id: string): Promise<PublicSubmission> {
      return advanceAsCollector(actor, id, 'ACCEPTED', 'Assignment accepted');
    },

    async startPickup(actor: SubmissionActor, id: string): Promise<PublicSubmission> {
      const record = await ensureCollectorOwnsSubmission(actor, id);
      validateTransition(record.status, 'IN_PROGRESS');
      await deps.submissions.updateStatus(id, 'IN_PROGRESS');
      // Stamp when the pickup actually began; the clock is injectable for tests.
      const updated = await deps.submissions.updatePickupSchedule(id, now());
      deps.logger.info(
        { submissionId: id, collectorId: actor.userId, actorId: actor.userId },
        'Pickup started',
      );
      return toPublicSubmission(updated);
    },

    async completePickup(actor: SubmissionActor, id: string): Promise<PublicSubmission> {
      return advanceAsCollector(actor, id, 'COLLECTED', 'Pickup completed');
    },

    async getCollectorDashboard(actor: SubmissionActor): Promise<PublicSubmission[]> {
      const records = await deps.submissions.findCollectorAssignments(actor.userId);
      return records.map(toPublicSubmission);
    },
  };
}
