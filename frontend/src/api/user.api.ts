/**
 * User API module (placeholders).
 *
 * Typed wrappers around the current-user/profile endpoints from
 * docs/engineering/05_API.md. Sprint 9.1 defines the surface only.
 */
import { notImplemented } from '@/api/not-implemented';
import type { User } from '@/types';

export const userApi = {
  /** GET /auth/me — current authenticated user profile */
  getProfile: (): Promise<User> => notImplemented('userApi.getProfile'),

  /** PATCH /users/me — update the current user's profile */
  updateProfile: (_payload: Partial<User>): Promise<User> =>
    notImplemented('userApi.updateProfile'),
};
