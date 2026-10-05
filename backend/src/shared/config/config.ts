import { envSchema } from './env.schema';

/** Immutable, typed application configuration derived from the environment. */
export interface AppConfig {
  readonly nodeEnv: 'development' | 'test' | 'production';
  readonly port: number;
  readonly apiPrefix: string;
  readonly logLevel: 'fatal' | 'error' | 'warn' | 'info' | 'debug' | 'trace';
  readonly databaseUrl: string | undefined;
  /** Allowlist of browser origins permitted by CORS. */
  readonly corsOrigins: readonly string[];
  readonly jwtSecret: string;
  readonly jwtRefreshSecret: string;
  readonly jwtAccessExpiry: string;
  readonly jwtRefreshExpiry: string;
  readonly bcryptRounds: number;
  /** Rate limiting for the authentication endpoints. */
  readonly authRateLimit: {
    /** Sliding window length in milliseconds. */
    readonly windowMs: number;
    /** Max requests permitted per IP within the window. */
    readonly max: number;
  };
  /** General-purpose API rate limiting, applied globally (P7.4). */
  readonly apiRateLimit: {
    readonly windowMs: number;
    readonly max: number;
  };
  readonly isProduction: boolean;
  readonly isTest: boolean;
  /** Base URL of the Python `intelligence/device_ai` service (P6.5 blockchain proxy). */
  readonly deviceAiServiceUrl: string;
  /** Timeout (ms) for the blockchain health proxy request. */
  readonly deviceAiTimeoutMs: number;
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
    corsOrigins: parsed.CORS_ORIGINS,
    jwtSecret: parsed.JWT_SECRET,
    jwtRefreshSecret: parsed.JWT_REFRESH_SECRET,
    jwtAccessExpiry: parsed.JWT_ACCESS_EXPIRY,
    jwtRefreshExpiry: parsed.JWT_REFRESH_EXPIRY,
    bcryptRounds: parsed.BCRYPT_ROUNDS,
    authRateLimit: {
      windowMs: parsed.AUTH_RATE_LIMIT_WINDOW_MS,
      max: parsed.AUTH_RATE_LIMIT_MAX,
    },
    apiRateLimit: {
      windowMs: parsed.API_RATE_LIMIT_WINDOW_MS,
      max: parsed.API_RATE_LIMIT_MAX,
    },
    isProduction: parsed.NODE_ENV === 'production',
    isTest: parsed.NODE_ENV === 'test',
    deviceAiServiceUrl: parsed.DEVICE_AI_SERVICE_URL,
    deviceAiTimeoutMs: parsed.DEVICE_AI_TIMEOUT_MS,
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
