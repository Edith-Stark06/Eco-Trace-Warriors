import { isAxiosError } from 'axios';
import { apiClient } from '@/api/axios';
import type { ApiErrorBody, ApiSuccess } from '@/types';

/**
 * Thin helpers shared by the typed API modules.
 *
 * `unwrap` extracts `data` from the standard success envelope so callers get
 * the resource directly. `toApiError` normalizes any thrown error into the
 * backend error contract shape for consistent handling in the UI layer.
 */

export async function unwrap<TData>(promise: Promise<{ data: ApiSuccess<TData> }>): Promise<TData> {
  const response = await promise;
  return response.data.data;
}

/** Normalize an unknown thrown value into the backend error contract shape. */
export function toApiError(error: unknown): ApiErrorBody {
  if (isAxiosError<{ error?: ApiErrorBody }>(error)) {
    const body = error.response?.data?.error;
    if (body) return body;

    return {
      code: error.code === 'ECONNABORTED' ? 'TIMEOUT' : 'NETWORK_ERROR',
      message: 'Unable to reach the server. Please check your connection and try again.',
    };
  }

  return {
    code: 'UNKNOWN_ERROR',
    message: 'Something went wrong. Please try again.',
  };
}

export { apiClient };
