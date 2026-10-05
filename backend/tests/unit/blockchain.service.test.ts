import { createBlockchainService } from '@modules/blockchain';
import type { BlockchainService, BlockchainServiceDeps } from '@modules/blockchain';
import { createLogger } from '@shared/logging';

const silentLogger = createLogger({ logLevel: 'fatal', nodeEnv: 'test' });

function buildService(
  fetchImpl: typeof fetch,
  overrides: Partial<BlockchainServiceDeps> = {},
): BlockchainService {
  return createBlockchainService({
    deviceAiServiceUrl: 'http://device-ai.internal:8100',
    timeoutMs: 5000,
    logger: silentLogger,
    fetchImpl,
    ...overrides,
  });
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('createBlockchainService', () => {
  describe('getHealth', () => {
    it('maps a successful device_ai response into the backend shape', async () => {
      const fetchMock = jest.fn((url: string | URL) => {
        expect(url).toBe('http://device-ai.internal:8100/system/blockchain/health');
        return Promise.resolve(
          jsonResponse({
            success: true,
            health: {
              status: 'connected',
              fabric_enabled: true,
              channel: 'ecotrace-channel',
              chaincode: 'ecotrace-lifecycle',
              msp_id: 'EcoTraceOrgMSP',
              peer_endpoint: 'localhost:7051',
              message: 'Fabric Gateway peer is reachable.',
              checked_at: '2026-01-01T00:00:00.000Z',
              latency_ms: 12.3,
            },
          }),
        );
      }) as unknown as typeof fetch;

      const service = buildService(fetchMock);
      const health = await service.getHealth();

      expect(health).toEqual({
        status: 'connected',
        fabricEnabled: true,
        channel: 'ecotrace-channel',
        chaincode: 'ecotrace-lifecycle',
        mspId: 'EcoTraceOrgMSP',
        peerEndpoint: 'localhost:7051',
        message: 'Fabric Gateway peer is reachable.',
        checkedAt: '2026-01-01T00:00:00.000Z',
        latencyMs: 12.3,
      });
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it('reports the disabled state faithfully (not fabricated as connected)', async () => {
      const fetchMock = jest.fn(() =>
        Promise.resolve(
          jsonResponse({
            success: true,
            health: {
              status: 'disabled',
              fabric_enabled: false,
              channel: 'ecotrace-channel',
              chaincode: 'ecotrace-lifecycle',
              msp_id: 'EcoTraceOrgMSP',
              peer_endpoint: 'localhost:7051',
              message: 'Fabric Gateway integration is disabled (FABRIC_ENABLED=false).',
              checked_at: '2026-01-01T00:00:00.000Z',
              latency_ms: null,
            },
          }),
        ),
      ) as unknown as typeof fetch;

      const health = await buildService(fetchMock).getHealth();

      expect(health.status).toBe('disabled');
      expect(health.fabricEnabled).toBe(false);
      expect(health.latencyMs).toBeNull();
    });

    it('degrades to proxy_unreachable on a network failure, without throwing', async () => {
      const fetchMock = jest.fn(() =>
        Promise.reject(new Error('ECONNREFUSED')),
      ) as unknown as typeof fetch;

      const health = await buildService(fetchMock).getHealth();

      expect(health.status).toBe('proxy_unreachable');
      expect(health.fabricEnabled).toBeNull();
      expect(health.message).toContain('Could not reach');
    });

    it('degrades to proxy_unreachable on a non-OK HTTP response', async () => {
      const fetchMock = jest.fn(() =>
        Promise.resolve(jsonResponse({}, 502)),
      ) as unknown as typeof fetch;

      const health = await buildService(fetchMock).getHealth();

      expect(health.status).toBe('proxy_unreachable');
      expect(health.message).toContain('502');
    });

    it('degrades to proxy_unreachable when the response shape is unexpected', async () => {
      const fetchMock = jest.fn(() =>
        Promise.resolve(jsonResponse({ unexpected: true })),
      ) as unknown as typeof fetch;

      const health = await buildService(fetchMock).getHealth();

      expect(health.status).toBe('proxy_unreachable');
    });

    it('trims a trailing slash from the configured base URL', async () => {
      const fetchMock = jest.fn((url: string | URL) => {
        expect(url).toBe('http://device-ai.internal:8100/system/blockchain/health');
        return Promise.resolve(
          jsonResponse({
            success: true,
            health: { status: 'disabled', message: 'disabled' },
          }),
        );
      }) as unknown as typeof fetch;

      await buildService(fetchMock, {
        deviceAiServiceUrl: 'http://device-ai.internal:8100/',
      }).getHealth();

      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it('never mutates or writes anything — purely a read-through proxy', () => {
      // The service has no repository/database dependency at all; this test
      // documents that invariant so a future change can't silently add one
      // without a reviewer noticing the constructor signature grew.
      const deps: BlockchainServiceDeps = {
        deviceAiServiceUrl: 'http://device-ai.internal:8100',
        timeoutMs: 5000,
        logger: silentLogger,
        fetchImpl: () =>
          Promise.resolve(jsonResponse({ success: true, health: { status: 'disabled' } })),
      };
      expect(Object.keys(deps).sort()).toEqual(
        ['deviceAiServiceUrl', 'fetchImpl', 'logger', 'timeoutMs'].sort(),
      );
    });

    it('invokes onCheck with the resolved status on both success and degraded outcomes (P7.3)', async () => {
      const observed: string[] = [];
      const okFetch = jest.fn(() =>
        Promise.resolve(jsonResponse({ success: true, health: { status: 'disabled' } })),
      ) as unknown as typeof fetch;

      await buildService(okFetch, { onCheck: (status) => observed.push(status) }).getHealth();

      const failingFetch = jest.fn(() =>
        Promise.reject(new Error('ECONNREFUSED')),
      ) as unknown as typeof fetch;
      await buildService(failingFetch, { onCheck: (status) => observed.push(status) }).getHealth();

      expect(observed).toEqual(['disabled', 'proxy_unreachable']);
    });
  });
});
