import { ServiceUnavailableError } from '@shared/errors';
import type { HealthData, HealthResponse, ReadinessResponse } from './health.types';

/** Dependencies injected into the health service. */
export interface HealthServiceDeps {
  /** Application version, sourced from package.json at assembly time. */
  readonly version: string;
  /** Service name, sourced from package.json at assembly time. */
  readonly serviceName: string;
  /** Deployment environment (from validated config). */
  readonly environment: string;
  /** Lightweight database connectivity probe — injected from infrastructure. */
  readonly pingDatabase: () => Promise<boolean>;
  /** Clock and uptime providers — injectable for deterministic tests. */
  readonly now?: () => Date;
  readonly uptime?: () => number;
}

export interface HealthService {
  /** Liveness: process is up and serving. Never touches external systems. */
  getStatus(): HealthResponse;
  /** Readiness: verifies downstream dependencies (database) are reachable. */
  getReadiness(): Promise<ReadinessResponse>;
}

/** Creates the health service. Framework-agnostic and fully unit-testable. */
export function createHealthService(deps: HealthServiceDeps): HealthService {
  const now = deps.now ?? ((): Date => new Date());
  const uptime = deps.uptime ?? ((): number => process.uptime());

  return {
    getStatus(): HealthResponse {
      const data: HealthData = {
        status: 'ok',
        service: deps.serviceName,
        version: deps.version,
        environment: deps.environment,
        uptime: uptime(),
        timestamp: now().toISOString(),
      };
      return { success: true, data };
    },

    async getReadiness(): Promise<ReadinessResponse> {
      const connected = await deps.pingDatabase();
      if (!connected) {
        throw new ServiceUnavailableError('Database connection is not available.');
      }
      return { success: true, data: { database: 'connected', ready: true } };
    },
  };
}
