import { pinoHttp } from 'pino-http';
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { RequestHandler } from 'express';
import type { Logger } from '@shared/logging';

/** Reads the elapsed request time (ms) pino-http records on the completion object. */
function readDurationMs(val: Record<string, unknown>): number {
  return typeof val.responseTime === 'number' ? val.responseTime : 0;
}

/**
 * Builds the structured fields attached to each request-completion log:
 * the correlation ID (from the requestId middleware), response status, and
 * request duration in milliseconds (measured by pino-http, not recomputed).
 */
function completionFields(
  req: IncomingMessage,
  res: ServerResponse,
  val: Record<string, unknown>,
): Record<string, unknown> {
  return {
    ...val,
    requestId: req.id ?? '',
    status: res.statusCode,
    durationMs: readDurationMs(val),
  };
}

/**
 * HTTP request logging using the shared Pino logger.
 * Reuses the request ID set by the requestId middleware as the log correlation ID
 * and surfaces response status and request duration (ms) on every completion log.
 */
export function requestLogger(logger: Logger): RequestHandler {
  return pinoHttp({
    logger,
    genReqId: (req) => req.id ?? '',
    autoLogging: {
      ignore: (req) => req.url?.endsWith('/health') === true,
    },
    customLogLevel: (_req, res, err) => {
      if (err || res.statusCode >= 500) return 'error';
      if (res.statusCode >= 400) return 'warn';
      return 'info';
    },
    customSuccessObject: (req, res, val: Record<string, unknown>) =>
      completionFields(req, res, val),
    customErrorObject: (req, res, _err, val: Record<string, unknown>) =>
      completionFields(req, res, val),
    customSuccessMessage: (req, res) => `${req.method ?? 'GET'} ${req.url ?? ''} ${res.statusCode}`,
    customErrorMessage: (req, res) => `${req.method ?? 'GET'} ${req.url ?? ''} ${res.statusCode}`,
  }) as RequestHandler;
}
