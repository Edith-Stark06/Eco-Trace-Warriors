/**
 * Recycler API module.
 *
 * Typed wrappers around the recycler workflow endpoints from
 * docs/engineering/05_API.md (backend/src/modules/submission), built on the
 * single shared Axios instance. Each method unwraps the success envelope
 * (`response.data.data`) and returns the resource directly.
 *
 * The recycler operates only on submissions already assigned to them — this
 * module exposes the read-only assignment queue plus the two legal recycling
 * transitions (start → complete). Recycler assignment itself is an
 * Admin/Government concern and is intentionally not exposed here.
 *
 * Completing a recycling job returns the updated submission together with the
 * reward the backend issued. Reward values are authoritative and are never
 * calculated on the frontend.
 */
import { apiClient } from '@/api/axios';
import { unwrap } from '@/api/client';
import type {
  ApiSuccess,
  CompleteRecyclingPayload,
  CompleteRecyclingResult,
  PaginationParams,
  Submission,
} from '@/types';

export const recyclerApi = {
  /**
   * GET /recycler/submissions — the authenticated recycler's active queue
   * (COLLECTED / RECYCLING assigned to them, newest first).
   */
  getAssignments: (params?: PaginationParams): Promise<Submission[]> =>
    unwrap<Submission[]>(
      apiClient.get<ApiSuccess<Submission[]>>('/recycler/submissions', { params }),
    ),

  /** PATCH /submissions/:id/recycle/start — begin processing: COLLECTED → RECYCLING. */
  startRecycling: (id: string): Promise<Submission> =>
    unwrap<Submission>(apiClient.patch<ApiSuccess<Submission>>(`/submissions/${id}/recycle/start`)),

  /**
   * PATCH /submissions/:id/recycle/complete — record the recovery outcome and
   * finalize: RECYCLING → RECYCLED. Returns the updated submission plus the
   * backend-issued reward.
   */
  completeRecycling: (
    id: string,
    body: CompleteRecyclingPayload,
  ): Promise<CompleteRecyclingResult> =>
    unwrap<CompleteRecyclingResult>(
      apiClient.patch<ApiSuccess<CompleteRecyclingResult>>(
        `/submissions/${id}/recycle/complete`,
        body,
      ),
    ),
};
