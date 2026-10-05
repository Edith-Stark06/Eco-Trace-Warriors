/**
 * API contract types shared across the frontend.
 *
 * These mirror the backend response envelope and error contract defined in
 * docs/engineering/05_API.md. Keep them in sync when the contract changes.
 */

/** Standard success envelope. `meta` is present only on paginated lists. */
export interface ApiSuccess<TData> {
  success: true;
  data: TData;
  meta?: ApiMeta;
}

export interface ApiMeta {
  page?: number;
  pageSize?: number;
  total?: number;
}

/** Field-level detail attached to validation-style errors. */
export interface ApiErrorDetail {
  field: string;
  issue: string;
}

/** Standard error envelope shape returned by the backend. */
export interface ApiErrorBody {
  code: string;
  message: string;
  details?: ApiErrorDetail[];
}

export interface ApiError {
  success: false;
  error: ApiErrorBody;
}

export type ApiResponse<TData> = ApiSuccess<TData> | ApiError;

/** Offset-based pagination parameters (docs/engineering/05_API.md → Pagination). */
export interface PaginationParams {
  limit?: number;
  offset?: number;
}
