/** Mirrors backend/src/modules/auth/auth.types.ts. */
export type UserRole = 'ADMIN' | 'GOVERNMENT' | 'RECYCLER' | 'COLLECTOR' | 'CONSUMER';

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

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
}

export interface AuthResult extends AuthTokens {
  user: PublicUser;
}

export interface LoginInput {
  email: string;
  password: string;
}
