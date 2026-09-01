import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { authApi } from '../api/authApi';
import { secureStorage } from '../storage/secureStorage';
import { ApiError } from '../api/ApiError';
import type { PublicUser, RegisterInput } from '../types/auth';

interface AuthState {
  status: 'loading' | 'authenticated' | 'unauthenticated';
  user: PublicUser | null;
  error: string | null;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function assertConsumerRole(user: PublicUser): void {
  if (user.role !== 'CONSUMER') {
    throw new ApiError('This account is not authorized for the Consumer app.', {
      code: 'FORBIDDEN_ROLE',
      status: 403,
    });
  }
}

/** Session lifecycle for the Consumer app — parallels the Collector app's AuthContext, plus registration. */
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
      assertConsumerRole(result.user);
      await secureStorage.setTokens(result.accessToken, result.refreshToken);
      setState({ status: 'authenticated', user: result.user, error: null });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Unable to sign in. Please try again.';
      setState({ status: 'unauthenticated', user: null, error: message });
      throw err;
    }
  }, []);

  const register = useCallback(async (input: RegisterInput) => {
    setState((prev) => ({ ...prev, error: null }));
    try {
      const result = await authApi.register(input);
      assertConsumerRole(result.user);
      await secureStorage.setTokens(result.accessToken, result.refreshToken);
      setState({ status: 'authenticated', user: result.user, error: null });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Unable to create your account.';
      setState({ status: 'unauthenticated', user: null, error: message });
      throw err;
    }
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = await secureStorage.getRefreshToken();
    await secureStorage.clearTokens();
    setState({ status: 'unauthenticated', user: null, error: null });
    if (refreshToken) {
      authApi.logout(refreshToken).catch(() => undefined);
    }
  }, []);

  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  const value = useMemo(
    () => ({ ...state, login, register, logout, clearError }),
    [state, login, register, logout, clearError],
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
