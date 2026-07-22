import { createHash, randomUUID } from 'node:crypto';
import jwt from 'jsonwebtoken';
import { UserRole } from '@prisma/client';
import { UnauthorizedError } from '@shared/errors';

/** Claims carried by a verified access token. */
export interface AccessTokenClaims {
  /** Subject — the user id. */
  readonly sub: string;
  readonly email: string;
  readonly role: UserRole;
}

/** A freshly minted refresh token and its storable representation. */
export interface MintedRefreshToken {
  /** The raw token handed to the client. Never persisted. */
  readonly token: string;
  /** SHA-256 hex digest of the token — the only form ever stored. */
  readonly tokenHash: string;
  readonly expiresAt: Date;
}

/** Dependencies injected into the token service. */
export interface TokenServiceDeps {
  readonly accessSecret: string;
  readonly refreshSecret: string;
  /** Expiry strings in jsonwebtoken format, e.g. "15m", "7d". */
  readonly accessExpiry: string;
  readonly refreshExpiry: string;
}

export interface TokenService {
  /** Signs a short-lived access token carrying user id, email, and role. */
  signAccessToken(input: { userId: string; email: string; role: UserRole }): string;
  /** Verifies an access token. Throws UnauthorizedError on any failure. */
  verifyAccessToken(token: string): AccessTokenClaims;
  /** Mints a refresh token (JWT with a unique jti) plus its storable hash. */
  mintRefreshToken(userId: string): MintedRefreshToken;
  /** Verifies a refresh token's signature and expiry. Throws UnauthorizedError. */
  verifyRefreshToken(token: string): { userId: string };
  /** SHA-256 hex digest used to look tokens up in storage. */
  hashToken(token: string): string;
}

function isUserRole(value: unknown): value is UserRole {
  return typeof value === 'string' && value in UserRole;
}

/** Creates the token service. Framework-agnostic and fully unit-testable. */
export function createTokenService(deps: TokenServiceDeps): TokenService {
  // Config supplies plain strings; jsonwebtoken v9 narrows expiresIn to a
  // template-literal type, so cast once at this boundary.
  const accessExpiry = deps.accessExpiry as jwt.SignOptions['expiresIn'];
  const refreshExpiry = deps.refreshExpiry as jwt.SignOptions['expiresIn'];

  const hashToken = (token: string): string => createHash('sha256').update(token).digest('hex');

  return {
    signAccessToken(input: { userId: string; email: string; role: UserRole }): string {
      return jwt.sign({ email: input.email, role: input.role }, deps.accessSecret, {
        subject: input.userId,
        expiresIn: accessExpiry,
      });
    },

    verifyAccessToken(token: string): AccessTokenClaims {
      let payload: jwt.JwtPayload;
      try {
        const decoded = jwt.verify(token, deps.accessSecret);
        if (typeof decoded === 'string') throw new Error('Unexpected string payload');
        payload = decoded;
      } catch {
        throw new UnauthorizedError('Invalid or expired access token.');
      }

      if (
        typeof payload.sub !== 'string' ||
        typeof payload['email'] !== 'string' ||
        !isUserRole(payload['role'])
      ) {
        throw new UnauthorizedError('Invalid or expired access token.');
      }

      return { sub: payload.sub, email: payload['email'], role: payload['role'] };
    },

    mintRefreshToken(userId: string): MintedRefreshToken {
      const token = jwt.sign({}, deps.refreshSecret, {
        subject: userId,
        jwtid: randomUUID(),
        expiresIn: refreshExpiry,
      });

      // Expiry is authoritative from the signed claim, not re-derived.
      const decoded = jwt.decode(token) as jwt.JwtPayload;
      const expiresAt = new Date((decoded.exp ?? 0) * 1000);

      return { token, tokenHash: hashToken(token), expiresAt };
    },

    verifyRefreshToken(token: string): { userId: string } {
      try {
        const decoded = jwt.verify(token, deps.refreshSecret);
        if (typeof decoded === 'string' || typeof decoded.sub !== 'string') {
          throw new Error('Unexpected payload');
        }
        return { userId: decoded.sub };
      } catch {
        throw new UnauthorizedError('Invalid or expired refresh token.');
      }
    },

    hashToken,
  };
}
