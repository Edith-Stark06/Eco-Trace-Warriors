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

/** Body for POST /submissions — mirrors submission.schemas.ts createSubmissionSchema. CONSUMER-only. */
export interface CreateSubmissionInput {
  category: string;
  description?: string;
  estimatedWeight: number;
  address: string;
  latitude: number;
  longitude: number;
  imageUrls?: string[];
}
