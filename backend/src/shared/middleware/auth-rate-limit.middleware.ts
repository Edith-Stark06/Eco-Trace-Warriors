import rateLimit from 'express-rate-limit';
import type { RequestHandler } from 'express';
import { TooManyRequestsError } from '@shared/errors';

/** Options for the auth rate limiter, sourced from typed configuration. */
export interface AuthRateLimitOptions {
  /** Sliding window length in milliseconds. */
  readonly windowMs: number;
  /** Max requests permitted per IP within the window. */
  readonly max: number;
}

/**
 * Rate limiter for the authentication endpoints (brute-force protection).
 * Scoped by the caller to the auth router — never registered globally.
 *
 * On exceeding the limit it delegates to the global error handler with a
 * TooManyRequestsError, so 429 responses use the standard error envelope
 * (05_API.md — Error Contract) and carry the standard RateLimit-* headers.
 */
export function authRateLimiter(options: AuthRateLimitOptions): RequestHandler {
  return rateLimit({
    windowMs: options.windowMs,
    max: options.max,
    standardHeaders: true,
    legacyHeaders: false,
    handler: (_req, _res, next) => {
      next(new TooManyRequestsError());
    },
  });
}
