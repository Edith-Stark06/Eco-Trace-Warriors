import { randomUUID } from 'node:crypto';
import { UserRole } from '@prisma/client';
import type {
  CreateUserInput,
  RefreshTokenRepository,
  StoredRefreshToken,
  UserRecord,
  UserRepository,
} from '@modules/auth';

/**
 * In-memory implementations of the auth repositories for integration tests.
 * Lets the full HTTP stack run through Supertest without a database.
 * The CONSUMER role is pre-seeded to mirror prisma/seed.ts.
 */

export interface InMemoryAuthRepositories {
  readonly users: UserRepository;
  readonly refreshTokens: RefreshTokenRepository;
}

export function createInMemoryAuthRepositories(): InMemoryAuthRepositories {
  const roleIds = new Map<UserRole, string>(
    Object.values(UserRole).map((name) => [name, `role-${name.toLowerCase()}`]),
  );
  const usersById = new Map<string, UserRecord>();
  const tokensByHash = new Map<string, StoredRefreshToken>();

  const users: UserRepository = {
    findByEmail(email: string): Promise<UserRecord | null> {
      const match = [...usersById.values()].find((u) => u.email === email) ?? null;
      return Promise.resolve(match);
    },

    findById(id: string): Promise<UserRecord | null> {
      return Promise.resolve(usersById.get(id) ?? null);
    },

    create(input: CreateUserInput): Promise<UserRecord> {
      const roleName =
        [...roleIds.entries()].find(([, id]) => id === input.roleId)?.[0] ?? UserRole.CONSUMER;
      const user: UserRecord = {
        id: randomUUID(),
        fullName: input.fullName,
        email: input.email,
        passwordHash: input.passwordHash,
        phone: input.phone ?? null,
        region: input.region ?? null,
        emailVerified: false,
        isActive: true,
        role: { name: roleName },
        createdAt: new Date(),
      };
      usersById.set(user.id, user);
      return Promise.resolve(user);
    },

    updateLastLogin(_id: string, _when: Date): Promise<void> {
      return Promise.resolve();
    },

    findRoleId(name: UserRole): Promise<string | null> {
      return Promise.resolve(roleIds.get(name) ?? null);
    },

    findByRole(role: UserRole): Promise<UserRecord[]> {
      const matches = [...usersById.values()]
        .filter((u) => u.isActive && u.role.name === role)
        .sort((a, b) => a.fullName.localeCompare(b.fullName));
      return Promise.resolve(matches);
    },
  };

  const refreshTokens: RefreshTokenRepository = {
    store(input: { tokenHash: string; userId: string; expiresAt: Date }): Promise<void> {
      tokensByHash.set(input.tokenHash, {
        id: randomUUID(),
        userId: input.userId,
        expiresAt: input.expiresAt,
        revokedAt: null,
      });
      return Promise.resolve();
    },

    findByHash(tokenHash: string): Promise<StoredRefreshToken | null> {
      return Promise.resolve(tokensByHash.get(tokenHash) ?? null);
    },

    revokeByHash(tokenHash: string): Promise<void> {
      const stored = tokensByHash.get(tokenHash);
      if (stored && !stored.revokedAt) {
        tokensByHash.set(tokenHash, { ...stored, revokedAt: new Date() });
      }
      return Promise.resolve();
    },

    revokeAllForUser(userId: string): Promise<void> {
      for (const [hash, stored] of tokensByHash) {
        if (stored.userId === userId && !stored.revokedAt) {
          tokensByHash.set(hash, { ...stored, revokedAt: new Date() });
        }
      }
      return Promise.resolve();
    },
  };

  return { users, refreshTokens };
}
