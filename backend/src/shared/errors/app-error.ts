import type { ErrorCode } from './error-codes';
import { ErrorCodes } from './error-codes';

/** Field-level detail attached to validation errors. */
export interface ErrorDetail {
  readonly field: string;
  readonly issue: string;
}

/**
 * Base class for all operational (expected) application errors.
 * Anything not an AppError is treated as an unexpected 500 by the error handler.
 */
export class AppError extends Error {
  readonly code: ErrorCode;
  readonly httpStatus: number;
  readonly details: readonly ErrorDetail[] | undefined;

  constructor(
    code: ErrorCode,
    httpStatus: number,
    message: string,
    details?: readonly ErrorDetail[],
  ) {
    super(message);
    this.name = new.target.name;
    this.code = code;
    this.httpStatus = httpStatus;
    this.details = details;
    Error.captureStackTrace(this, new.target);
  }
}

export class ValidationError extends AppError {
  constructor(message = 'Request validation failed.', details?: readonly ErrorDetail[]) {
    super(ErrorCodes.VALIDATION_ERROR, 400, message, details);
  }
}

export class UnauthorizedError extends AppError {
  constructor(message = 'Authentication is required.') {
    super(ErrorCodes.UNAUTHORIZED, 401, message);
  }
}

export class ForbiddenError extends AppError {
  constructor(message = 'You are not allowed to perform this action.') {
    super(ErrorCodes.FORBIDDEN, 403, message);
  }
}

export class NotFoundError extends AppError {
  constructor(message = 'The requested resource was not found.') {
    super(ErrorCodes.NOT_FOUND, 404, message);
  }
}

export class ConflictError extends AppError {
  constructor(message = 'The request conflicts with the current state.') {
    super(ErrorCodes.CONFLICT, 409, message);
  }
}

export class TooManyRequestsError extends AppError {
  constructor(message = 'Too many requests. Please try again later.') {
    super(ErrorCodes.TOO_MANY_REQUESTS, 429, message);
  }
}

export class InternalError extends AppError {
  constructor(message = 'An unexpected error occurred.') {
    super(ErrorCodes.INTERNAL_ERROR, 500, message);
  }
}

export class ServiceUnavailableError extends AppError {
  constructor(message = 'The service is temporarily unavailable.') {
    super(ErrorCodes.SERVICE_UNAVAILABLE, 503, message);
  }
}
