import type { Request } from 'express';
import type { UserRole } from '@prisma/client';
import { UnauthorizedError } from '@shared/errors';
import type { SuccessResponse } from '../../types';

/** The only user shape that ever leaves the auth module. Never carries the password hash. */
export interface PublicUser {
  readonly id: string;
  readonly fullName: string;
  readonly email: string;
  readonly phone: string | null;
  readonly region: string | null;
  readonly role: UserRole;
  readonly emailVerified: boolean;
  readonly createdAt: string;
}

/** Access + refresh token pair issued on register/login/refresh. */
export interface AuthTokens {
  readonly accessToken: string;
  readonly refreshToken: string;
}

/** Result of register and login: the user plus a fresh token pair. */
export interface AuthResult extends AuthTokens {
  readonly user: PublicUser;
}

/** Payload returned by POST /auth/logout. */
export interface LogoutData {
  readonly loggedOut: true;
}

export type AuthResponse = SuccessResponse<AuthResult>;
export type TokensResponse = SuccessResponse<AuthTokens>;
export type MeResponse = SuccessResponse<PublicUser>;
export type LogoutResponse = SuccessResponse<LogoutData>;

/** The authenticated principal attached to a request by the authenticate middleware. */
export interface AuthContext {
  readonly userId: string;
  readonly role: UserRole;
}

/**
 * Narrows `req.user` for controllers on protected routes.
 * Throws UnauthorizedError if the authenticate middleware did not run —
 * a defensive guard that keeps controllers free of non-null assertions.
 */
export function getAuthContext(req: Request): AuthContext {
  if (!req.user) {
    throw new UnauthorizedError('Authentication is required.');
  }
  return req.user;
}
