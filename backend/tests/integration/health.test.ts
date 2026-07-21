import request from 'supertest';
import { createApp } from '../../src/app';
import { loadConfig } from '@shared/config';
import { createLogger } from '@shared/logging';

function buildTestApp(): ReturnType<typeof createApp> {
  const config = loadConfig({ NODE_ENV: 'test', LOG_LEVEL: 'fatal' });
  const logger = createLogger(config);
  return createApp({ config, logger });
}

describe('GET /api/v1/health', () => {
  it('returns 200 with the documented health envelope', async () => {
    const res = await request(buildTestApp()).get('/api/v1/health');

    expect(res.status).toBe(200);
    expect(res.body).toEqual({
      success: true,
      data: {
        status: 'ok',
        service: 'ecotrace-backend',
        version: expect.stringMatching(/^\d+\.\d+\.\d+/),
        environment: 'test',
        uptime: expect.any(Number),
        timestamp: expect.any(String),
      },
    });
  });

  it('returns a valid ISO timestamp and non-negative uptime', async () => {
    const res = await request(buildTestApp()).get('/api/v1/health');

    expect(Number.isNaN(Date.parse(res.body.data.timestamp))).toBe(false);
    expect(res.body.data.uptime).toBeGreaterThanOrEqual(0);
  });

  it('echoes a provided X-Request-Id header', async () => {
    const res = await request(buildTestApp())
      .get('/api/v1/health')
      .set('X-Request-Id', 'test-correlation-id');

    expect(res.headers['x-request-id']).toBe('test-correlation-id');
  });

  it('generates an X-Request-Id when none is provided', async () => {
    const res = await request(buildTestApp()).get('/api/v1/health');

    expect(res.headers['x-request-id']).toEqual(expect.any(String));
    expect(res.headers['x-request-id']).not.toHaveLength(0);
  });
});

describe('GET /api/v1', () => {
  it('returns 200 with the documented API info envelope', async () => {
    const res = await request(buildTestApp()).get('/api/v1');

    expect(res.status).toBe(200);
    expect(res.body).toEqual({
      success: true,
      data: {
        name: 'EcoTrace India Backend API',
        version: 'v1',
        environment: 'test',
        documentation: '/api/v1/docs',
      },
    });
  });
});

describe('GET /api/v1/ready', () => {
  it('returns 503 with the error envelope when the database is unreachable', async () => {
    // The test environment has no database running, so the Prisma ping fails
    // and the service maps it to SERVICE_UNAVAILABLE via the global handler.
    const res = await request(buildTestApp()).get('/api/v1/ready');

    expect(res.status).toBe(503);
    expect(res.body).toEqual({
      success: false,
      error: {
        code: 'SERVICE_UNAVAILABLE',
        message: expect.any(String),
      },
    });
  });
});

describe('unknown routes', () => {
  it('returns 404 with the documented error envelope', async () => {
    const res = await request(buildTestApp()).get('/api/v1/does-not-exist');

    expect(res.status).toBe(404);
    expect(res.body).toEqual({
      success: false,
      error: {
        code: 'NOT_FOUND',
        message: expect.any(String),
      },
    });
  });
});
