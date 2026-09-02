import NetInfo from '@react-native-community/netinfo';
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
  /** Request timeout in milliseconds (default 15000). */
  timeoutMs?: number;
  /** Extra headers merged in after Content-Type/Authorization (e.g. X-Idempotency-Key). */
  headers?: Record<string, string>;
};

const DEFAULT_TIMEOUT_MS = 15000;
const MAX_NETWORK_RETRIES = 2;
const RETRY_BASE_DELAY_MS = 500;

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

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ApiError('The request took too long to respond.', {
        code: 'TIMEOUT',
        status: null,
      });
    }
    throw new ApiError('Unable to reach the server. Check your connection.', {
      code: 'NETWORK_ERROR',
      status: null,
    });
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Fetch-based API client for the EcoTrace backend (and, via `baseUrl`, the
 * device-ai service). Attaches the stored access token, and on a single 401
 * transparently refreshes and retries exactly once.
 *
 * Hardening (P9.4): fails fast with a clear ApiError when NetInfo already
 * reports no connectivity (no point waiting out a timeout we know will
 * fail); enforces a request timeout via AbortController; retries GET
 * requests (the only inherently idempotent, safe-to-retry method here) up
 * to twice with jittered backoff on a genuine network/timeout error only —
 * never on a real server response (4xx/5xx), and never for
 * POST/PATCH/DELETE, which the offline sync queues (not this client) are
 * responsible for retrying safely with their own idempotency handling.
 */
export async function apiClient<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    method = 'GET',
    body,
    skipAuth = false,
    skipRefresh = false,
    baseUrl = env.apiBaseUrl,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    headers: extraHeaders,
  } = options;

  if (!skipRefresh) {
    const netState = await NetInfo.fetch();
    if (netState.isConnected === false || netState.isInternetReachable === false) {
      throw new ApiError('You are offline. Check your connection and try again.', {
        code: 'NETWORK_ERROR',
        status: null,
      });
    }
  }

  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...extraHeaders };
  if (!skipAuth) {
    const token = await secureStorage.getAccessToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }

  const init: RequestInit = {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  };

  let response: Response;
  let attempt = 0;
  for (;;) {
    try {
      response = await fetchWithTimeout(`${baseUrl}${path}`, init, timeoutMs);
      break;
    } catch (err) {
      const retryable = method === 'GET' && err instanceof ApiError && err.isNetworkError;
      if (retryable && attempt < MAX_NETWORK_RETRIES) {
        attempt += 1;
        await delay(RETRY_BASE_DELAY_MS * 2 ** (attempt - 1) + Math.random() * 100);
        continue;
      }
      throw err;
    }
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
