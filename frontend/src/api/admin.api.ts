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
 *   GET  /users?role=          — active users by role (COLLECTOR or RECYCLER); ADMIN+GOVERNMENT
 *   POST /users                — provision a COLLECTOR/RECYCLER/GOVERNMENT account (ADMIN only)
 *   PATCH /submissions/:id/assign          — assign collector (ADMIN+GOVERNMENT)
 *   PATCH /submissions/:id/assign-recycler — assign recycler (ADMIN+GOVERNMENT)
 */
import { apiClient } from '@/api/axios';
import { unwrap } from '@/api/client';
import type {
  ApiSuccess,
  CreatableUserRole,
  CreateUserResult,
  PaginationParams,
  PublicUser,
  RewardSummary,
  Submission,
} from '@/types';

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

  /**
   * GET /users?role=COLLECTOR|RECYCLER — active users eligible for assignment.
   * Protected by ADMIN and GOVERNMENT roles on the backend.
   */
  listUsersByRole: (role: 'COLLECTOR' | 'RECYCLER'): Promise<PublicUser[]> =>
    unwrap<PublicUser[]>(apiClient.get<ApiSuccess<PublicUser[]>>('/users', { params: { role } })),

  /**
   * PATCH /submissions/:id/assign — assign a collector to a PENDING submission.
   * Moves status to ASSIGNED. ADMIN+GOVERNMENT only.
   */
  assignCollector: (submissionId: string, collectorId: string): Promise<Submission> =>
    unwrap<Submission>(
      apiClient.patch<ApiSuccess<Submission>>(`/submissions/${submissionId}/assign`, {
        collectorId,
      }),
    ),

  /**
   * PATCH /submissions/:id/assign-recycler — assign a recycler to a COLLECTED submission.
   * ADMIN+GOVERNMENT only.
   */
  assignRecycler: (submissionId: string, recyclerId: string): Promise<Submission> =>
    unwrap<Submission>(
      apiClient.patch<ApiSuccess<Submission>>(`/submissions/${submissionId}/assign-recycler`, {
        recyclerId,
      }),
    ),

  /**
   * POST /users — provisions a COLLECTOR/RECYCLER/GOVERNMENT account. ADMIN
   * only (GOVERNMENT gets 403, unlike the GET /users directory lookup). The
   * backend generates the password server-side; it is returned in plaintext
   * exactly once, in this response, and never sent again.
   */
  createUser: (email: string, role: CreatableUserRole): Promise<CreateUserResult> =>
    unwrap<CreateUserResult>(
      apiClient.post<ApiSuccess<CreateUserResult>>('/users', { email, role }),
    ),
};
