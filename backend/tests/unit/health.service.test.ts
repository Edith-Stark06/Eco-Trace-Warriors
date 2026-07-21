import { createHealthService } from '@modules/health';
import type { HealthService, HealthServiceDeps } from '@modules/health';
import { ServiceUnavailableError } from '@shared/errors';

function buildService(overrides: Partial<HealthServiceDeps> = {}): HealthService {
  return createHealthService({
    version: '1.2.3',
    serviceName: 'ecotrace-backend',
    environment: 'test',
    pingDatabase: () => Promise.resolve(true),
    ...overrides,
  });
}

describe('createHealthService', () => {
  describe('getStatus', () => {
    it('returns the documented envelope with injected clock and uptime', () => {
      const fixedDate = new Date('2026-07-21T10:00:00.000Z');
      const service = buildService({
        now: () => fixedDate,
        uptime: () => 42.5,
      });

      expect(service.getStatus()).toEqual({
        success: true,
        data: {
          status: 'ok',
          service: 'ecotrace-backend',
          version: '1.2.3',
          environment: 'test',
          uptime: 42.5,
          timestamp: '2026-07-21T10:00:00.000Z',
        },
      });
    });

    it('defaults to the process clock and uptime', () => {
      const status = buildService().getStatus();

      expect(Number.isNaN(Date.parse(status.data.timestamp))).toBe(false);
      expect(status.data.uptime).toBeGreaterThanOrEqual(0);
    });
  });

  describe('getReadiness', () => {
    it('reports ready when the database ping succeeds', async () => {
      const service = buildService({ pingDatabase: () => Promise.resolve(true) });

      await expect(service.getReadiness()).resolves.toEqual({
        success: true,
        data: { database: 'connected', ready: true },
      });
    });

    it('throws ServiceUnavailableError when the database ping fails', async () => {
      const service = buildService({ pingDatabase: () => Promise.resolve(false) });

      await expect(service.getReadiness()).rejects.toBeInstanceOf(ServiceUnavailableError);
    });
  });
});
