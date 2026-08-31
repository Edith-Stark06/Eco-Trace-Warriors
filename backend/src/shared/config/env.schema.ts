import { z } from 'zod';

/** Development placeholder prefix — rejected in production by the refinement below. */
const DEV_SECRET_PREFIX = 'dev-insecure-';

/**
 * Zod schema for all environment variables the backend reads.
 * Parsing happens once at startup (fail fast) — see loadConfig().
 *
 * JWT secrets default to obvious placeholders so local development and tests
 * work with an empty environment; production rejects the placeholders.
 */
export const envSchema = z
  .object({
    NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
    PORT: z.coerce.number().int().min(1).max(65535).default(3000),
    API_PREFIX: z
      .string()
      .regex(/^\/[a-z0-9/-]*$/i, 'API_PREFIX must start with "/"')
      .default('/api/v1'),
    LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace']).default('info'),
    DATABASE_URL: z.string().url().optional(),
    // Comma-separated allowlist of browser origins permitted by CORS.
    // Parsed into a trimmed, non-empty string[]; empty/whitespace entries are dropped.
    CORS_ORIGINS: z
      .string()
      .default('http://localhost:5173')
      .transform((value) =>
        value
          .split(',')
          .map((origin) => origin.trim())
          .filter((origin) => origin.length > 0),
      ),
    JWT_SECRET: z
      .string()
      .min(32, 'JWT_SECRET must be at least 32 characters')
      .default(`${DEV_SECRET_PREFIX}access-secret-change-me-00000000`),
    JWT_REFRESH_SECRET: z
      .string()
      .min(32, 'JWT_REFRESH_SECRET must be at least 32 characters')
      .default(`${DEV_SECRET_PREFIX}refresh-secret-change-me-0000000`),
    JWT_ACCESS_EXPIRY: z.string().min(1).default('15m'),
    JWT_REFRESH_EXPIRY: z.string().min(1).default('7d'),
    BCRYPT_ROUNDS: z.coerce.number().int().min(4).max(15).default(10),
    // Auth rate limiting — window length and max requests per IP per window.
    // Applies only to the authentication endpoints (see auth router).
    AUTH_RATE_LIMIT_WINDOW_MS: z.coerce
      .number()
      .int()
      .min(1000)
      .default(15 * 60 * 1000),
    AUTH_RATE_LIMIT_MAX: z.coerce.number().int().min(1).default(10),
    // Base URL of the Python `intelligence/device_ai` service — the P6.1/P6.2
    // Fabric Gateway integration lives there (see
    // `intelligence/device_ai/api/blockchain_routes.py`). This backend does
    // not hold its own Fabric connection; the blockchain module proxies a
    // read-only health check to this URL (P6.5).
    DEVICE_AI_SERVICE_URL: z.string().url().default('http://localhost:8100'),
    DEVICE_AI_TIMEOUT_MS: z.coerce.number().int().min(100).default(5000),
  })
  .superRefine((env, ctx) => {
    if (env.NODE_ENV !== 'production') return;

    if (!env.DATABASE_URL) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['DATABASE_URL'],
        message: 'DATABASE_URL is required in production',
      });
    }
    if (env.JWT_SECRET.startsWith(DEV_SECRET_PREFIX)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['JWT_SECRET'],
        message: 'JWT_SECRET must be set to a strong value in production',
      });
    }
    if (env.JWT_REFRESH_SECRET.startsWith(DEV_SECRET_PREFIX)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['JWT_REFRESH_SECRET'],
        message: 'JWT_REFRESH_SECRET must be set to a strong value in production',
      });
    }
    if (env.JWT_SECRET === env.JWT_REFRESH_SECRET) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['JWT_REFRESH_SECRET'],
        message: 'JWT_REFRESH_SECRET must differ from JWT_SECRET',
      });
    }
  });

export type Env = z.infer<typeof envSchema>;
