/** Thrown by apiClient for any non-2xx response or network failure. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number | null;
  readonly details?: readonly { field: string; issue: string }[];

  constructor(
    message: string,
    options: { code: string; status: number | null; details?: readonly { field: string; issue: string }[] },
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = options.code;
    this.status = options.status;
    this.details = options.details;
  }

  /**
   * True for a connectivity failure (device offline, host unreachable) or a
   * request timeout — i.e. we don't know whether the server ever saw the
   * request, as opposed to a real API error response. Both are safe to
   * retry for idempotent (GET) requests.
   */
  get isNetworkError(): boolean {
    return this.code === 'NETWORK_ERROR' || this.code === 'TIMEOUT';
  }

  /** True specifically for a request that was aborted after exceeding its timeout. */
  get isTimeout(): boolean {
    return this.code === 'TIMEOUT';
  }
}
