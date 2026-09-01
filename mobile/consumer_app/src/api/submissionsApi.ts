import { apiClient } from './client';
import type { CreateSubmissionInput, PublicSubmission } from '../types/submission';

/** Real backend routes — backend/src/modules/submission/submission.routes.ts. */
export const submissionsApi = {
  /** POST /submissions is CONSUMER-only — reporting e-waste for pickup. */
  create(input: CreateSubmissionInput): Promise<PublicSubmission> {
    return apiClient<PublicSubmission>('/submissions', { method: 'POST', body: input });
  },
  /** The caller's own submissions (no role guard — GET /submissions returns the caller's own data). */
  list(): Promise<readonly PublicSubmission[]> {
    return apiClient<readonly PublicSubmission[]>('/submissions');
  },
  get(id: string): Promise<PublicSubmission> {
    return apiClient<PublicSubmission>(`/submissions/${id}`);
  },
};
