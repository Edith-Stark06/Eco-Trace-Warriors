import type { Prisma, SubmissionStatus } from '@prisma/client';
import type { SuccessResponse } from '../../types';

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

export type SubmissionResponse = SuccessResponse<PublicSubmission>;
export type SubmissionListResponse = SuccessResponse<readonly PublicSubmission[]>;
