import { loadConfig } from '@shared/config';

describe('loadConfig', () => {
  it('applies documented defaults for an empty environment', () => {
    const config = loadConfig({});

    expect(config.nodeEnv).toBe('development');
    expect(config.port).toBe(3000);
    expect(config.apiPrefix).toBe('/api/v1');
    expect(config.logLevel).toBe('info');
    expect(config.databaseUrl).toBeUndefined();
    expect(config.corsOrigins).toEqual(['http://localhost:5173']);
    expect(config.jwtSecret).toMatch(/^dev-insecure-/);
    expect(config.jwtRefreshSecret).toMatch(/^dev-insecure-/);
    expect(config.jwtAccessExpiry).toBe('15m');
    expect(config.jwtRefreshExpiry).toBe('7d');
    expect(config.bcryptRounds).toBe(10);
    expect(config.authRateLimit).toEqual({ windowMs: 15 * 60 * 1000, max: 10 });
    expect(config.isProduction).toBe(false);
    expect(config.isTest).toBe(false);
  });

  it('parses explicit values', () => {
    const config = loadConfig({
      NODE_ENV: 'production',
      PORT: '8080',
      API_PREFIX: '/api/v2',
      LOG_LEVEL: 'warn',
      DATABASE_URL: 'postgresql://user:pass@db:5432/ecotrace',
      JWT_SECRET: 'a-strong-production-access-secret-0123456789',
      JWT_REFRESH_SECRET: 'a-strong-production-refresh-secret-0123456789',
      JWT_ACCESS_EXPIRY: '5m',
      JWT_REFRESH_EXPIRY: '30d',
      BCRYPT_ROUNDS: '12',
      AUTH_RATE_LIMIT_WINDOW_MS: '60000',
      AUTH_RATE_LIMIT_MAX: '5',
    });

    expect(config.nodeEnv).toBe('production');
    expect(config.port).toBe(8080);
    expect(config.apiPrefix).toBe('/api/v2');
    expect(config.logLevel).toBe('warn');
    expect(config.databaseUrl).toBe('postgresql://user:pass@db:5432/ecotrace');
    expect(config.jwtSecret).toBe('a-strong-production-access-secret-0123456789');
    expect(config.jwtRefreshSecret).toBe('a-strong-production-refresh-secret-0123456789');
    expect(config.jwtAccessExpiry).toBe('5m');
    expect(config.jwtRefreshExpiry).toBe('30d');
    expect(config.bcryptRounds).toBe(12);
    expect(config.authRateLimit).toEqual({ windowMs: 60000, max: 5 });
    expect(config.isProduction).toBe(true);
  });

  it('rejects an invalid NODE_ENV', () => {
    expect(() => loadConfig({ NODE_ENV: 'staging' })).toThrow(/Invalid environment configuration/);
  });

  it('rejects a non-numeric PORT', () => {
    expect(() => loadConfig({ PORT: 'not-a-port' })).toThrow(/Invalid environment configuration/);
  });

  it('rejects an out-of-range PORT', () => {
    expect(() => loadConfig({ PORT: '70000' })).toThrow(/Invalid environment configuration/);
  });

  it('rejects an API_PREFIX that does not start with a slash', () => {
    expect(() => loadConfig({ API_PREFIX: 'api/v1' })).toThrow(/API_PREFIX/);
  });

  it('rejects a malformed DATABASE_URL', () => {
    expect(() => loadConfig({ DATABASE_URL: 'not-a-url' })).toThrow(
      /Invalid environment configuration/,
    );
  });

  it('rejects placeholder JWT secrets in production', () => {
    expect(() => loadConfig({ NODE_ENV: 'production' })).toThrow(
      /JWT_SECRET must be set to a strong value in production/,
    );
  });

  it('rejects identical access and refresh secrets in production', () => {
    expect(() =>
      loadConfig({
        NODE_ENV: 'production',
        JWT_SECRET: 'a-strong-production-secret-shared-0123456789',
        JWT_REFRESH_SECRET: 'a-strong-production-secret-shared-0123456789',
      }),
    ).toThrow(/JWT_REFRESH_SECRET must differ from JWT_SECRET/);
  });

  it('rejects a too-short JWT_SECRET', () => {
    expect(() => loadConfig({ JWT_SECRET: 'short' })).toThrow(/JWT_SECRET/);
  });

  it('rejects an out-of-range BCRYPT_ROUNDS', () => {
    expect(() => loadConfig({ BCRYPT_ROUNDS: '20' })).toThrow(/Invalid environment configuration/);
  });

  it('rejects a non-numeric AUTH_RATE_LIMIT_MAX', () => {
    expect(() => loadConfig({ AUTH_RATE_LIMIT_MAX: 'lots' })).toThrow(
      /Invalid environment configuration/,
    );
  });

  it('rejects an AUTH_RATE_LIMIT_WINDOW_MS below the minimum', () => {
    expect(() => loadConfig({ AUTH_RATE_LIMIT_WINDOW_MS: '10' })).toThrow(
      /Invalid environment configuration/,
    );
  });

  it('returns a frozen (immutable) config object', () => {
    const config = loadConfig({});
    expect(Object.isFrozen(config)).toBe(true);
  });

  it('parses CORS_ORIGINS into a trimmed, non-empty allowlist', () => {
    const config = loadConfig({
      CORS_ORIGINS: 'https://app.ecotrace.in, https://admin.ecotrace.in ,,  ',
    });

    expect(config.corsOrigins).toEqual(['https://app.ecotrace.in', 'https://admin.ecotrace.in']);
  });
});
