/**
 * Admin API module.
 *
 * Typed wrappers around the backend endpoints that an ADMIN principal may call,
 * built on the single shared Axios instance. Each method unwraps the success
 * envelope (`response.data.data`) and returns the resource directly.
 *
 * Implemented backend surface (verified from backend/src/modules):
 *   GET  /submissions          — admin sees ALL submissions (service: isAdmin → findAll)
 *   POST /rewards/issue/:id    — manual reward issuance (ADMIN only; status must be RECYCLED)
 *
 * No user-listing, no collector/recycler lookup, and no analytics endpoints exist
 * on this backend instance. Those sections render informational unavailable states.
 */
import { apiClient } from '@/api/axios';
import { unwrap } from '@/api/client';
import type { ApiSuccess, PaginationParams, RewardSummary, Submission } from '@/types';

export const adminApi = {
  /**
   * GET /submissions — when called by an ADMIN the service returns ALL
   * submissions across every user (backend: isAdmin ? findAll : findByUser).
   * Supports offset-based pagination via `?limit&offset`.
   */
  listAllSubmissions: (params?: PaginationParams): Promise<Submission[]> =>
    unwrap<Submission[]>(apiClient.get<ApiSuccess<Submission[]>>('/submissions', { params })),

  /**
   * POST /rewards/issue/:submissionId — manually issue a reward for a RECYCLED
   * submission that has not yet received one. ADMIN only; the backend validates
   * status and idempotency. Returns the full RewardSummary on success.
   */
  issueReward: (submissionId: string): Promise<RewardSummary> =>
    unwrap<RewardSummary>(
      apiClient.post<ApiSuccess<RewardSummary>>(`/rewards/issue/${submissionId}`),
    ),
};
