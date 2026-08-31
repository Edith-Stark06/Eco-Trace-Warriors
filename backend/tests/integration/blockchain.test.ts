import request from 'supertest';
import { createApp } from '../../src/app';
import { loadConfig } from '@shared/config';
import { createLogger } from '@shared/logging';
import type { BlockchainService } from '@modules/blockchain';

function buildTestApp(blockchainService?: BlockchainService): ReturnType<typeof createApp> {
  const config = loadConfig({ NODE_ENV: 'test', LOG_LEVEL: 'fatal' });
  const logger = createLogger(config);
  return createApp({ config, logger, blockchainService });
}

describe('GET /api/v1/system/blockchain/health', () => {
  it('is public — no Authorization header required', async () => {
    const fakeService: BlockchainService = {
      getHealth: () =>
        Promise.resolve({
          status: 'disabled',
          fabricEnabled: false,
          channel: null,
          chaincode: null,
          mspId: null,
          peerEndpoint: null,
          message: 'Fabric Gateway integration is disabled (FABRIC_ENABLED=false).',
          checkedAt: '2026-01-01T00:00:00.000Z',
          latencyMs: null,
        }),
    };

    const res = await request(buildTestApp(fakeService)).get('/api/v1/system/blockchain/health');

    expect(res.status).toBe(200);
    expect(res.body).toEqual({
      success: true,
      data: {
        status: 'disabled',
        fabricEnabled: false,
        channel: null,
        chaincode: null,
        mspId: null,
        peerEndpoint: null,
        message: 'Fabric Gateway integration is disabled (FABRIC_ENABLED=false).',
        checkedAt: '2026-01-01T00:00:00.000Z',
        latencyMs: null,
      },
    });
  });

  it('reflects a connected upstream status without alteration', async () => {
    const fakeService: BlockchainService = {
      getHealth: () =>
        Promise.resolve({
          status: 'connected',
          fabricEnabled: true,
          channel: 'ecotrace-channel',
          chaincode: 'ecotrace-lifecycle',
          mspId: 'EcoTraceOrgMSP',
          peerEndpoint: 'localhost:7051',
          message: 'Fabric Gateway peer is reachable.',
          checkedAt: '2026-01-01T00:00:00.000Z',
          latencyMs: 8.4,
        }),
    };

    const res = await request(buildTestApp(fakeService)).get('/api/v1/system/blockchain/health');

    expect(res.status).toBe(200);
    expect(res.body.data.status).toBe('connected');
    expect(res.body.data.latencyMs).toBe(8.4);
  });

  it('never returns a 5xx even when the upstream is unreachable — degrades to 200 proxy_unreachable', async () => {
    const fakeService: BlockchainService = {
      getHealth: () =>
        Promise.resolve({
          status: 'proxy_unreachable',
          fabricEnabled: null,
          channel: null,
          chaincode: null,
          mspId: null,
          peerEndpoint: null,
          message: 'Could not reach the device intelligence / Fabric Gateway service.',
          checkedAt: '2026-01-01T00:00:00.000Z',
          latencyMs: null,
        }),
    };

    const res = await request(buildTestApp(fakeService)).get('/api/v1/system/blockchain/health');

    expect(res.status).toBe(200);
    expect(res.body.data.status).toBe('proxy_unreachable');
  });

  it('performs a real (default, unmocked) health check against the configured URL without throwing', async () => {
    // Uses the real createBlockchainService (no override) pointed at the
    // default http://localhost:8100 — nothing is listening there in this
    // test run, so this exercises the actual network-failure degradation
    // path end-to-end, not just the injected-fake path above.
    const res = await request(buildTestApp()).get('/api/v1/system/blockchain/health');

    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.data.status).toBe('proxy_unreachable');
  });
});
