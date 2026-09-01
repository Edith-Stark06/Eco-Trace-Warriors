import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { authApi } from '../api/authApi';
import { secureStorage } from '../storage/secureStorage';
import { ApiError } from '../api/ApiError';
import type { PublicUser } from '../types/auth';

interface AuthState {
  status: 'loading' | 'authenticated' | 'unauthenticated';
  user: PublicUser | null;
  error: string | null;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * Session lifecycle for the Collector app: persists tokens in secure
 * storage (P8.7 pattern), restores the session on cold start via GET
 * /auth/me, and exposes login/logout to the rest of the app. Mirrors the
 * Flutter app's AuthProvider/auth_repository split but as a single
 * context, matching this codebase's simpler screen count.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading', user: null, error: null });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const token = await secureStorage.getAccessToken();
      if (!token) {
        if (!cancelled) setState({ status: 'unauthenticated', user: null, error: null });
        return;
      }
      try {
        const user = await authApi.me();
        if (!cancelled) setState({ status: 'authenticated', user, error: null });
      } catch {
        await secureStorage.clearTokens();
        if (!cancelled) setState({ status: 'unauthenticated', user: null, error: null });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setState((prev) => ({ ...prev, error: null }));
    try {
      const result = await authApi.login({ email, password });
      if (result.user.role !== 'COLLECTOR' && result.user.role !== 'ADMIN') {
        throw new ApiError('This account is not authorized for the Collector app.', {
          code: 'FORBIDDEN_ROLE',
          status: 403,
        });
      }
      await secureStorage.setTokens(result.accessToken, result.refreshToken);
      setState({ status: 'authenticated', user: result.user, error: null });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Unable to sign in. Please try again.';
      setState({ status: 'unauthenticated', user: null, error: message });
      throw err;
    }
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = await secureStorage.getRefreshToken();
    await secureStorage.clearTokens();
    setState({ status: 'unauthenticated', user: null, error: null });
    if (refreshToken) {
      // Best-effort server-side revocation; local session is already cleared either way.
      authApi.logout(refreshToken).catch(() => undefined);
    }
  }, []);

  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  const value = useMemo(
    () => ({ ...state, login, logout, clearError }),
    [state, login, logout, clearError],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
}
