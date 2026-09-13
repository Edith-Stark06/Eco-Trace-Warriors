import { apiClient } from './client';
import type {
  CreateSubmissionInput,
  PublicSubmission,
  SubmissionLifecycleView,
} from '../types/submission';

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
  /**
   * The Submission lifecycle for a device_ai device_id/eco_id (P10.1) — the
   * Device Passport's "Collection & Recycling" section. A 404 means no
   * submission has been linked to this device yet, a legitimate state the
   * screen renders as "Collection information unavailable", not an error.
   */
  getByDevice(identifier: string): Promise<SubmissionLifecycleView> {
    return apiClient<SubmissionLifecycleView>(`/submissions/by-device/${identifier}`);
  },
};
