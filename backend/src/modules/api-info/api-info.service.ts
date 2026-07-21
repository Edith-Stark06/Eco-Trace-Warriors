import type { ApiInfoData, ApiInfoResponse } from './api-info.types';

/** Product-facing name of the API surface (distinct from the npm package name). */
export const API_NAME = 'EcoTrace India Backend API';

/** Dependencies injected into the API info service. */
export interface ApiInfoServiceDeps {
  readonly name: string;
  /** API version label (e.g. "v1"), derived from the mounted API prefix. */
  readonly version: string;
  /** Deployment environment (from validated config). */
  readonly environment: string;
  /** Absolute path to the API documentation. */
  readonly documentationPath: string;
}

export interface ApiInfoService {
  getInfo(): ApiInfoResponse;
}

/** Creates the API info service. Framework-agnostic and fully unit-testable. */
export function createApiInfoService(deps: ApiInfoServiceDeps): ApiInfoService {
  return {
    getInfo(): ApiInfoResponse {
      const data: ApiInfoData = {
        name: deps.name,
        version: deps.version,
        environment: deps.environment,
        documentation: deps.documentationPath,
      };
      return { success: true, data };
    },
  };
}
