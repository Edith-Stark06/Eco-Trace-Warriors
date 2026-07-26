import axios, {
  AxiosError,
  AxiosHeaders,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from 'axios';
import { env } from '@/lib/env';
import { tokenStorage } from '@/services/token.service';
import type { ApiErrorBody } from '@/types';

/**
 * Single shared Axios instance for the whole app.
 *
 * All API modules build on this instance; UI code never calls axios/fetch
 * directly (docs/engineering/07_FRONTEND.md → exactly one API client).
 *
 * Sprint 9.1: request/response interceptors and the 401 refresh hook are
 * wired as INFRASTRUCTURE. The actual `/auth/refresh` call is intentionally
 * not implemented yet — see `refreshAccessToken` below.
 */

/** Config flag so a retried request is only retried once after refresh. */
interface RetryableConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
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
/* Refresh infrastructure.                                                    */
/*                                                                            */
/* A single in-flight refresh promise is shared so concurrent 401s trigger    */
/* only one refresh attempt. The concrete refresh call is a placeholder in    */
/* this sprint and returns null (treated as "cannot refresh").                */
/* -------------------------------------------------------------------------- */
let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  // TODO (Sprint 9.2): call POST /auth/refresh with the stored refresh token,
  // persist the rotated pair via tokenStorage, and return the new access token.
  // Infrastructure only for now.
  return null;
}

function requestRefresh(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = refreshAccessToken().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/* -------------------------------------------------------------------------- */
/* Response interceptor: normalize errors and handle 401 → refresh → retry.   */
/* -------------------------------------------------------------------------- */
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ error?: ApiErrorBody }>) => {
    const original = error.config as RetryableConfig | undefined;

    if (error.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      const newToken = await requestRefresh();

      if (newToken) {
        const headers = AxiosHeaders.from(original.headers);
        headers.set('Authorization', `Bearer ${newToken}`);
        original.headers = headers;
        return apiClient(original);
      }

      // Refresh unavailable/failed → clear session so guards redirect to login.
      tokenStorage.clear();
    }

    return Promise.reject(error);
  },
);
