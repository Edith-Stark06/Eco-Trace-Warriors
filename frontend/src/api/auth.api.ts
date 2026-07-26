/**
 * Auth API module.
 *
 * Typed wrappers around the auth endpoints from docs/engineering/05_API.md,
 * built on the single shared Axios instance. Each method unwraps the success
 * envelope (`response.data.data`) and returns the resource directly.
 */
import { apiClient } from '@/api/axios';
import { unwrap } from '@/api/client';
import type { ApiSuccess, AuthResult, AuthTokens, LoginCredentials, PublicUser } from '@/types';

export const authApi = {
  /** POST /auth/login — exchange credentials for a user + token pair. */
  login: (credentials: LoginCredentials): Promise<AuthResult> =>
    unwrap<AuthResult>(apiClient.post<ApiSuccess<AuthResult>>('/auth/login', credentials)),

  /**
   * POST /auth/refresh — rotate the token pair.
   *
   * Flagged with `skipAuthRefresh` so a 401 from the refresh endpoint itself
   * is not intercepted and retried (which would recurse infinitely).
   */
  refresh: (refreshToken: string): Promise<AuthTokens> =>
    unwrap<AuthTokens>(
      apiClient.post<ApiSuccess<AuthTokens>>(
        '/auth/refresh',
        { refreshToken },
        { skipAuthRefresh: true },
      ),
    ),

  /** POST /auth/logout — revoke a refresh token (idempotent server-side). */
  logout: (refreshToken: string): Promise<{ loggedOut: boolean }> =>
    unwrap<{ loggedOut: boolean }>(
      apiClient.post<ApiSuccess<{ loggedOut: boolean }>>('/auth/logout', { refreshToken }),
    ),

  /** GET /auth/me — the current authenticated user (server is source of truth). */
  getCurrentUser: (): Promise<PublicUser> =>
    unwrap<PublicUser>(apiClient.get<ApiSuccess<PublicUser>>('/auth/me')),
};
