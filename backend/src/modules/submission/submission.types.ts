import type { Prisma, SubmissionStatus } from '@prisma/client';
import type { SuccessResponse } from '../../types';
import type { RewardSummary } from '../rewards/reward.service';

/**
 * The submission shape returned to clients. Dates are serialized to ISO
 * strings at the service boundary — the raw Date/record never leaves the module.
 */
export interface PublicSubmission {
  readonly id: string;
  readonly userId: string;
  readonly category: string;
  readonly description: string | null;
  readonly estimatedWeight: number;
  readonly address: string;
  readonly latitude: number;
  readonly longitude: number;
  readonly imageUrls: readonly string[];
  readonly status: SubmissionStatus;
  readonly assignedCollectorId: string | null;
  readonly assignedRecyclerId: string | null;
  readonly pickupScheduledAt: string | null;
  readonly completedAt: string | null;
  readonly processingStartedAt: string | null;
  readonly recycledAt: string | null;
  readonly recyclerNotes: string | null;
  readonly recoveredWeight: number | null;
  readonly materialRecovery: Prisma.JsonValue | null;
  readonly createdAt: string;
  readonly updatedAt: string;
}

/** Combined response for recycler completion with reward issuance. */
export interface CompleteRecyclingWithRewardData {
  readonly submission: PublicSubmission;
  readonly reward: RewardSummary;
}

export type SubmissionResponse = SuccessResponse<PublicSubmission>;
export type CompleteRecyclingWithRewardResponse = SuccessResponse<CompleteRecyclingWithRewardData>;
export type SubmissionListResponse = SuccessResponse<readonly PublicSubmission[]>;
