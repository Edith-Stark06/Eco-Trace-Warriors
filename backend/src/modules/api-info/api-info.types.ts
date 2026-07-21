import type { SuccessResponse } from '../../types';

/** Payload returned inside the envelope by GET /api/v1. */
export interface ApiInfoData {
  name: string;
  version: string;
  environment: string;
  documentation: string;
}

export type ApiInfoResponse = SuccessResponse<ApiInfoData>;
