import { UserRole } from '@prisma/client';
import type { SubmissionStatus } from '@prisma/client';
import { ConflictError, ForbiddenError, NotFoundError } from '@shared/errors';
import type { Logger } from '@shared/logging';
import type { Pagination } from '@shared/pagination';
import type { SubmissionRecord, SubmissionRepository } from './submission.repository';
import type {
  CompleteRecyclingInput,
  CreateSubmissionInput,
  UpdateSubmissionInput,
} from './submission.schemas';
import type { PublicSubmission, CompleteRecyclingWithRewardData } from './submission.types';
import type { RewardService, RewardSummary } from '../rewards/reward.service';

/**
 * The single source of truth for the submission workflow state machine.
 * Every status change flows through validateTransition() — transition rules
 * are never duplicated or checked inline elsewhere.
 *
 *   PENDING → ASSIGNED → ACCEPTED → IN_PROGRESS → COLLECTED   (collector, Phase 6)
 *   COLLECTED → RECYCLING → RECYCLED                          (recycler, Phase 7)
 *
 * Statuses beyond RECYCLED belong to later lifecycle phases and expose no
 * onward transitions here; any move not listed is rejected.
 */
export const allowedTransitions: Readonly<Record<SubmissionStatus, readonly SubmissionStatus[]>> = {
  PENDING: ['ASSIGNED'],
  ASSIGNED: ['ACCEPTED'],
  ACCEPTED: ['IN_PROGRESS'],
  IN_PROGRESS: ['COLLECTED'],
  COLLECTED: ['RECYCLING'],
  RECYCLING: ['RECYCLED'],
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
  readonly rewards: RewardService;
  /** Clock provider — injectable for deterministic tests. Defaults to wall-clock. */
  readonly now?: () => Date;
}

export interface SubmissionService {
  /** Creates a submission owned by the actor. Status is always PENDING. */
  create(actor: SubmissionActor, input: CreateSubmissionInput): Promise<PublicSubmission>;
  /** Lists submissions: an admin sees all; anyone else sees only their own. */
  list(actor: SubmissionActor, pagination?: Pagination): Promise<PublicSubmission[]>;
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
  getCollectorDashboard(
    actor: SubmissionActor,
    pagination?: Pagination,
  ): Promise<PublicSubmission[]>;

  // --- Recycler workflow (Phase 7) ------------------------------------------

  /** Admin/Government assigns a recycler to a collected submission. */
  assignRecycler(actor: SubmissionActor, id: string, recyclerId: string): Promise<PublicSubmission>;
  /** Assigned recycler begins processing: COLLECTED → RECYCLING. */
  startRecycling(actor: SubmissionActor, id: string): Promise<PublicSubmission>;
  /** Assigned recycler records the recovery outcome: RECYCLING → RECYCLED. */
  completeRecycling(
    actor: SubmissionActor,
    id: string,
    input: CompleteRecyclingInput,
  ): Promise<CompleteRecyclingWithRewardData>;
  /** The recycler's active queue: COLLECTED/RECYCLING assigned to them, newest first. */
  getRecyclerDashboard(
    actor: SubmissionActor,
    pagination?: Pagination,
  ): Promise<PublicSubmission[]>;
}

function isAdmin(actor: SubmissionActor): boolean {
  return actor.role === UserRole.ADMIN;
}

/** Roles permitted to assign a collector to a submission. */
function canAssign(actor: SubmissionActor): boolean {
  return actor.role === UserRole.ADMIN || actor.role === UserRole.GOVERNMENT;
}

/**
 * Roles permitted read/audit visibility across every submission, regardless
 * of ownership. Government already has system-wide assignment authority
 * (canAssign) — without this, a government actor could route a submission to
 * a collector/recycler they can never see in `list()`/`getById()`, an
 * authorization gap (write power without matching read visibility) found via
 * live P8.5 audit-trail testing. Deliberately narrower than isAdmin(): it
 * grants read visibility only, not the update/delete override admins get.
 */
function canAudit(actor: SubmissionActor): boolean {
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
    processingStartedAt: record.processingStartedAt?.toISOString() ?? null,
    recycledAt: record.recycledAt?.toISOString() ?? null,
    recyclerNotes: record.recyclerNotes,
    recoveredWeight: record.recoveredWeight,
    materialRecovery: record.materialRecovery,
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
   * Loads a submission for a read-only lookup, visible to its owner or any
   * canAudit() actor (admin or government). Kept distinct from
   * loadAccessible(): update()/delete() must stay admin-only overrides, but
   * getById() is a pure read and should match list()'s audit visibility.
   */
  async function loadForAudit(actor: SubmissionActor, id: string): Promise<SubmissionRecord> {
    const record = await deps.submissions.findById(id);
    if (!record) {
      throw new NotFoundError('Submission not found.');
    }
    if (!canAudit(actor) && record.userId !== actor.userId) {
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

  /**
   * Loads a submission for a recycler workflow action and asserts the actor is
   * the assigned recycler. As with collectors, an unknown id and someone else's
   * submission both surface as NotFound so a recycler cannot probe for
   * submissions that are not theirs (admin override is handled separately).
   */
  async function ensureRecyclerOwnsSubmission(
    actor: SubmissionActor,
    id: string,
  ): Promise<SubmissionRecord> {
    const record = await deps.submissions.findById(id);
    if (!record || record.assignedRecyclerId !== actor.userId) {
      throw new NotFoundError('Submission not found.');
    }
    return record;
  }

  return {
    async create(actor: SubmissionActor, input: CreateSubmissionInput): Promise<PublicSubmission> {
      const record = await deps.submissions.create({ ...input, userId: actor.userId });
      deps.logger.info({ submissionId: record.id, userId: actor.userId }, 'Submission created');
      return toPublicSubmission(record);
    },

    async list(actor: SubmissionActor, pagination?: Pagination): Promise<PublicSubmission[]> {
      const records = canAudit(actor)
        ? await deps.submissions.findAll(pagination)
        : await deps.submissions.findByUser(actor.userId, pagination);
      return records.map(toPublicSubmission);
    },

    async getById(actor: SubmissionActor, id: string): Promise<PublicSubmission> {
      const record = await loadForAudit(actor, id);
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

    async getCollectorDashboard(
      actor: SubmissionActor,
      pagination?: Pagination,
    ): Promise<PublicSubmission[]> {
      const records = await deps.submissions.findCollectorAssignments(actor.userId, pagination);
      return records.map(toPublicSubmission);
    },

    async assignRecycler(
      actor: SubmissionActor,
      id: string,
      recyclerId: string,
    ): Promise<PublicSubmission> {
      // Only Admin/Government may assign a recycler — same rule as collectors.
      if (!canAssign(actor)) {
        throw new ForbiddenError('You are not allowed to assign recyclers.');
      }

      const record = await deps.submissions.findById(id);
      if (!record) {
        throw new NotFoundError('Submission not found.');
      }

      // The assignee must exist and actually be an active recycler.
      const recycler = await deps.submissions.findRecyclerById(recyclerId);
      if (!recycler || recycler.role !== UserRole.RECYCLER || !recycler.isActive) {
        throw new NotFoundError('Recycler not found.');
      }

      // A submission may only be handed to a recycler once it has been collected.
      // Admin may override at any status; Government must follow the strict path.
      if (!isAdmin(actor) && record.status !== 'COLLECTED') {
        throw new ConflictError(`Cannot assign a recycler while status is ${record.status}.`);
      }

      const updated = await deps.submissions.assignRecycler(id, recyclerId);
      deps.logger.info(
        { submissionId: id, recyclerId, actorId: actor.userId },
        'Recycler assigned',
      );
      return toPublicSubmission(updated);
    },

    async startRecycling(actor: SubmissionActor, id: string): Promise<PublicSubmission> {
      const record = await ensureRecyclerOwnsSubmission(actor, id);
      validateTransition(record.status, 'RECYCLING');
      const updated = await deps.submissions.updateRecyclerProcessing(id, now());
      deps.logger.info(
        { submissionId: id, recyclerId: actor.userId, actorId: actor.userId },
        'Recycling started',
      );
      return toPublicSubmission(updated);
    },

    async completeRecycling(
      actor: SubmissionActor,
      id: string,
      input: CompleteRecyclingInput,
    ): Promise<{ submission: PublicSubmission; reward: RewardSummary }> {
      const record = await ensureRecyclerOwnsSubmission(actor, id);
      validateTransition(record.status, 'RECYCLED');
      const updated = await deps.submissions.updateRecyclerCompletion(id, now(), {
        recoveredWeight: input.recoveredWeight,
        recyclerNotes: input.recyclerNotes,
        materialRecovery: input.materialRecovery,
      });
      deps.logger.info(
        { submissionId: id, recyclerId: actor.userId, actorId: actor.userId },
        'Recycling completed',
      );

      // Automatically issue reward for the recycled submission
      deps.logger.info({ submissionId: id }, 'Reward automatically issued for recycled submission');
      const reward = await deps.rewards.issueReward(id);
      deps.logger.info(
        { submissionId: id, rewardId: reward.rewardTransaction.id },
        'Reward issued',
      );

      return { submission: toPublicSubmission(updated), reward };
    },

    async getRecyclerDashboard(
      actor: SubmissionActor,
      pagination?: Pagination,
    ): Promise<PublicSubmission[]> {
      const records = await deps.submissions.findRecyclerAssignments(actor.userId, pagination);
      return records.map(toPublicSubmission);
    },
  };
}
