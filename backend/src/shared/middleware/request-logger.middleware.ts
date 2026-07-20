import { pinoHttp } from 'pino-http';
import type { RequestHandler } from 'express';
import type { Logger } from '@shared/logging';

/**
 * HTTP request logging using the shared Pino logger.
 * Reuses the request ID set by the requestId middleware as the log correlation ID.
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
  }) as RequestHandler;
}
