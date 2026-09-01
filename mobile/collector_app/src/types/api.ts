/**
 * Backend response envelope — mirrors backend/src/types/api.ts exactly.
 * Never invent a shape here; this must track the real backend contract.
 */
export interface SuccessResponse<T> {
  success: true;
  data: T;
  meta?: PaginationMeta;
}

export interface PaginationMeta {
  page: number;
  pageSize: number;
  total: number;
}

export interface ErrorResponse {
  success: false;
  error: {
    code: string;
    message: string;
    details?: readonly { field: string; issue: string }[];
  };
}

export type ApiResponse<T> = SuccessResponse<T> | ErrorResponse;
