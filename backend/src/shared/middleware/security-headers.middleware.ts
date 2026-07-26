import helmet from 'helmet';
import type { RequestHandler } from 'express';

/**
 * Applies HTTP security response headers via Helmet.
 * Runs first in the pipeline so every response — including 404s and errors —
 * carries the headers.
 *
 * Content-Security-Policy is disabled: this service is a JSON REST API, and a
 * restrictive default CSP would break the future Swagger/UI docs page
 * (`{apiPrefix}/docs`). All other Helmet defaults (HSTS, X-Content-Type-Options,
 * X-Frame-Options, Referrer-Policy, etc.) are appropriate for an API and stay on.
 */
export function securityHeaders(): RequestHandler {
  return helmet({
    contentSecurityPolicy: false,
  });
}
