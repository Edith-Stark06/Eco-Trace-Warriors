import { z } from 'zod';

/**
 * Query schema for GET /analytics/forecast. Mirrors the coercion pattern in
 * shared/pagination/pagination.schema.ts: values arrive as query-string
 * strings, so they are coerced to numbers here; out-of-range or non-numeric
 * values fail validation and the `validate` middleware returns 400.
 */
export const DEFAULT_FORECAST_HORIZON = 30;
export const MAX_FORECAST_HORIZON = 90;

export const forecastQuerySchema = z.object({
  horizon: z.coerce
    .number({ invalid_type_error: 'horizon must be a number' })
    .int('horizon must be an integer')
    .min(1, 'horizon must be at least 1')
    .max(MAX_FORECAST_HORIZON, `horizon must be at most ${MAX_FORECAST_HORIZON}`)
    .default(DEFAULT_FORECAST_HORIZON),
});

/** Validated, coerced forecast query parameters passed from controller to service. */
export type ForecastQuery = z.infer<typeof forecastQuerySchema>;
