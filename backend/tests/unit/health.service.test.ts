import { createHealthService } from '@modules/health';

describe('createHealthService', () => {
  it('returns the documented status shape with injected clock and uptime', () => {
    const fixedDate = new Date('2026-07-21T10:00:00.000Z');
    const service = createHealthService({
      version: '1.2.3',
      now: () => fixedDate,
      uptime: () => 42.5,
    });

    expect(service.getStatus()).toEqual({
      success: true,
      message: 'EcoTrace Backend is running',
      version: '1.2.3',
      timestamp: '2026-07-21T10:00:00.000Z',
      uptime: 42.5,
    });
  });

  it('defaults to the process clock and uptime', () => {
    const service = createHealthService({ version: '0.1.0' });
    const status = service.getStatus();

    expect(Number.isNaN(Date.parse(status.timestamp))).toBe(false);
    expect(status.uptime).toBeGreaterThanOrEqual(0);
  });
});
