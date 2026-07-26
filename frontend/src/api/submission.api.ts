/**
 * Submission API module.
 *
 * Typed wrappers around the submission endpoints from docs/engineering/05_API.md
 * (backend/src/modules/submission), built on the single shared Axios instance.
 * Each method unwraps the success envelope (`response.data.data`) and returns
 * the resource directly. The consumer module uses only the CRUD endpoints;
 * collector/recycler transition endpoints are intentionally not exposed here.
 */
import { apiClient } from '@/api/axios';
import { unwrap } from '@/api/client';
import type {
  ApiSuccess,
  CreateSubmissionPayload,
  PaginationParams,
  Submission,
  UpdateSubmissionPayload,
} from '@/types';

export const submissionApi = {
  /** GET /submissions — the caller's own submissions (server scopes by owner). */
  list: (params?: PaginationParams): Promise<Submission[]> =>
    unwrap<Submission[]>(apiClient.get<ApiSuccess<Submission[]>>('/submissions', { params })),

  /** GET /submissions/:id — a single submission the caller may view. */
  getById: (id: string): Promise<Submission> =>
    unwrap<Submission>(apiClient.get<ApiSuccess<Submission>>(`/submissions/${id}`)),

  /** POST /submissions — create a new e-waste submission (consumer only). */
  create: (payload: CreateSubmissionPayload): Promise<Submission> =>
    unwrap<Submission>(apiClient.post<ApiSuccess<Submission>>('/submissions', payload)),

  /** PATCH /submissions/:id — update a submission (owner, while PENDING). */
  update: (id: string, payload: UpdateSubmissionPayload): Promise<Submission> =>
    unwrap<Submission>(apiClient.patch<ApiSuccess<Submission>>(`/submissions/${id}`, payload)),

  /** DELETE /submissions/:id — remove a submission (owner, while PENDING). Returns 204. */
  remove: async (id: string): Promise<void> => {
    await apiClient.delete(`/submissions/${id}`);
  },
};
