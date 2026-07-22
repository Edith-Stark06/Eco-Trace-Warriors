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
  })
  .superRefine((env, ctx) => {
    if (env.NODE_ENV !== 'production') return;

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
