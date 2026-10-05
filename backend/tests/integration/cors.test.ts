import request from 'supertest';
import { createApp } from '../../src/app';
import { loadConfig } from '@shared/config';
import { createLogger } from '@shared/logging';
import { createInMemoryAuthRepositories } from '../helpers/in-memory-auth-repositories';

/**
 * CHANGE-008: cors.middleware.ts is a strict allowlist driven entirely by
 * CORS_ORIGINS (see its own module comment) — no wildcard/pattern support.
 * These tests pin down the exact origin set the local-dev compose stack
 * configures (docker-compose.yml's CORS_ORIGINS default), so a future
 * change to that default that silently drops an origin fails a test
 * instead of only surfacing as a browser CORS error days later.
 */
const LOCAL_DEV_CORS_ORIGINS = [
  'http://localhost:8080',
  'http://localhost:5173',
  'http://10.13.29.243:5173',
  'http://localhost:8081',
  'http://localhost:8082',
].join(',');

const TEST_ENV = {
  NODE_ENV: 'test',
  LOG_LEVEL: 'fatal',
  BCRYPT_ROUNDS: '4',
  AUTH_RATE_LIMIT_MAX: '1000',
  CORS_ORIGINS: LOCAL_DEV_CORS_ORIGINS,
} as const;

function buildTestApp(): ReturnType<typeof createApp> {
  const config = loadConfig(TEST_ENV);
  const logger = createLogger(config);
  return createApp({ config, logger, authRepositories: createInMemoryAuthRepositories() });
}

describe('CORS — local-dev origin allowlist (CHANGE-008)', () => {
  it.each(['http://localhost:8082', 'http://localhost:8081', 'http://localhost:5173'])(
    'grants Access-Control-Allow-Origin to the allowed origin %s',
    async (origin) => {
      const res = await request(buildTestApp())
        .options('/api/v1/auth/login')
        .set('Origin', origin)
        .set('Access-Control-Request-Method', 'POST')
        .set('Access-Control-Request-Headers', 'content-type');

      expect(res.headers['access-control-allow-origin']).toBe(origin);
    },
  );

  it('does NOT grant an unrelated origin', async () => {
    const res = await request(buildTestApp())
      .options('/api/v1/auth/login')
      .set('Origin', 'http://evil.example')
      .set('Access-Control-Request-Method', 'POST')
      .set('Access-Control-Request-Headers', 'content-type');

    expect(res.headers['access-control-allow-origin']).toBeUndefined();
  });

  it('never emits a wildcard Access-Control-Allow-Origin, even for an allowed origin', async () => {
    const res = await request(buildTestApp())
      .options('/api/v1/auth/login')
      .set('Origin', 'http://localhost:8082')
      .set('Access-Control-Request-Method', 'POST')
      .set('Access-Control-Request-Headers', 'content-type');

    expect(res.headers['access-control-allow-origin']).not.toBe('*');
  });

  it('preserves Access-Control-Allow-Credentials for an allowed origin (credentials: true, cors.middleware.ts)', async () => {
    const res = await request(buildTestApp())
      .options('/api/v1/auth/login')
      .set('Origin', 'http://localhost:8082')
      .set('Access-Control-Request-Method', 'POST')
      .set('Access-Control-Request-Headers', 'content-type');

    expect(res.headers['access-control-allow-credentials']).toBe('true');
  });

  it('completes the POST /api/v1/auth/login preflight for an allowed Collector origin', async () => {
    const res = await request(buildTestApp())
      .options('/api/v1/auth/login')
      .set('Origin', 'http://localhost:8082')
      .set('Access-Control-Request-Method', 'POST')
      .set('Access-Control-Request-Headers', 'content-type');

    expect(res.status).toBeLessThan(300);
    expect(res.headers['access-control-allow-origin']).toBe('http://localhost:8082');
    expect(res.headers['access-control-allow-methods']).toBeDefined();
  });

  it('rejects an unlisted origin on the actual (non-preflight) request too', async () => {
    const res = await request(buildTestApp())
      .post('/api/v1/auth/login')
      .set('Origin', 'http://evil.example')
      .send({ email: 'nobody@example.com', password: 'irrelevant' });

    expect(res.headers['access-control-allow-origin']).toBeUndefined();
  });
});
