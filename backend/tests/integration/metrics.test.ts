import request from 'supertest';
import { createApp } from '../../src/app';
import { loadConfig } from '@shared/config';
import { createLogger } from '@shared/logging';
import { createMetricsRegistry } from '@shared/metrics';
import { createBlockchainService } from '@modules/blockchain';

function buildTestApp(): ReturnType<typeof createApp> {
  const config = loadConfig({ NODE_ENV: 'test', LOG_LEVEL: 'fatal' });
  const logger = createLogger(config);
  return createApp({ config, logger });
}

describe('GET /api/v1/metrics', () => {
  it('returns 200 with an empty-but-shaped snapshot before any traffic', async () => {
    const res = await request(buildTestApp()).get('/api/v1/metrics');

    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.data).toMatchObject({
      uptimeSeconds: expect.any(Number),
      requests: { total: expect.any(Number), byRoute: expect.any(Array) },
      blockchain: { checks: expect.any(Number) },
    });
  });

  it('records prior requests to other routes by their matched route pattern', async () => {
    const app = buildTestApp();

    await request(app).get('/api/v1/health');
    await request(app).get('/api/v1/health');
    const res = await request(app).get('/api/v1/metrics');

    const byRoute = res.body.data.requests.byRoute as Array<{
      method: string;
      route: string;
      count: number;
      avgDurationMs: number;
    }>;
    const healthEntry = byRoute.find((r) => r.method === 'GET' && r.route === '/api/v1/health');
    expect(healthEntry).toBeDefined();
    expect(healthEntry?.count).toBeGreaterThanOrEqual(2);
    expect(healthEntry?.avgDurationMs).toBeGreaterThanOrEqual(0);
  });

  it('records a blockchain check outcome when the blockchain health route is hit', async () => {
    const config = loadConfig({ NODE_ENV: 'test', LOG_LEVEL: 'fatal' });
    const logger = createLogger(config);
    const metricsRegistry = createMetricsRegistry();
    const blockchainService = createBlockchainService({
      deviceAiServiceUrl: 'http://device-ai.internal:8100',
      timeoutMs: 1000,
      logger,
      fetchImpl: () => Promise.reject(new Error('ECONNREFUSED')),
      onCheck: (status) => metricsRegistry.recordBlockchainCheck(status),
    });
    const app = createApp({ config, logger, metricsRegistry, blockchainService });

    await request(app).get('/api/v1/system/blockchain/health');
    const res = await request(app).get('/api/v1/metrics');

    expect(res.body.data.blockchain.checks).toBe(1);
    expect(res.body.data.blockchain.proxyUnreachable).toBe(1);
  });
});
