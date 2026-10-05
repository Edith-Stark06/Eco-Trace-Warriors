import axios, {
  AxiosError,
  AxiosHeaders,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from 'axios';
import { env } from '@/lib/env';
import { tokenStorage } from '@/services/token.service';
import { sessionEvents } from '@/services/session-events';
import type { ApiErrorBody, ApiSuccess, AuthTokens } from '@/types';

/**
 * Single shared Axios instance for the whole app.
 *
 * All API modules build on this instance; UI code never calls axios/fetch
 * directly (docs/engineering/07_FRONTEND.md → exactly one API client).
 *
 * A request interceptor attaches the bearer token. The response interceptor
 * implements the `401 → refresh → retry` flow: on an expired access token it
 * rotates the token pair via POST /auth/refresh (single-flight, shared across
 * concurrent 401s), retries the original request once, and — if refresh fails
 * — clears the session and emits `unauthorized` so the app redirects to login.
 */

/** Extra per-request flags recognized by the interceptors. */
declare module 'axios' {
  export interface AxiosRequestConfig {
    /** Skip 401 refresh handling (used by the refresh call itself). */
    skipAuthRefresh?: boolean;
    /** Internal: marks a request already retried after a refresh. */
    _retry?: boolean;
  }
}

export const apiClient: AxiosInstance = axios.create({
  baseURL: env.apiBaseUrl,
  timeout: env.apiTimeout,
  headers: {
    'Content-Type': 'application/json',
  },
});

/* -------------------------------------------------------------------------- */
/* Request interceptor: attach the bearer token when present.                 */
/* -------------------------------------------------------------------------- */
apiClient.interceptors.request.use((config) => {
  const token = tokenStorage.getAccessToken();
  if (token) {
    const headers = AxiosHeaders.from(config.headers);
    headers.set('Authorization', `Bearer ${token}`);
    config.headers = headers;
  }
  return config;
});

/* -------------------------------------------------------------------------- */
/* Refresh flow (single-flight).                                              */
/*                                                                            */
/* A single in-flight refresh promise is shared so concurrent 401s trigger    */
/* only one POST /auth/refresh. Refresh tokens rotate: on success BOTH tokens */
/* are replaced. On failure the session is cleared and `unauthorized` fires.  */
/* -------------------------------------------------------------------------- */
let refreshInFlight: Promise<string | null> | null = null;

async function performRefresh(): Promise<string | null> {
  const refreshToken = tokenStorage.getRefreshToken();
  if (!refreshToken) return null;

  try {
    // `skipAuthRefresh` prevents this call's own 401 from recursing here.
    const response = await apiClient.post<ApiSuccess<AuthTokens>>(
      '/auth/refresh',
      { refreshToken },
      { skipAuthRefresh: true },
    );
    const tokens = response.data.data;
    tokenStorage.setAccessToken(tokens.accessToken);
    tokenStorage.setRefreshToken(tokens.refreshToken);
    return tokens.accessToken;
  } catch {
    return null;
  }
}

function requestRefresh(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/* -------------------------------------------------------------------------- */
/* Response interceptor: handle 401 → refresh → retry (once).                 */
/* -------------------------------------------------------------------------- */
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ error?: ApiErrorBody }>) => {
    const original = error.config as InternalAxiosRequestConfig | undefined;
    const isAuthError = error.response?.status === 401;

    if (isAuthError && original && !original.skipAuthRefresh && !original._retry) {
      original._retry = true;
      const newToken = await requestRefresh();

      if (newToken) {
        const headers = AxiosHeaders.from(original.headers);
        headers.set('Authorization', `Bearer ${newToken}`);
        original.headers = headers;
        return apiClient(original);
      }

      // Refresh unavailable/failed → drop the session and notify the app so
      // route guards send the user to login.
      tokenStorage.clear();
      sessionEvents.emit('unauthorized');
    }

    return Promise.reject(error);
  },
);
