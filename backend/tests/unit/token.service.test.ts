import { createHash } from 'node:crypto';
import { UserRole } from '@prisma/client';
import { createTokenService } from '@modules/auth';
import { UnauthorizedError } from '@shared/errors';

function buildService(
  overrides: Partial<Parameters<typeof createTokenService>[0]> = {},
): ReturnType<typeof createTokenService> {
  return createTokenService({
    accessSecret: 'unit-test-access-secret-0123456789abcdef',
    refreshSecret: 'unit-test-refresh-secret-0123456789abcdef',
    accessExpiry: '15m',
    refreshExpiry: '7d',
    ...overrides,
  });
}

describe('createTokenService', () => {
  describe('access tokens', () => {
    it('round-trips userId, email, and role through sign/verify', () => {
      const service = buildService();
      const token = service.signAccessToken({
        userId: 'user-1',
        email: 'user@example.com',
        role: UserRole.CONSUMER,
      });

      expect(service.verifyAccessToken(token)).toEqual({
        sub: 'user-1',
        email: 'user@example.com',
        role: UserRole.CONSUMER,
      });
    });

    it('rejects a tampered token', () => {
      const service = buildService();
      const token = service.signAccessToken({
        userId: 'user-1',
        email: 'user@example.com',
        role: UserRole.CONSUMER,
      });

      expect(() => service.verifyAccessToken(`${token}tampered`)).toThrow(UnauthorizedError);
    });

    it('rejects a token signed with a different secret', () => {
      const service = buildService();
      const other = buildService({ accessSecret: 'a-completely-different-secret-0123456789' });
      const token = other.signAccessToken({
        userId: 'user-1',
        email: 'user@example.com',
        role: UserRole.ADMIN,
      });

      expect(() => service.verifyAccessToken(token)).toThrow(UnauthorizedError);
    });

    it('rejects an expired token', () => {
      const service = buildService({ accessExpiry: '-1s' });
      const token = service.signAccessToken({
        userId: 'user-1',
        email: 'user@example.com',
        role: UserRole.CONSUMER,
      });

      expect(() => service.verifyAccessToken(token)).toThrow(UnauthorizedError);
    });

    it('rejects a refresh token presented as an access token', () => {
      const service = buildService();
      const { token } = service.mintRefreshToken('user-1');

      expect(() => service.verifyAccessToken(token)).toThrow(UnauthorizedError);
    });
  });

  describe('refresh tokens', () => {
    it('mints a token whose hash matches hashToken and carries a future expiry', () => {
      const service = buildService();
      const minted = service.mintRefreshToken('user-1');

      expect(minted.tokenHash).toBe(service.hashToken(minted.token));
      expect(minted.expiresAt.getTime()).toBeGreaterThan(Date.now());
    });

    it('mints unique tokens for the same user (jti)', () => {
      const service = buildService();

      expect(service.mintRefreshToken('user-1').token).not.toBe(
        service.mintRefreshToken('user-1').token,
      );
    });

    it('round-trips the userId through mint/verify', () => {
      const service = buildService();
      const { token } = service.mintRefreshToken('user-42');

      expect(service.verifyRefreshToken(token)).toEqual({ userId: 'user-42' });
    });

    it('rejects an expired refresh token', () => {
      const service = buildService({ refreshExpiry: '-1s' });
      const { token } = service.mintRefreshToken('user-1');

      expect(() => service.verifyRefreshToken(token)).toThrow(UnauthorizedError);
    });

    it('rejects an access token presented as a refresh token', () => {
      const service = buildService();
      const token = service.signAccessToken({
        userId: 'user-1',
        email: 'user@example.com',
        role: UserRole.CONSUMER,
      });

      expect(() => service.verifyRefreshToken(token)).toThrow(UnauthorizedError);
    });
  });

  describe('hashToken', () => {
    it('is a deterministic SHA-256 hex digest', () => {
      const service = buildService();
      const expected = createHash('sha256').update('some-token').digest('hex');

      expect(service.hashToken('some-token')).toBe(expected);
      expect(service.hashToken('some-token')).toBe(service.hashToken('some-token'));
    });
  });
});
