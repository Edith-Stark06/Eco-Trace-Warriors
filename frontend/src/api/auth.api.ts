/**
 * Auth API module (placeholders).
 *
 * Typed wrappers around the auth endpoints from docs/engineering/05_API.md.
 * Sprint 9.1 defines the surface only; bodies are intentionally unimplemented.
 */
import { notImplemented } from '@/api/not-implemented';
import type { AuthSession, AuthTokens, User } from '@/types';

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  confirmPassword: string;
  fullName: string;
  phone?: string;
  region?: string;
}

export const authApi = {
  /** POST /auth/login */
  login: (_payload: LoginPayload): Promise<AuthSession> => notImplemented('authApi.login'),

  /** POST /auth/register */
  register: (_payload: RegisterPayload): Promise<AuthSession> => notImplemented('authApi.register'),

  /** POST /auth/refresh */
  refresh: (_refreshToken: string): Promise<AuthTokens> => notImplemented('authApi.refresh'),

  /** POST /auth/logout */
  logout: (_refreshToken: string): Promise<{ loggedOut: boolean }> =>
    notImplemented('authApi.logout'),

  /** GET /auth/me */
  me: (): Promise<User> => notImplemented('authApi.me'),
};
