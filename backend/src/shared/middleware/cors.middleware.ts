import corsMiddleware from 'cors';
import type { RequestHandler } from 'express';

/**
 * Cross-Origin Resource Sharing policy, driven entirely by the configured
 * allowlist (`AppConfig.corsOrigins`).
 *
 * Policy:
 * - Requests with no Origin header (curl, Postman, server-to-server) are allowed.
 * - Browser requests whose Origin is in the allowlist are allowed.
 * - Any other Origin is rejected: no CORS headers are emitted, so the browser
 *   blocks the response. The request itself is not errored — non-browser clients
 *   are unaffected.
 */
export function cors(allowedOrigins: readonly string[]): RequestHandler {
  const allowlist = new Set(allowedOrigins);

  return corsMiddleware({
    origin(origin, callback) {
      if (origin === undefined || allowlist.has(origin)) {
        callback(null, true);
        return;
      }
      callback(null, false);
    },
    credentials: true,
  });
}
