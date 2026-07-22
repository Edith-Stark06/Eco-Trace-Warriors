import type { Request, Response } from 'express';
import { UserRole } from '@prisma/client';
import { authorize } from '@shared/middleware';
import { ForbiddenError, UnauthorizedError } from '@shared/errors';

function buildReq(role?: UserRole): Request {
  const req = {} as Request;
  if (role) {
    req.user = { userId: 'user-1', role };
  }
  return req;
}

describe('authorize', () => {
  const res = {} as Response;

  it('throws UnauthorizedError when no principal is attached', () => {
    expect(() => authorize(UserRole.ADMIN)(buildReq(), res, jest.fn())).toThrow(UnauthorizedError);
  });

  it('throws ForbiddenError when the role is not allowed', () => {
    expect(() => authorize(UserRole.ADMIN)(buildReq(UserRole.CONSUMER), res, jest.fn())).toThrow(
      ForbiddenError,
    );
  });

  it('calls next() when the role is allowed', () => {
    const next = jest.fn();

    authorize(UserRole.ADMIN, UserRole.GOVERNMENT)(buildReq(UserRole.GOVERNMENT), res, next);

    expect(next).toHaveBeenCalledWith();
  });
});
