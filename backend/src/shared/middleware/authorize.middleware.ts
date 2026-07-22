import type { RequestHandler } from 'express';
import type { UserRole } from '@prisma/client';
import { ForbiddenError, UnauthorizedError } from '@shared/errors';

/**
 * Role-based access control guard. Must run after authenticate().
 * 401 when no principal is attached; 403 when the role is not allowed.
 */
export function authorize(...roles: readonly UserRole[]): RequestHandler {
  return (req, _res, next): void => {
    if (!req.user) {
      throw new UnauthorizedError('Authentication is required.');
    }
    if (!roles.includes(req.user.role)) {
      throw new ForbiddenError();
    }
    next();
  };
}
