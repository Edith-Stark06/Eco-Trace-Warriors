import type { NextFunction, Request, RequestHandler, Response } from 'express';
import { NotFoundError } from '@shared/errors';

/** Converts unmatched routes into a NotFoundError for the global error handler. */
export function notFoundHandler(): RequestHandler {
  return (req: Request, _res: Response, next: NextFunction): void => {
    next(new NotFoundError(`Route ${req.method} ${req.path} does not exist.`));
  };
}
