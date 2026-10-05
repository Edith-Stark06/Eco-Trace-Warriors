/* eslint-disable @typescript-eslint/unbound-method -- jest.fn() mocks carry no `this`; referencing them in expect() is safe */
import { UserRole } from '@prisma/client';
import { createAuthService } from '@modules/auth';
import type {
  AuthServiceDeps,
  PasswordService,
  RefreshTokenRepository,
  StoredRefreshToken,
  TokenService,
  UserRecord,
  UserRepository,
} from '@modules/auth';
import { ConflictError, NotFoundError, UnauthorizedError } from '@shared/errors';
import { createLogger } from '@shared/logging';

const FIXED_NOW = new Date('2026-07-22T10:00:00.000Z');
const FUTURE = new Date('2026-07-29T10:00:00.000Z');

const consumerUser: UserRecord = {
  id: 'user-1',
  fullName: 'Asha Kumar',
  email: 'asha@example.com',
  passwordHash: 'hashed:password123',
  phone: null,
  region: null,
  emailVerified: false,
  isActive: true,
  role: { name: UserRole.CONSUMER },
  createdAt: new Date('2026-07-01T00:00:00.000Z'),
};

function buildUsers(overrides: Partial<UserRepository> = {}): jest.Mocked<UserRepository> {
  return {
    findByEmail: jest.fn().mockResolvedValue(null),
    findById: jest.fn().mockResolvedValue(consumerUser),
    create: jest.fn().mockResolvedValue(consumerUser),
    updateLastLogin: jest.fn().mockResolvedValue(undefined),
    findRoleId: jest.fn().mockResolvedValue('role-consumer'),
    ...overrides,
  } as jest.Mocked<UserRepository>;
}

function buildRefreshTokens(
  overrides: Partial<RefreshTokenRepository> = {},
): jest.Mocked<RefreshTokenRepository> {
  return {
    store: jest.fn().mockResolvedValue(undefined),
    findByHash: jest.fn().mockResolvedValue(null),
    revokeByHash: jest.fn().mockResolvedValue(undefined),
    revokeAllForUser: jest.fn().mockResolvedValue(undefined),
    ...overrides,
  } as jest.Mocked<RefreshTokenRepository>;
}

function buildPasswords(overrides: Partial<PasswordService> = {}): jest.Mocked<PasswordService> {
  return {
    hash: jest.fn().mockImplementation((plain: string) => Promise.resolve(`hashed:${plain}`)),
    verify: jest
      .fn()
      .mockImplementation((plain: string, hash: string) =>
        Promise.resolve(hash === `hashed:${plain}`),
      ),
    ...overrides,
  } as jest.Mocked<PasswordService>;
}

function buildTokens(overrides: Partial<TokenService> = {}): jest.Mocked<TokenService> {
  return {
    signAccessToken: jest.fn().mockReturnValue('access-token'),
    verifyAccessToken: jest.fn(),
    mintRefreshToken: jest.fn().mockReturnValue({
      token: 'refresh-token',
      tokenHash: 'hash:refresh-token',
      expiresAt: FUTURE,
    }),
    verifyRefreshToken: jest.fn().mockReturnValue({ userId: 'user-1' }),
    hashToken: jest.fn().mockImplementation((token: string) => `hash:${token}`),
    ...overrides,
  } as jest.Mocked<TokenService>;
}

interface TestDeps {
  users: jest.Mocked<UserRepository>;
  refreshTokens: jest.Mocked<RefreshTokenRepository>;
  passwords: jest.Mocked<PasswordService>;
  tokens: jest.Mocked<TokenService>;
}

function buildService(overrides: Partial<TestDeps> = {}): {
  service: ReturnType<typeof createAuthService>;
  deps: TestDeps;
} {
  const deps: TestDeps = {
    users: overrides.users ?? buildUsers(),
    refreshTokens: overrides.refreshTokens ?? buildRefreshTokens(),
    passwords: overrides.passwords ?? buildPasswords(),
    tokens: overrides.tokens ?? buildTokens(),
  };
  const serviceDeps: AuthServiceDeps = {
    ...deps,
    logger: createLogger({ logLevel: 'fatal', nodeEnv: 'test' }),
    now: () => FIXED_NOW,
  };
  return { service: createAuthService(serviceDeps), deps };
}

describe('createAuthService', () => {
  describe('register', () => {
    const input = {
      email: 'asha@example.com',
      password: 'password123',
      confirmPassword: 'password123',
      fullName: 'Asha Kumar',
    };

    it('creates a CONSUMER user and returns tokens with the public profile', async () => {
      const { service, deps } = buildService();

      const result = await service.register(input);

      expect(deps.passwords.hash).toHaveBeenCalledWith('password123');
      expect(deps.users.create).toHaveBeenCalledWith(
        expect.objectContaining({
          email: 'asha@example.com',
          passwordHash: 'hashed:password123',
          roleId: 'role-consumer',
        }),
      );
      expect(deps.refreshTokens.store).toHaveBeenCalledWith({
        tokenHash: 'hash:refresh-token',
        userId: 'user-1',
        expiresAt: FUTURE,
      });
      expect(result).toEqual({
        user: expect.objectContaining({ id: 'user-1', role: UserRole.CONSUMER }),
        accessToken: 'access-token',
        refreshToken: 'refresh-token',
      });
      expect(result.user).not.toHaveProperty('passwordHash');
    });

    it('rejects a duplicate email with ConflictError', async () => {
      const { service } = buildService({
        users: buildUsers({ findByEmail: jest.fn().mockResolvedValue(consumerUser) }),
      });

      await expect(service.register(input)).rejects.toBeInstanceOf(ConflictError);
    });
  });

  describe('login', () => {
    const input = { email: 'asha@example.com', password: 'password123' };

    it('returns tokens and profile for valid credentials', async () => {
      const { service, deps } = buildService({
        users: buildUsers({ findByEmail: jest.fn().mockResolvedValue(consumerUser) }),
      });

      const result = await service.login(input);

      expect(deps.users.updateLastLogin).toHaveBeenCalledWith('user-1', FIXED_NOW);
      expect(result.accessToken).toBe('access-token');
      expect(result.user.email).toBe('asha@example.com');
    });

    it('rejects an unknown email with a generic UnauthorizedError', async () => {
      const { service } = buildService();

      await expect(service.login(input)).rejects.toThrow('Invalid email or password.');
    });

    it('rejects a wrong password with the same generic message', async () => {
      const { service } = buildService({
        users: buildUsers({ findByEmail: jest.fn().mockResolvedValue(consumerUser) }),
      });

      await expect(service.login({ ...input, password: 'wrong' })).rejects.toThrow(
        'Invalid email or password.',
      );
    });

    it('rejects a deactivated account', async () => {
      const { service } = buildService({
        users: buildUsers({
          findByEmail: jest.fn().mockResolvedValue({ ...consumerUser, isActive: false }),
        }),
      });

      await expect(service.login(input)).rejects.toThrow('This account has been deactivated.');
    });
  });

  describe('refresh', () => {
    const activeStored: StoredRefreshToken = {
      id: 'rt-1',
      userId: 'user-1',
      expiresAt: FUTURE,
      revokedAt: null,
    };

    it('rotates: revokes the presented token and issues a new pair', async () => {
      const { service, deps } = buildService({
        refreshTokens: buildRefreshTokens({
          findByHash: jest.fn().mockResolvedValue(activeStored),
        }),
      });

      const result = await service.refresh('old-refresh-token');

      expect(deps.refreshTokens.revokeByHash).toHaveBeenCalledWith('hash:old-refresh-token');
      expect(deps.refreshTokens.store).toHaveBeenCalled();
      expect(result).toEqual({ accessToken: 'access-token', refreshToken: 'refresh-token' });
    });

    it('rejects an unknown token', async () => {
      const { service } = buildService();

      await expect(service.refresh('unknown')).rejects.toBeInstanceOf(UnauthorizedError);
    });

    it('revokes all sessions when a rotated token is reused', async () => {
      const { service, deps } = buildService({
        refreshTokens: buildRefreshTokens({
          findByHash: jest
            .fn()
            .mockResolvedValue({ ...activeStored, revokedAt: new Date('2026-07-21') }),
        }),
      });

      await expect(service.refresh('reused')).rejects.toBeInstanceOf(UnauthorizedError);
      expect(deps.refreshTokens.revokeAllForUser).toHaveBeenCalledWith('user-1');
    });

    it('rejects an expired stored token', async () => {
      const { service } = buildService({
        refreshTokens: buildRefreshTokens({
          findByHash: jest
            .fn()
            .mockResolvedValue({ ...activeStored, expiresAt: new Date('2026-07-01') }),
        }),
      });

      await expect(service.refresh('expired')).rejects.toBeInstanceOf(UnauthorizedError);
    });

    it('rejects when the user has been deactivated since issuance', async () => {
      const { service } = buildService({
        users: buildUsers({
          findById: jest.fn().mockResolvedValue({ ...consumerUser, isActive: false }),
        }),
        refreshTokens: buildRefreshTokens({
          findByHash: jest.fn().mockResolvedValue(activeStored),
        }),
      });

      await expect(service.refresh('valid')).rejects.toBeInstanceOf(UnauthorizedError);
    });
  });

  describe('logout', () => {
    it('revokes the presented token', async () => {
      const { service, deps } = buildService();

      await service.logout('refresh-token');

      expect(deps.refreshTokens.revokeByHash).toHaveBeenCalledWith('hash:refresh-token');
    });

    it('succeeds silently for an unparseable token (idempotent)', async () => {
      const { service, deps } = buildService({
        tokens: buildTokens({
          verifyRefreshToken: jest.fn().mockImplementation(() => {
            throw new UnauthorizedError();
          }),
        }),
      });

      await expect(service.logout('garbage')).resolves.toBeUndefined();
      expect(deps.refreshTokens.revokeByHash).not.toHaveBeenCalled();
    });
  });

  describe('getMe', () => {
    it('returns the public profile without the password hash', async () => {
      const { service } = buildService();

      const user = await service.getMe('user-1');

      expect(user).toEqual({
        id: 'user-1',
        fullName: 'Asha Kumar',
        email: 'asha@example.com',
        phone: null,
        region: null,
        role: UserRole.CONSUMER,
        emailVerified: false,
        createdAt: '2026-07-01T00:00:00.000Z',
      });
    });

    it('throws NotFoundError for a missing user', async () => {
      const { service } = buildService({
        users: buildUsers({ findById: jest.fn().mockResolvedValue(null) }),
      });

      await expect(service.getMe('ghost')).rejects.toBeInstanceOf(NotFoundError);
    });
  });
});
