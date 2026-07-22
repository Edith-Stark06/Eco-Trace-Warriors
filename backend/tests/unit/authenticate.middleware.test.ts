import type { Request, Response } from 'express';
import { UserRole } from '@prisma/client';
import { createTokenService } from '@modules/auth';
import { authenticate } from '@shared/middleware';
import { UnauthorizedError } from '@shared/errors';

const tokens = createTokenService({
  accessSecret: 'unit-test-access-secret-0123456789abcdef',
  refreshSecret: 'unit-test-refresh-secret-0123456789abcdef',
  accessExpiry: '15m',
  refreshExpiry: '7d',
});

function buildReq(authorization?: string): Request {
  return { headers: authorization ? { authorization } : {} } as Request;
}

describe('authenticate', () => {
  const middleware = authenticate(tokens);
  const res = {} as Response;

  it('throws UnauthorizedError when the header is missing', () => {
    expect(() => middleware(buildReq(), res, jest.fn())).toThrow(UnauthorizedError);
  });

  it('throws UnauthorizedError for a non-Bearer scheme', () => {
    expect(() => middleware(buildReq('Basic abc123'), res, jest.fn())).toThrow(UnauthorizedError);
  });

  it('throws UnauthorizedError for an invalid token', () => {
    expect(() => middleware(buildReq('Bearer not-a-jwt'), res, jest.fn())).toThrow(
      UnauthorizedError,
    );
  });

  it('attaches the principal and calls next() for a valid token', () => {
    const token = tokens.signAccessToken({
      userId: 'user-1',
      email: 'user@example.com',
      role: UserRole.COLLECTOR,
    });
    const req = buildReq(`Bearer ${token}`);
    const next = jest.fn();

    middleware(req, res, next);

    expect(req.user).toEqual({ userId: 'user-1', role: UserRole.COLLECTOR });
    expect(next).toHaveBeenCalledWith();
  });
});
