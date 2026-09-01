/** Mirrors backend/src/modules/submission/submission.types.ts. */
export type SubmissionStatus =
  | 'PENDING'
  | 'ASSIGNED'
  | 'ACCEPTED'
  | 'IN_PROGRESS'
  | 'COLLECTED'
  | 'RECYCLING'
  | 'RECYCLED'
  | 'COMPLETED'
  | 'REJECTED';

export interface PublicSubmission {
  id: string;
  userId: string;
  category: string;
  description: string | null;
  estimatedWeight: number;
  address: string;
  latitude: number;
  longitude: number;
  imageUrls: readonly string[];
  status: SubmissionStatus;
  assignedCollectorId: string | null;
  assignedRecyclerId: string | null;
  pickupScheduledAt: string | null;
  completedAt: string | null;
  processingStartedAt: string | null;
  recycledAt: string | null;
  recyclerNotes: string | null;
  recoveredWeight: number | null;
  materialRecovery: unknown;
  createdAt: string;
  updatedAt: string;
}

/**
 * Ordered lifecycle states this app's Collector role progresses a
 * submission through (P5's device lifecycle is a separate, richer
 * state machine on the device_ai side; this is the coarser Submission
 * record lifecycle owned by the Node backend — see docs/engineering/03_ARCHITECTURE.md
 * on the two-system split).
 */
export const COLLECTOR_LIFECYCLE_ORDER: readonly SubmissionStatus[] = [
  'PENDING',
  'ASSIGNED',
  'ACCEPTED',
  'IN_PROGRESS',
  'COLLECTED',
];
