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
  /** Cross-domain link to intelligence/device_ai's Device record. Null until linked (P10.1). */
  readonly deviceId: string | null;
  readonly ecoId: string | null;
  readonly createdAt: string;
  readonly updatedAt: string;
}

/**
 * Read-only aggregation of the submission lifecycle for a linked device_ai
 * Device — GET /submissions/by-device/:identifier. Deliberately trimmed
 * relative to PublicSubmission: no collector/recycler user ids, address, or
 * imagery, since this view is served to the Consumer's Device Passport.
 * Every field is a real, already-persisted value from the Submission domain
 * (see reward.service.ts for co2Saved/energySaved/landfillDiverted) — never
 * recomputed or fabricated here.
 */
export interface SubmissionLifecycleView {
  readonly submissionId: string;
  readonly status: SubmissionStatus;
  readonly collectorAssigned: boolean;
  readonly pickupAccepted: boolean;
  readonly pickupStarted: boolean;
  readonly collected: boolean;
  readonly recyclingStarted: boolean;
  readonly recycled: boolean;
  readonly pickupStartedAt: string | null;
  readonly recyclingStartedAt: string | null;
  readonly recycledAt: string | null;
  readonly recoveredWeight: number | null;
  readonly co2Saved: number | null;
  readonly energySaved: number | null;
  readonly landfillDiverted: number | null;
}

/** Combined response for recycler completion with reward issuance. */
export interface CompleteRecyclingWithRewardData {
  readonly submission: PublicSubmission;
  readonly reward: RewardSummary;
}

/**
 * One completed job in a recycler's own history — GET
 * /recycler/submissions/history. Deliberately trimmed relative to
 * PublicSubmission (no owner/collector user ids, address, or imagery — this
 * is a recycler-facing processing record, not the full submission) and
 * additive relative to it (carries co2Saved/energySaved/landfillDiverted,
 * which PublicSubmission does not expose). Every field is a real,
 * already-persisted value — the reward module computes and stores the
 * sustainability figures once, at completion time (reward.service.ts); they
 * are never recomputed here.
 */
export interface RecyclerHistoryEntry {
  readonly id: string;
  readonly category: string;
  readonly estimatedWeight: number;
  readonly recoveredWeight: number | null;
  readonly recycledAt: string | null;
  readonly materialRecovery: Prisma.JsonValue | null;
  readonly recyclerNotes: string | null;
  readonly co2Saved: number | null;
  readonly energySaved: number | null;
  readonly landfillDiverted: number | null;
}

export type SubmissionResponse = SuccessResponse<PublicSubmission>;
export type CompleteRecyclingWithRewardResponse = SuccessResponse<CompleteRecyclingWithRewardData>;
export type SubmissionListResponse = SuccessResponse<readonly PublicSubmission[]>;
export type SubmissionLifecycleResponse = SuccessResponse<SubmissionLifecycleView>;
export type RecyclerHistoryResponse = SuccessResponse<readonly RecyclerHistoryEntry[]>;
