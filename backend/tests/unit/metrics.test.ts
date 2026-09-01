import { createMetricsRegistry } from '@shared/metrics';

describe('createMetricsRegistry', () => {
  it('starts with an empty snapshot', () => {
    const registry = createMetricsRegistry();
    const snapshot = registry.snapshot();

    expect(snapshot.requests.total).toBe(0);
    expect(snapshot.requests.byRoute).toEqual([]);
    expect(snapshot.blockchain).toEqual({
      checks: 0,
      connected: 0,
      unavailable: 0,
      proxyUnreachable: 0,
    });
  });

  it('aggregates request count, average latency, and status counts per route', () => {
    const registry = createMetricsRegistry();

    registry.recordRequest('GET', '/api/v1/health', 200, 10);
    registry.recordRequest('GET', '/api/v1/health', 200, 20);
    registry.recordRequest('GET', '/api/v1/health', 500, 30);

    const snapshot = registry.snapshot();

    expect(snapshot.requests.total).toBe(3);
    expect(snapshot.requests.byRoute).toEqual([
      {
        method: 'GET',
        route: '/api/v1/health',
        count: 3,
        avgDurationMs: 20,
        statusCounts: { '200': 2, '500': 1 },
      },
    ]);
  });

  it('keeps distinct routes and methods separate', () => {
    const registry = createMetricsRegistry();

    registry.recordRequest('GET', '/api/v1/submissions', 200, 5);
    registry.recordRequest('POST', '/api/v1/submissions', 201, 15);

    const snapshot = registry.snapshot();
    expect(snapshot.requests.byRoute).toHaveLength(2);
    expect(snapshot.requests.total).toBe(2);
  });

  it('classifies blockchain check outcomes into connected / unavailable / proxy_unreachable buckets', () => {
    const registry = createMetricsRegistry();

    registry.recordBlockchainCheck('connected');
    registry.recordBlockchainCheck('disabled');
    registry.recordBlockchainCheck('configuration_error');
    registry.recordBlockchainCheck('unavailable');
    registry.recordBlockchainCheck('proxy_unreachable');

    const snapshot = registry.snapshot();
    expect(snapshot.blockchain).toEqual({
      checks: 5,
      connected: 1,
      unavailable: 3, // disabled + configuration_error + unavailable all count as "not connected"
      proxyUnreachable: 1,
    });
  });

  it('reports a non-negative uptime that increases with elapsed time', () => {
    let clock = 1000;
    const registry = createMetricsRegistry(() => clock);

    expect(registry.snapshot().uptimeSeconds).toBe(0);
    clock += 2500;
    expect(registry.snapshot().uptimeSeconds).toBe(2.5);
  });

  it('reset() clears all recorded data', () => {
    const registry = createMetricsRegistry();
    registry.recordRequest('GET', '/api/v1/health', 200, 10);
    registry.recordBlockchainCheck('connected');

    registry.reset();

    const snapshot = registry.snapshot();
    expect(snapshot.requests.total).toBe(0);
    expect(snapshot.blockchain.checks).toBe(0);
  });
});
