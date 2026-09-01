import { apiClient } from './client';
import type { PublicSubmission } from '../types/submission';

/**
 * Real backend routes — backend/src/modules/submission/submission.routes.ts.
 * No `create` here: POST /submissions requires the CONSUMER role, not
 * COLLECTOR — a Collector only acts on submissions already assigned to
 * them by an Admin/Government.
 */
export const submissionsApi = {
  /** Submissions assigned to the signed-in collector. */
  listForCollector(): Promise<readonly PublicSubmission[]> {
    return apiClient<readonly PublicSubmission[]>('/collector/submissions');
  },
  get(id: string): Promise<PublicSubmission> {
    return apiClient<PublicSubmission>(`/submissions/${id}`);
  },
  accept(id: string): Promise<PublicSubmission> {
    return apiClient<PublicSubmission>(`/submissions/${id}/accept`, { method: 'PATCH' });
  },
  start(id: string): Promise<PublicSubmission> {
    return apiClient<PublicSubmission>(`/submissions/${id}/start`, { method: 'PATCH' });
  },
  complete(id: string): Promise<PublicSubmission> {
    return apiClient<PublicSubmission>(`/submissions/${id}/complete`, { method: 'PATCH' });
  },
};
