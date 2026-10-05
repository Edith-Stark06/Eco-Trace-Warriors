/**
 * API response envelope types.
 * See docs/engineering/05_API.md — Request & Response Format / Error Contract.
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
