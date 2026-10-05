import type { SuccessResponse } from '../../types';

/** Payload returned inside the envelope by GET /api/v1/health. */
export interface HealthData {
  status: 'ok';
  service: string;
  version: string;
  environment: string;
  uptime: number;
  timestamp: string;
}

/** Payload returned inside the envelope by GET /api/v1/ready when the app is ready. */
export interface ReadinessData {
  database: 'connected';
  ready: true;
}

export type HealthResponse = SuccessResponse<HealthData>;
export type ReadinessResponse = SuccessResponse<ReadinessData>;
