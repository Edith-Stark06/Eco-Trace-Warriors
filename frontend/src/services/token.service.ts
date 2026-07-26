/**
 * Token storage abstraction.
 *
 * Provides a single seam for reading/writing auth tokens so the storage
 * strategy can change without touching call sites (axios interceptors,
 * auth provider). Per docs/engineering/07_FRONTEND.md, the access token is
 * kept in memory (not localStorage) to reduce XSS exposure; the refresh
 * token is persisted so sessions survive reloads until the refresh flow is
 * implemented in a later sprint.
 *
 * NOTE (Sprint 9.1): infrastructure only — no JWT parsing or refresh calls.
 */

const REFRESH_TOKEN_KEY = 'ecotrace.refreshToken';

/** In-memory access token — cleared on full page reload by design. */
let accessToken: string | null = null;

export interface TokenStorage {
  getAccessToken(): string | null;
  setAccessToken(token: string | null): void;
  getRefreshToken(): string | null;
  setRefreshToken(token: string | null): void;
  clear(): void;
}

function safeGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(key: string, value: string | null): void {
  try {
    if (value === null) {
      window.localStorage.removeItem(key);
    } else {
      window.localStorage.setItem(key, value);
    }
  } catch {
    // Storage may be unavailable (private mode, SSR); fail silently.
  }
}

export const tokenStorage: TokenStorage = {
  getAccessToken: () => accessToken,
  setAccessToken: (token) => {
    accessToken = token;
  },
  getRefreshToken: () => safeGet(REFRESH_TOKEN_KEY),
  setRefreshToken: (token) => safeSet(REFRESH_TOKEN_KEY, token),
  clear: () => {
    accessToken = null;
    safeSet(REFRESH_TOKEN_KEY, null);
  },
};
