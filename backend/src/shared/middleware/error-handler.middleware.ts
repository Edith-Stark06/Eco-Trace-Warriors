import type { ErrorRequestHandler, NextFunction, Request, Response } from 'express';
import { AppError, ErrorCodes } from '@shared/errors';
import type { Logger } from '@shared/logging';
import type { ErrorResponse } from '../../types';

/**
 * Global error handler — the single place errors become HTTP responses.
 * AppError instances map to their status and code; anything else is a
 * generic 500 whose internals are logged but never sent to the client.
 * See docs/engineering/05_API.md — Error Contract.
 */
export function errorHandler(logger: Logger): ErrorRequestHandler {
  return (err: unknown, req: Request, res: Response, _next: NextFunction): void => {
    if (err instanceof AppError) {
      const body: ErrorResponse = {
        success: false,
        error: {
          code: err.code,
          message: err.message,
          ...(err.details ? { details: err.details } : {}),
        },
      };
      res.status(err.httpStatus).json(body);
      return;
    }

    logger.error({ err, requestId: req.id, path: req.path }, 'Unhandled error');

    const body: ErrorResponse = {
      success: false,
      error: {
        code: ErrorCodes.INTERNAL_ERROR,
        message: 'An unexpected error occurred.',
      },
    };
    res.status(500).json(body);
  };
}
