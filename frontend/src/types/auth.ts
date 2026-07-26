/**
 * Authentication & user domain types.
 *
 * Mirrors the user shape and role enum from docs/engineering/04_DATABASE.md
 * and 05_API.md. This sprint defines the types only; no auth logic yet.
 */

/** Server-side roles (docs/engineering/04_DATABASE.md → UserRole). */
export const USER_ROLES = ['CONSUMER', 'COLLECTOR', 'RECYCLER', 'GOVERNMENT', 'ADMIN'] as const;

export type UserRole = (typeof USER_ROLES)[number];

export interface User {
  id: string;
  fullName: string;
  email: string;
  phone: string | null;
  region: string | null;
  role: UserRole;
  emailVerified: boolean;
  createdAt: string;
}

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
}

/** Payload returned by login/register (docs/engineering/05_API.md → Auth). */
export interface AuthSession extends AuthTokens {
  user: User;
}

/** Shape exposed by the auth context to consumers. */
export interface AuthState {
  user: User | null;
  status: 'idle' | 'loading' | 'authenticated' | 'unauthenticated';
  isAuthenticated: boolean;
}
