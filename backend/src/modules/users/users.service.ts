import type { UserRole } from '@prisma/client';
import type { UserRecord, UserRepository } from '@modules/auth';
import type { UserListItem } from './users.types';

/** Dependencies injected into the users service. */
export interface UsersServiceDeps {
  readonly users: UserRepository;
}

export interface UsersService {
  /** Active users with the given role, mapped to the lightweight list DTO. */
  listByRole(role: UserRole): Promise<UserListItem[]>;
}

/** Maps a full user record to the lightweight list item (no secrets, no PII beyond contact). */
function toListItem(user: UserRecord): UserListItem {
  return {
    id: user.id,
    fullName: user.fullName,
    email: user.email,
    region: user.region,
    role: user.role.name,
  };
}

/**
 * Creates the users service. Reuses the auth module's UserRepository — the user
 * table has a single owner (auth), so we depend on its interface rather than
 * introducing a second Prisma access point (keeps modules decoupled).
 */
export function createUsersService(deps: UsersServiceDeps): UsersService {
  return {
    async listByRole(role: UserRole): Promise<UserListItem[]> {
      const records = await deps.users.findByRole(role);
      return records.map(toListItem);
    },
  };
}
