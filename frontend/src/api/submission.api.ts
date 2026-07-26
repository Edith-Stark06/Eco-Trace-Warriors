/**
 * Submission API module (placeholders).
 *
 * Typed wrappers around the submission endpoints from
 * docs/engineering/05_API.md. Sprint 9.1 defines the surface only.
 */
import { notImplemented } from '@/api/not-implemented';
import type { PaginationParams } from '@/types';

export const submissionApi = {
  /** GET /submissions */
  list: (_params?: PaginationParams): Promise<unknown[]> => notImplemented('submissionApi.list'),

  /** GET /submissions/{id} */
  getById: (_id: string): Promise<unknown> => notImplemented('submissionApi.getById'),

  /** POST /submissions */
  create: (_payload: unknown): Promise<unknown> => notImplemented('submissionApi.create'),

  /** PATCH /submissions/{id} */
  update: (_id: string, _payload: unknown): Promise<unknown> =>
    notImplemented('submissionApi.update'),

  /** DELETE /submissions/{id} */
  remove: (_id: string): Promise<void> => notImplemented('submissionApi.remove'),
};
