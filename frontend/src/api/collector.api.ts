/**
 * Collector API module.
 *
 * Typed wrappers around the collector workflow endpoints from
 * docs/engineering/05_API.md (backend/src/modules/submission), built on the
 * single shared Axios instance. Each method unwraps the success envelope
 * (`response.data.data`) and returns the resource directly.
 *
 * The collector operates only on submissions already assigned to them — this
 * module exposes the read-only assignment queue plus the three legal status
 * transitions (accept → start → complete). Assignment itself is an
 * Admin/Government concern and is intentionally not exposed here.
 */
import { apiClient } from '@/api/axios';
import { unwrap } from '@/api/client';
import type { ApiSuccess, PaginationParams, Submission } from '@/types';

export const collectorApi = {
  /**
   * GET /collector/submissions — the authenticated collector's active queue
   * (ASSIGNED / ACCEPTED / IN_PROGRESS assigned to them, newest first).
   */
  getAssignments: (params?: PaginationParams): Promise<Submission[]> =>
    unwrap<Submission[]>(
      apiClient.get<ApiSuccess<Submission[]>>('/collector/submissions', { params }),
    ),

  /** PATCH /submissions/:id/accept — accept an assignment: ASSIGNED → ACCEPTED. */
  acceptAssignment: (id: string): Promise<Submission> =>
    unwrap<Submission>(apiClient.patch<ApiSuccess<Submission>>(`/submissions/${id}/accept`)),

  /** PATCH /submissions/:id/start — start the pickup: ACCEPTED → IN_PROGRESS. */
  startPickup: (id: string): Promise<Submission> =>
    unwrap<Submission>(apiClient.patch<ApiSuccess<Submission>>(`/submissions/${id}/start`)),

  /** PATCH /submissions/:id/complete — complete the pickup: IN_PROGRESS → COLLECTED. */
  completePickup: (id: string): Promise<Submission> =>
    unwrap<Submission>(apiClient.patch<ApiSuccess<Submission>>(`/submissions/${id}/complete`)),
};
