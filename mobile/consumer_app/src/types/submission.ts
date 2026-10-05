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

/**
 * Mirrors backend/src/modules/submission/submission.types.ts
 * SubmissionLifecycleView — the Submission-domain view surfaced on the
 * Device Passport's "Collection & Recycling" section (P10.1).
 * GET /submissions/by-device/:identifier. Every field is a real,
 * already-persisted Submission value; a missing value stays `null`
 * rather than being guessed.
 */
export interface SubmissionLifecycleView {
  submissionId: string;
  status: SubmissionStatus;
  collectorAssigned: boolean;
  pickupAccepted: boolean;
  pickupStarted: boolean;
  collected: boolean;
  recyclingStarted: boolean;
  recycled: boolean;
  pickupStartedAt: string | null;
  recyclingStartedAt: string | null;
  recycledAt: string | null;
  recoveredWeight: number | null;
  co2Saved: number | null;
  energySaved: number | null;
  landfillDiverted: number | null;
}
