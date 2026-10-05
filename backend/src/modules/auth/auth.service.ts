import { UserRole } from '@prisma/client';
import { ConflictError, InternalError, NotFoundError, UnauthorizedError } from '@shared/errors';
import type { Logger } from '@shared/logging';
import type { RefreshTokenRepository, UserRecord, UserRepository } from './auth.repository';
import type { LoginInput, RegisterInput } from './auth.schemas';
import type { AuthResult, AuthTokens, PublicUser } from './auth.types';
import type { PasswordService } from './password.service';
import type { TokenService } from './token.service';

/** Generic message for every credential failure — prevents user enumeration. */
const INVALID_CREDENTIALS = 'Invalid email or password.';

/** Dependencies injected into the auth service. */
export interface AuthServiceDeps {
  readonly users: UserRepository;
  readonly refreshTokens: RefreshTokenRepository;
  readonly passwords: PasswordService;
  readonly tokens: TokenService;
  readonly logger: Logger;
  /** Clock provider — injectable for deterministic tests. */
  readonly now?: () => Date;
}

export interface AuthService {
  /** Creates a CONSUMER account and issues an initial token pair. */
  register(input: RegisterInput): Promise<AuthResult>;
  /** Verifies credentials and issues a token pair. */
  login(input: LoginInput): Promise<AuthResult>;
  /** Rotates a refresh token: revokes the old one, issues a new pair. */
  refresh(refreshToken: string): Promise<AuthTokens>;
  /** Revokes a refresh token. Idempotent — dead tokens still log out cleanly. */
  logout(refreshToken: string): Promise<void>;
  /** Returns the authenticated user's public profile. */
  getMe(userId: string): Promise<PublicUser>;
}

function toPublicUser(user: UserRecord): PublicUser {
  return {
    id: user.id,
    fullName: user.fullName,
    email: user.email,
    phone: user.phone,
    region: user.region,
    role: user.role.name,
    emailVerified: user.emailVerified,
    createdAt: user.createdAt.toISOString(),
  };
}

/** Creates the auth service. Framework-agnostic and fully unit-testable. */
export function createAuthService(deps: AuthServiceDeps): AuthService {
  const now = deps.now ?? ((): Date => new Date());

  async function issueTokens(user: UserRecord): Promise<AuthTokens> {
    const accessToken = deps.tokens.signAccessToken({
      userId: user.id,
      email: user.email,
      role: user.role.name,
    });
    const minted = deps.tokens.mintRefreshToken(user.id);
    await deps.refreshTokens.store({
      tokenHash: minted.tokenHash,
      userId: user.id,
      expiresAt: minted.expiresAt,
    });
    return { accessToken, refreshToken: minted.token };
  }

  return {
    async register(input: RegisterInput): Promise<AuthResult> {
      const existing = await deps.users.findByEmail(input.email);
      if (existing) {
        throw new ConflictError('An account with this email already exists.');
      }

      const roleId = await deps.users.findRoleId(UserRole.CONSUMER);
      if (!roleId) {
        // Roles are seeded by prisma/seed.ts; absence is a deployment fault.
        deps.logger.error({ role: UserRole.CONSUMER }, 'Required role missing from database');
        throw new InternalError();
      }

      const passwordHash = await deps.passwords.hash(input.password);
      const user = await deps.users.create({
        fullName: input.fullName,
        email: input.email,
        passwordHash,
        phone: input.phone,
        region: input.region,
        roleId,
      });

      deps.logger.info({ userId: user.id }, 'User registered');
      const tokens = await issueTokens(user);
      return { user: toPublicUser(user), ...tokens };
    },

    async login(input: LoginInput): Promise<AuthResult> {
      const user = await deps.users.findByEmail(input.email);
      if (!user) {
        throw new UnauthorizedError(INVALID_CREDENTIALS);
      }

      const passwordOk = await deps.passwords.verify(input.password, user.passwordHash);
      if (!passwordOk) {
        throw new UnauthorizedError(INVALID_CREDENTIALS);
      }

      if (!user.isActive) {
        throw new UnauthorizedError('This account has been deactivated.');
      }

      await deps.users.updateLastLogin(user.id, now());
      deps.logger.info({ userId: user.id }, 'User logged in');
      const tokens = await issueTokens(user);
      return { user: toPublicUser(user), ...tokens };
    },

    async refresh(refreshToken: string): Promise<AuthTokens> {
      const { userId } = deps.tokens.verifyRefreshToken(refreshToken);
      const tokenHash = deps.tokens.hashToken(refreshToken);
      const stored = await deps.refreshTokens.findByHash(tokenHash);

      if (!stored) {
        throw new UnauthorizedError('Invalid or expired refresh token.');
      }

      if (stored.revokedAt) {
        // Reuse of a rotated token — treat the whole family as compromised.
        deps.logger.warn({ userId }, 'Revoked refresh token reused; revoking all sessions');
        await deps.refreshTokens.revokeAllForUser(userId);
        throw new UnauthorizedError('Invalid or expired refresh token.');
      }

      if (stored.expiresAt.getTime() <= now().getTime()) {
        throw new UnauthorizedError('Invalid or expired refresh token.');
      }

      const user = await deps.users.findById(userId);
      if (!user || !user.isActive) {
        throw new UnauthorizedError('Invalid or expired refresh token.');
      }

      // Rotation: the presented token becomes single-use.
      await deps.refreshTokens.revokeByHash(tokenHash);
      return issueTokens(user);
    },

    async logout(refreshToken: string): Promise<void> {
      let userId: string;
      try {
        userId = deps.tokens.verifyRefreshToken(refreshToken).userId;
      } catch {
        // An unparseable token has no session to revoke — logout still succeeds.
        return;
      }
      await deps.refreshTokens.revokeByHash(deps.tokens.hashToken(refreshToken));
      deps.logger.info({ userId }, 'User logged out');
    },

    async getMe(userId: string): Promise<PublicUser> {
      const user = await deps.users.findById(userId);
      if (!user) {
        throw new NotFoundError('User not found.');
      }
      return toPublicUser(user);
    },
  };
}
