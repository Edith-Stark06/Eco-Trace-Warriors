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

/**
 * Roles an ADMIN may provision via POST /users. ADMIN and CONSUMER are
 * intentionally excluded — ADMIN accounts are not self-service, and CONSUMER
 * accounts are created only via public registration.
 */
export const CREATABLE_USER_ROLES = ['COLLECTOR', 'RECYCLER', 'GOVERNMENT'] as const;

export type CreatableUserRole = (typeof CREATABLE_USER_ROLES)[number];

/** The created user's public projection returned by POST /users. */
export interface CreatedUser {
  id: string;
  email: string;
  role: CreatableUserRole;
  createdAt: string;
}

/**
 * Result of POST /users. `generatedPassword` is plaintext and exists only in
 * this one response — never persisted, cached, or shown again after this.
 */
export interface CreateUserResult {
  user: CreatedUser;
  generatedPassword: string;
}
