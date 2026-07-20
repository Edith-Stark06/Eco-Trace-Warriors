import { loadConfig } from '@shared/config';

describe('loadConfig', () => {
  it('applies documented defaults for an empty environment', () => {
    const config = loadConfig({});

    expect(config.nodeEnv).toBe('development');
    expect(config.port).toBe(3000);
    expect(config.apiPrefix).toBe('/api/v1');
    expect(config.logLevel).toBe('info');
    expect(config.databaseUrl).toBeUndefined();
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
    });

    expect(config.nodeEnv).toBe('production');
    expect(config.port).toBe(8080);
    expect(config.apiPrefix).toBe('/api/v2');
    expect(config.logLevel).toBe('warn');
    expect(config.databaseUrl).toBe('postgresql://user:pass@db:5432/ecotrace');
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

  it('returns a frozen (immutable) config object', () => {
    const config = loadConfig({});
    expect(Object.isFrozen(config)).toBe(true);
  });
});
