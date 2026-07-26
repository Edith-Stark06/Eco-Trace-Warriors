/**
 * Authentication & user domain types.
 *
 * Mirrors the user shape and role enum from docs/engineering/04_DATABASE.md
 * and 05_API.md.
 */

/** Server-side roles (docs/engineering/04_DATABASE.md → UserRole). */
export const USER_ROLES = ['CONSUMER', 'COLLECTOR', 'RECYCLER', 'GOVERNMENT', 'ADMIN'] as const;

export type UserRole = (typeof USER_ROLES)[number];

/**
 * The public-safe user projection returned by the backend (never includes
 * secrets such as the password hash). Canonical user type across the app.
 */
export interface PublicUser {
  id: string;
  fullName: string;
  email: string;
  phone: string | null;
  region: string | null;
  role: UserRole;
  emailVerified: boolean;
  createdAt: string;
}

/** Backwards-compatible alias; prefer {@link PublicUser}. */
export type User = PublicUser;

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
}

/** Payload returned by POST /auth/login (docs/engineering/05_API.md → Auth). */
export interface AuthResult extends AuthTokens {
  user: PublicUser;
}

/** Backwards-compatible alias; prefer {@link AuthResult}. */
export type AuthSession = AuthResult;

/** Credentials accepted by the login form and POST /auth/login. */
export interface LoginCredentials {
  email: string;
  password: string;
}

export type AuthStatus = 'idle' | 'loading' | 'authenticated' | 'unauthenticated';

/** Reactive auth state exposed to the app. */
export interface AuthState {
  user: PublicUser | null;
  status: AuthStatus;
  isAuthenticated: boolean;
  isLoading: boolean;
}
