import type { HealthStatus } from './health.types';

/** Dependencies injected into the health service. */
export interface HealthServiceDeps {
  /** Application version, sourced from package.json at assembly time. */
  readonly version: string;
  /** Clock and uptime providers — injectable for deterministic tests. */
  readonly now?: () => Date;
  readonly uptime?: () => number;
}

export interface HealthService {
  getStatus(): HealthStatus;
}

/** Creates the health service. Framework-agnostic and fully unit-testable. */
export function createHealthService(deps: HealthServiceDeps): HealthService {
  const now = deps.now ?? ((): Date => new Date());
  const uptime = deps.uptime ?? ((): number => process.uptime());

  return {
    getStatus(): HealthStatus {
      return {
        success: true,
        message: 'EcoTrace Backend is running',
        version: deps.version,
        timestamp: now().toISOString(),
        uptime: uptime(),
      };
    },
  };
}
