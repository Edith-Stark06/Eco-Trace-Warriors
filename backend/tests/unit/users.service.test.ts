/* eslint-disable @typescript-eslint/unbound-method -- jest.fn() mocks carry no `this`; referencing them in expect() is safe */
import { UserRole } from '@prisma/client';
import { createUsersService } from '@modules/users';
import type { UsersServiceDeps } from '@modules/users';
import type { PasswordService, UserRecord, UserRepository } from '@modules/auth';
import { ConflictError } from '@shared/errors';
import { createLogger } from '@shared/logging';

function buildUserRecord(overrides: Partial<UserRecord> = {}): UserRecord {
  return {
    id: 'user-1',
    fullName: 'john.collector',
    email: 'john.collector@example.com',
    passwordHash: 'hashed:generated-password',
    phone: null,
    region: null,
    emailVerified: false,
    isActive: true,
    role: { name: UserRole.COLLECTOR },
    createdAt: new Date('2026-09-14T00:00:00.000Z'),
    ...overrides,
  };
}

function buildUsers(overrides: Partial<UserRepository> = {}): jest.Mocked<UserRepository> {
  return {
    findByEmail: jest.fn().mockResolvedValue(null),
    findById: jest.fn().mockResolvedValue(null),
    create: jest.fn().mockResolvedValue(buildUserRecord()),
    updateLastLogin: jest.fn().mockResolvedValue(undefined),
    findRoleId: jest.fn().mockResolvedValue('role-collector'),
    findByRole: jest.fn().mockResolvedValue([]),
    ...overrides,
  } as jest.Mocked<UserRepository>;
}

function buildPasswords(overrides: Partial<PasswordService> = {}): jest.Mocked<PasswordService> {
  return {
    hash: jest.fn().mockImplementation((plain: string) => Promise.resolve(`hashed:${plain}`)),
    verify: jest.fn().mockResolvedValue(true),
    ...overrides,
  } as jest.Mocked<PasswordService>;
}

function buildService(overrides: Partial<UsersServiceDeps> = {}): {
  service: ReturnType<typeof createUsersService>;
  deps: UsersServiceDeps;
} {
  const deps: UsersServiceDeps = {
    users: overrides.users ?? buildUsers(),
    passwords: overrides.passwords ?? buildPasswords(),
    logger: overrides.logger ?? createLogger({ logLevel: 'fatal', nodeEnv: 'test' }),
  };
  return { service: createUsersService(deps), deps };
}

describe('createUsersService — createUser (P10.5 Admin create-user)', () => {
  it.each([UserRole.COLLECTOR, UserRole.RECYCLER, UserRole.GOVERNMENT])(
    'creates a %s user successfully',
    async (role) => {
      const created = buildUserRecord({ role: { name: role } });
      const { service, deps } = buildService({
        users: buildUsers({ create: jest.fn().mockResolvedValue(created) }),
      });

      const result = await service.createUser({ email: 'john.collector@example.com', role });

      expect(deps.users.findRoleId).toHaveBeenCalledWith(role);
      expect(result.user).toEqual({
        id: created.id,
        email: created.email,
        role,
        createdAt: created.createdAt.toISOString(),
      });
    },
  );

  it('returns the generated plaintext password in the result', async () => {
    const { service } = buildService();

    const result = await service.createUser({
      email: 'john.collector@example.com',
      role: UserRole.COLLECTOR,
    });

    expect(typeof result.generatedPassword).toBe('string');
    expect(result.generatedPassword.length).toBeGreaterThanOrEqual(12);
  });

  it('hashes the generated password before persistence, via the existing PasswordService', async () => {
    const { service, deps } = buildService();

    const result = await service.createUser({
      email: 'john.collector@example.com',
      role: UserRole.COLLECTOR,
    });

    expect(deps.passwords.hash).toHaveBeenCalledWith(result.generatedPassword);
    expect(deps.users.create).toHaveBeenCalledWith(
      expect.objectContaining({ passwordHash: `hashed:${result.generatedPassword}` }),
    );
  });

  it('never persists the plaintext password (only the opaque hash reaches the repository)', async () => {
    // An opaque, input-independent stand-in for a real bcrypt hash — unlike
    // the default `hashed:${plain}` test double, this exposes whether the
    // plaintext leaks into the persisted payload by any path other than
    // `passwords.hash()`'s return value.
    const OPAQUE_HASH = '$2b$10$opaqueTestHashValue........................';
    const users = buildUsers();
    const { service } = buildService({
      users,
      passwords: buildPasswords({ hash: jest.fn().mockResolvedValue(OPAQUE_HASH) }),
    });

    const result = await service.createUser({
      email: 'john.collector@example.com',
      role: UserRole.COLLECTOR,
    });

    const createCall = users.create.mock.calls[0]?.[0] as { passwordHash: string };
    expect(createCall.passwordHash).toBe(OPAQUE_HASH);
    expect(JSON.stringify(createCall)).not.toContain(result.generatedPassword);
  });

  it('derives fullName from the email local-part', async () => {
    const { service, deps } = buildService();

    await service.createUser({ email: 'jane.doe@example.com', role: UserRole.RECYCLER });

    expect(deps.users.create).toHaveBeenCalledWith(
      expect.objectContaining({ fullName: 'jane.doe', email: 'jane.doe@example.com' }),
    );
  });

  it('generates a different password on each call (not hardcoded/predictable)', async () => {
    const { service } = buildService();

    const first = await service.createUser({
      email: 'a@example.com',
      role: UserRole.COLLECTOR,
    });
    const second = await service.createUser({
      email: 'b@example.com',
      role: UserRole.COLLECTOR,
    });

    expect(first.generatedPassword).not.toBe(second.generatedPassword);
  });

  it('rejects a duplicate email with ConflictError and does not create a second user', async () => {
    const { service, deps } = buildService({
      users: buildUsers({ findByEmail: jest.fn().mockResolvedValue(buildUserRecord()) }),
    });

    await expect(
      service.createUser({ email: 'john.collector@example.com', role: UserRole.COLLECTOR }),
    ).rejects.toBeInstanceOf(ConflictError);
    expect(deps.users.create).not.toHaveBeenCalled();
  });
});
