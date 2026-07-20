import { randomUUID } from 'node:crypto';
import type { NextFunction, Request, RequestHandler, Response } from 'express';

export const REQUEST_ID_HEADER = 'x-request-id';

/**
 * Attaches a correlation ID to every request.
 * Honors an incoming X-Request-Id header (from the gateway) or generates a UUID.
 * The ID is echoed on the response and propagated to downstream service calls.
 */
export function requestId(): RequestHandler {
  return (req: Request, res: Response, next: NextFunction): void => {
    const incoming = req.header(REQUEST_ID_HEADER);
    const id = incoming && incoming.length <= 128 ? incoming : randomUUID();
    req.id = id;
    res.setHeader(REQUEST_ID_HEADER, id);
    next();
  };
}
