/**
 * Submission domain types.
 *
 * Mirror the backend contract for the submission module exactly
 * (backend/src/modules/submission/*, docs/engineering/05_API.md). Dates are
 * serialized to ISO strings at the service boundary, so every timestamp is a
 * string here. Keep in sync when the backend contract changes.
 */

/**
 * Submission lifecycle statuses (Prisma `SubmissionStatus`). The consumer
 * lifecycle progresses PENDING → ASSIGNED → ACCEPTED → IN_PROGRESS →
 * COLLECTED → RECYCLING → RECYCLED. COMPLETED and REJECTED are terminal
 * administrative states outside the happy path.
 */
export const SUBMISSION_STATUSES = [
  'PENDING',
  'ASSIGNED',
  'ACCEPTED',
  'IN_PROGRESS',
  'COLLECTED',
  'RECYCLING',
  'RECYCLED',
  'COMPLETED',
  'REJECTED',
] as const;

export type SubmissionStatus = (typeof SUBMISSION_STATUSES)[number];

/**
 * The ordered lifecycle stages shown in the read-only submission timeline.
 * Terminal administrative states (COMPLETED, REJECTED) are intentionally
 * excluded — they are not steps on the recycling path.
 */
export const SUBMISSION_LIFECYCLE: readonly SubmissionStatus[] = [
  'PENDING',
  'ASSIGNED',
  'ACCEPTED',
  'IN_PROGRESS',
  'COLLECTED',
  'RECYCLING',
  'RECYCLED',
] as const;

/**
 * A submission as returned by the backend (`PublicSubmission`). The consumer
 * module reads every field; collector/recycler-only fields are typed but not
 * edited here.
 */
export interface Submission {
  id: string;
  userId: string;
  category: string;
  description: string | null;
  estimatedWeight: number;
  address: string;
  latitude: number;
  longitude: number;
  imageUrls: string[];
  status: SubmissionStatus;
  assignedCollectorId: string | null;
  assignedRecyclerId: string | null;
  pickupScheduledAt: string | null;
  completedAt: string | null;
  processingStartedAt: string | null;
  recycledAt: string | null;
  recyclerNotes: string | null;
  recoveredWeight: number | null;
  materialRecovery: unknown | null;
  createdAt: string;
  updatedAt: string;
}

/**
 * Request body for POST /submissions. Mirrors the backend
 * `createSubmissionSchema`. `imageUrls` is an array of URL strings — the
 * backend does NOT accept file uploads.
 */
export interface CreateSubmissionPayload {
  category: string;
  description?: string;
  estimatedWeight: number;
  address: string;
  latitude: number;
  longitude: number;
  imageUrls?: string[];
}

/**
 * Request body for PATCH /submissions/:id. Every field is optional; the
 * backend requires at least one to be present.
 */
export type UpdateSubmissionPayload = Partial<CreateSubmissionPayload>;
