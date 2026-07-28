import type { PrismaClient, UserRole } from '@prisma/client';

/**
 * Repositories are the only place Prisma is used for the auth module.
 * Services depend on these interfaces, never on Prisma directly —
 * see docs/engineering/06_BACKEND.md (Layering).
 */

/** Input for creating a user row. The role is referenced by id (FK). */
export interface CreateUserInput {
  readonly fullName: string;
  readonly email: string;
  readonly passwordHash: string;
  readonly phone?: string | undefined;
  readonly region?: string | undefined;
  readonly roleId: string;
}

/** User row as read by the auth module, with the role name joined in. */
export interface UserRecord {
  readonly id: string;
  readonly fullName: string;
  readonly email: string;
  readonly passwordHash: string;
  readonly phone: string | null;
  readonly region: string | null;
  readonly emailVerified: boolean;
  readonly isActive: boolean;
  readonly role: { readonly name: UserRole };
  readonly createdAt: Date;
}

export interface UserRepository {
  findByEmail(email: string): Promise<UserRecord | null>;
  findById(id: string): Promise<UserRecord | null>;
  create(input: CreateUserInput): Promise<UserRecord>;
  updateLastLogin(id: string, when: Date): Promise<void>;
  /** Resolves a role's primary key by its enum name (roles are seeded). */
  findRoleId(name: UserRole): Promise<string | null>;
  /** Returns all active users with the given role, ordered by fullName. */
  findByRole(role: UserRole): Promise<UserRecord[]>;
}

const userSelect = {
  id: true,
  fullName: true,
  email: true,
  passwordHash: true,
  phone: true,
  region: true,
  emailVerified: true,
  isActive: true,
  role: { select: { name: true } },
  createdAt: true,
} as const;

/** Creates the user repository backed by Prisma. */
export function createUserRepository(deps: { readonly prisma: PrismaClient }): UserRepository {
  const { prisma } = deps;

  return {
    async findByEmail(email: string): Promise<UserRecord | null> {
      return prisma.user.findUnique({ where: { email }, select: userSelect });
    },

    async findById(id: string): Promise<UserRecord | null> {
      return prisma.user.findUnique({ where: { id }, select: userSelect });
    },

    async create(input: CreateUserInput): Promise<UserRecord> {
      return prisma.user.create({
        data: {
          fullName: input.fullName,
          email: input.email,
          passwordHash: input.passwordHash,
          phone: input.phone ?? null,
          region: input.region ?? null,
          roleId: input.roleId,
        },
        select: userSelect,
      });
    },

    async updateLastLogin(id: string, when: Date): Promise<void> {
      await prisma.user.update({ where: { id }, data: { lastLogin: when } });
    },

    async findRoleId(name: UserRole): Promise<string | null> {
      const role = await prisma.role.findUnique({ where: { name }, select: { id: true } });
      return role?.id ?? null;
    },

    async findByRole(role: UserRole): Promise<UserRecord[]> {
      // Only active users are eligible assignment targets; the submission
      // service rejects inactive assignees, so filtering here keeps the
      // lookup list aligned with what assignment will actually accept.
      return prisma.user.findMany({
        where: { isActive: true, role: { name: role } },
        orderBy: { fullName: 'asc' },
        select: userSelect,
      });
    },
  };
}

/** Stored refresh-token row (hash only — the raw token is never persisted). */
export interface StoredRefreshToken {
  readonly id: string;
  readonly userId: string;
  readonly expiresAt: Date;
  readonly revokedAt: Date | null;
}

export interface RefreshTokenRepository {
  store(input: { tokenHash: string; userId: string; expiresAt: Date }): Promise<void>;
  findByHash(tokenHash: string): Promise<StoredRefreshToken | null>;
  /** Idempotent — revoking an unknown or already-revoked token is a no-op. */
  revokeByHash(tokenHash: string): Promise<void>;
  /** Revokes every active token of a user (logout-all / reuse response). */
  revokeAllForUser(userId: string): Promise<void>;
}

/** Creates the refresh-token repository backed by Prisma. */
export function createRefreshTokenRepository(deps: {
  readonly prisma: PrismaClient;
}): RefreshTokenRepository {
  const { prisma } = deps;

  return {
    async store(input: { tokenHash: string; userId: string; expiresAt: Date }): Promise<void> {
      await prisma.refreshToken.create({ data: input });
    },

    async findByHash(tokenHash: string): Promise<StoredRefreshToken | null> {
      return prisma.refreshToken.findUnique({
        where: { tokenHash },
        select: { id: true, userId: true, expiresAt: true, revokedAt: true },
      });
    },

    async revokeByHash(tokenHash: string): Promise<void> {
      await prisma.refreshToken.updateMany({
        where: { tokenHash, revokedAt: null },
        data: { revokedAt: new Date() },
      });
    },

    async revokeAllForUser(userId: string): Promise<void> {
      await prisma.refreshToken.updateMany({
        where: { userId, revokedAt: null },
        data: { revokedAt: new Date() },
      });
    },
  };
}
