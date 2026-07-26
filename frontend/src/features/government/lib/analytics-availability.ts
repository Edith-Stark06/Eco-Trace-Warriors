/**
 * Government analytics availability helpers.
 *
 * The backend Analytics module is documented but may not be deployed on a given
 * backend instance. When it is absent, the analytics endpoints respond with
 * HTTP 404. Per product decision, that specific case is treated as an expected
 * "feature unavailable" condition and surfaced with a dedicated informational
 * empty state — NOT a generic server error.
 *
 * These helpers classify a thrown query error into that distinction. They
 * contain no data and no business logic beyond error classification.
 */
import { isAxiosError } from 'axios';

/**
 * True when the error represents an HTTP 404 — i.e. the analytics endpoint does
 * not exist on this backend instance (Analytics module not yet deployed).
 */
export function isAnalyticsUnavailable(error: unknown): boolean {
  return isAxiosError(error) && error.response?.status === 404;
}

/**
 * True for any other failure (network, 5xx, unexpected) that should surface the
 * generic server-error screen with a retry action.
 */
export function isUnexpectedAnalyticsError(error: unknown): boolean {
  return Boolean(error) && !isAnalyticsUnavailable(error);
}
