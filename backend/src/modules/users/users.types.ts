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
