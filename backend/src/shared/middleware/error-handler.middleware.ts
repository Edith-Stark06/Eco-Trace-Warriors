import type { ErrorRequestHandler, NextFunction, Request, Response } from 'express';
import { Prisma } from '@prisma/client';
import { AppError, ErrorCodes } from '@shared/errors';
import type { ErrorCode } from '@shared/errors';
import type { Logger } from '@shared/logging';
import type { ErrorResponse } from '../../types';

/**
 * Known Prisma error codes mapped to safe, semantic HTTP responses. Messages are
 * intentionally generic — the raw Prisma message may expose table/column/SQL
 * detail and must never reach the client (05_API.md — Error Contract). Any
 * Prisma code not listed here falls through to the generic 500 path.
 */
const PRISMA_ERROR_MAP: Readonly<
  Record<string, { httpStatus: number; code: ErrorCode; message: string }>
> = {
  // Unique constraint violation.
  P2002: {
    httpStatus: 409,
    code: ErrorCodes.CONFLICT,
    message: 'The request conflicts with the current state.',
  },
  // Record required by the operation was not found (e.g. update/delete on a missing row).
  P2025: {
    httpStatus: 404,
    code: ErrorCodes.NOT_FOUND,
    message: 'The requested resource was not found.',
  },
};

/**
 * Global error handler — the single place errors become HTTP responses.
 * AppError instances map to their status and code; known Prisma errors map to
 * semantic 409/404 responses; anything else is a generic 500 whose internals
 * are logged but never sent to the client.
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

    // express.json() throws a SyntaxError (status 400, type
    // 'entity.parse.failed') for a malformed request body. Without this
    // check it falls through to the generic 500 below (found live during
    // P9.7 security testing) — a client mistake should never be reported
    // as a server error.
    if (
      err instanceof SyntaxError &&
      'status' in err &&
      (err as SyntaxError & { status?: number }).status === 400 &&
      'type' in err &&
      (err as SyntaxError & { type?: string }).type === 'entity.parse.failed'
    ) {
      const body: ErrorResponse = {
        success: false,
        error: {
          code: ErrorCodes.VALIDATION_ERROR,
          message: 'The request body is not valid JSON.',
        },
      };
      res.status(400).json(body);
      return;
    }

    if (err instanceof Prisma.PrismaClientKnownRequestError) {
      const mapped = PRISMA_ERROR_MAP[err.code];
      if (mapped) {
        // Logged for observability; the raw Prisma detail never reaches the client.
        logger.warn(
          { err, requestId: req.id, path: req.path, prismaCode: err.code },
          'Mapped Prisma error',
        );
        const body: ErrorResponse = {
          success: false,
          error: { code: mapped.code, message: mapped.message },
        };
        res.status(mapped.httpStatus).json(body);
        return;
      }
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
