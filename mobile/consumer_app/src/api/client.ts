import { env } from '../config/env';
import { secureStorage } from '../storage/secureStorage';
import { ApiError } from './ApiError';
import type { ApiResponse } from '../types/api';
import type { AuthTokens } from '../types/auth';

export type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  /** Skip attaching the Authorization header (login/register/refresh). */
  skipAuth?: boolean;
  /** Skip the automatic 401 -> refresh -> retry cycle (the refresh call itself). */
  skipRefresh?: boolean;
  baseUrl?: string;
};

let refreshPromise: Promise<AuthTokens | null> | null = null;

/** Exchanges the stored refresh token for a new pair, deduped across concurrent 401s. */
async function refreshTokens(): Promise<AuthTokens | null> {
  if (refreshPromise) {
    return refreshPromise;
  }
  refreshPromise = (async () => {
    const refreshToken = await secureStorage.getRefreshToken();
    if (!refreshToken) {
      return null;
    }
    try {
      const res = await fetch(`${env.apiBaseUrl}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refreshToken }),
      });
      const json = (await res.json()) as ApiResponse<AuthTokens>;
      if (!res.ok || !json.success) {
        await secureStorage.clearTokens();
        return null;
      }
      await secureStorage.setTokens(json.data.accessToken, json.data.refreshToken);
      return json.data;
    } catch {
      return null;
    }
  })();
  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

/**
 * Fetch-based API client for the EcoTrace backend (and, via `baseUrl`, the
 * device-ai service). Attaches the stored access token, and on a single 401
 * transparently refreshes and retries exactly once — mirrors the Flutter
 * app's Dio interceptor behavior (api_client.dart) without pulling in an
 * HTTP library dependency.
 */
export async function apiClient<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, skipAuth = false, skipRefresh = false, baseUrl = env.apiBaseUrl } = options;

  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (!skipAuth) {
    const token = await secureStorage.getAccessToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }

  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError('Unable to reach the server. Check your connection.', {
      code: 'NETWORK_ERROR',
      status: null,
    });
  }

  if (response.status === 401 && !skipAuth && !skipRefresh) {
    const refreshed = await refreshTokens();
    if (refreshed) {
      return apiClient<T>(path, { ...options, skipRefresh: true });
    }
  }

  const json = (await response.json().catch(() => null)) as ApiResponse<T> | null;

  if (!response.ok || !json || !json.success) {
    const error = json && !json.success ? json.error : null;
    throw new ApiError(error?.message ?? `Request failed with status ${response.status}`, {
      code: error?.code ?? 'UNKNOWN_ERROR',
      status: response.status,
      details: error?.details,
    });
  }

  return json.data;
}
