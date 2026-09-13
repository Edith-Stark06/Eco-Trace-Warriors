import type { SuccessResponse } from '../../types';
import type { UserRole } from '@prisma/client';

/** Lightweight user projection returned by GET /users?role=. */
export interface UserListItem {
  readonly id: string;
  readonly fullName: string;
  readonly email: string;
  readonly region: string | null;
  readonly role: UserRole;
}

export type UserListResponse = SuccessResponse<UserListItem[]>;

/** The created user's public projection — never includes passwordHash. */
export interface CreatedUser {
  readonly id: string;
  readonly email: string;
  readonly role: UserRole;
  readonly createdAt: string;
}

/**
 * Result of POST /users. `generatedPassword` is plaintext and exists only in
 * this one response — it is never persisted, logged, or returned again.
 */
export interface CreateUserResult {
  readonly user: CreatedUser;
  readonly generatedPassword: string;
}

export type CreateUserResponse = SuccessResponse<CreateUserResult>;
