import { UserRole } from '@prisma/client';
import { ForbiddenError, NotFoundError } from '@shared/errors';
import type { Logger } from '@shared/logging';
import type { SubmissionRecord, SubmissionRepository } from './submission.repository';
import type { CreateSubmissionInput, UpdateSubmissionInput } from './submission.schemas';
import type { PublicSubmission } from './submission.types';

/** The authenticated principal acting on submissions (from req.user). */
export interface SubmissionActor {
  readonly userId: string;
  readonly role: UserRole;
}

/** Dependencies injected into the submission service. */
export interface SubmissionServiceDeps {
  readonly submissions: SubmissionRepository;
  readonly logger: Logger;
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
}

function isAdmin(actor: SubmissionActor): boolean {
  return actor.role === UserRole.ADMIN;
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
  };
}
