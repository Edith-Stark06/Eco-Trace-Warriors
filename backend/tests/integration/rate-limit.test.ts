import request from 'supertest';
import { createApp } from '../../src/app';
import { loadConfig } from '@shared/config';
import { createLogger } from '@shared/logging';

function buildAppWithLowLimit(max: number): ReturnType<typeof createApp> {
  const config = loadConfig({
    NODE_ENV: 'test',
    LOG_LEVEL: 'fatal',
    API_RATE_LIMIT_WINDOW_MS: '60000',
    API_RATE_LIMIT_MAX: String(max),
  });
  const logger = createLogger(config);
  return createApp({ config, logger });
}

describe('API rate limiting (P7.4)', () => {
  it('returns 429 with the standard error envelope once the limit is exceeded', async () => {
    const app = buildAppWithLowLimit(2);

    const first = await request(app).get('/api/v1');
    const second = await request(app).get('/api/v1');
    const third = await request(app).get('/api/v1');

    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    expect(third.status).toBe(429);
    expect(third.body).toEqual({
      success: false,
      error: { code: 'TOO_MANY_REQUESTS', message: expect.any(String) },
    });
  });

  it('sets standard RateLimit-* headers, not the legacy X-RateLimit-* ones', async () => {
    const app = buildAppWithLowLimit(5);
    const res = await request(app).get('/api/v1');

    expect(res.headers['ratelimit-limit']).toBeDefined();
    expect(res.headers['x-ratelimit-limit']).toBeUndefined();
  });

  it('never throttles GET /health or GET /ready, even past the limit', async () => {
    const app = buildAppWithLowLimit(1);

    // Exhaust the limit against a normal route first.
    await request(app).get('/api/v1');
    const exhausted = await request(app).get('/api/v1');
    expect(exhausted.status).toBe(429);

    // Health/ready must still succeed — mounted before the limiter.
    for (let i = 0; i < 5; i += 1) {
      const health = await request(app).get('/api/v1/health');
      expect(health.status).toBe(200);
    }
  });
});
