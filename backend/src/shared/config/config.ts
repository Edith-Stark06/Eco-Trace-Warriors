import { envSchema } from './env.schema';

/** Immutable, typed application configuration derived from the environment. */
export interface AppConfig {
  readonly nodeEnv: 'development' | 'test' | 'production';
  readonly port: number;
  readonly apiPrefix: string;
  readonly logLevel: 'fatal' | 'error' | 'warn' | 'info' | 'debug' | 'trace';
  readonly databaseUrl: string | undefined;
  readonly jwtSecret: string;
  readonly jwtRefreshSecret: string;
  readonly jwtAccessExpiry: string;
  readonly jwtRefreshExpiry: string;
  readonly bcryptRounds: number;
  readonly isProduction: boolean;
  readonly isTest: boolean;
}

/**
 * Parses and validates the given environment into an AppConfig.
 * Throws with a readable message when validation fails so the process fails fast.
 */
export function loadConfig(env: NodeJS.ProcessEnv = process.env): AppConfig {
  const result = envSchema.safeParse(env);

  if (!result.success) {
    const issues = result.error.issues
      .map((issue) => `${issue.path.join('.')}: ${issue.message}`)
      .join('; ');
    throw new Error(`Invalid environment configuration — ${issues}`);
  }

  const parsed = result.data;

  return Object.freeze({
    nodeEnv: parsed.NODE_ENV,
    port: parsed.PORT,
    apiPrefix: parsed.API_PREFIX,
    logLevel: parsed.LOG_LEVEL,
    databaseUrl: parsed.DATABASE_URL,
    jwtSecret: parsed.JWT_SECRET,
    jwtRefreshSecret: parsed.JWT_REFRESH_SECRET,
    jwtAccessExpiry: parsed.JWT_ACCESS_EXPIRY,
    jwtRefreshExpiry: parsed.JWT_REFRESH_EXPIRY,
    bcryptRounds: parsed.BCRYPT_ROUNDS,
    isProduction: parsed.NODE_ENV === 'production',
    isTest: parsed.NODE_ENV === 'test',
  });
}

let cachedConfig: AppConfig | undefined;

/** Returns the process-wide configuration, loading it on first access. */
export function getConfig(): AppConfig {
  cachedConfig ??= loadConfig();
  return cachedConfig;
}

/** Test-only: clears the cached configuration. */
export function resetConfigForTesting(): void {
  cachedConfig = undefined;
}
