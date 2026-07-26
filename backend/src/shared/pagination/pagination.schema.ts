import { z } from 'zod';

/**
 * Offset-based pagination for list endpoints. Applied via the validate
 * middleware as a query schema — see docs/engineering/05_API.md (Pagination).
 *
 * Defaults keep existing (paginationless) requests working: a caller that omits
 * both parameters gets the first 50 rows. Values are coerced from the query
 * string, so `?limit=20&offset=40` arrives as numbers. Out-of-range or
 * non-numeric values fail validation → 400.
 */
export const DEFAULT_PAGINATION_LIMIT = 50;
export const MAX_PAGINATION_LIMIT = 100;

export const paginationQuerySchema = z.object({
  limit: z.coerce
    .number({ invalid_type_error: 'limit must be a number' })
    .int('limit must be an integer')
    .min(1, 'limit must be at least 1')
    .max(MAX_PAGINATION_LIMIT, `limit must be at most ${MAX_PAGINATION_LIMIT}`)
    .default(DEFAULT_PAGINATION_LIMIT),
  offset: z.coerce
    .number({ invalid_type_error: 'offset must be a number' })
    .int('offset must be an integer')
    .min(0, 'offset must be at least 0')
    .default(0),
});

/** Validated, coerced pagination parameters passed from controllers to services. */
export type Pagination = z.infer<typeof paginationQuerySchema>;
