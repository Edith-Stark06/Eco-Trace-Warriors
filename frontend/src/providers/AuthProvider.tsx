import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { authApi } from '@/api/auth.api';
import { tokenStorage } from '@/services/token.service';
import { sessionEvents } from '@/services/session-events';
import type { AuthStatus, LoginCredentials, PublicUser } from '@/types';
import { AuthContext, type AuthContextValue } from '@/providers/auth-context';

/**
 * Owns authentication state and the operations that mutate it.
 *
 * Server is the source of truth: the current user is always resolved via
 * GET /auth/me (never by decoding the JWT client-side). Tokens live behind the
 * `tokenStorage` abstraction; the Axios interceptor performs the transparent
 * refresh-and-retry and emits `unauthorized` when the session is unrecoverable.
 *
 * This provider is mounted above the router, so it never navigates directly —
 * it exposes state and actions; route guards handle redirects.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<PublicUser | null>(null);
  // Starts in `loading` because bootstrapSession runs on mount.
  const [status, setStatus] = useState<AuthStatus>('loading');

  const applyUnauthenticated = useCallback(() => {
    tokenStorage.clear();
    setUser(null);
    setStatus('unauthenticated');
    queryClient.clear();
  }, [queryClient]);

  /** Resolve the current user from a stored token on app start. */
  const bootstrapSession = useCallback(async () => {
    // No credentials at all → nothing to restore; skip the network round-trip.
    if (!tokenStorage.getAccessToken() && !tokenStorage.getRefreshToken()) {
      setStatus('unauthenticated');
      return;
    }

    setStatus('loading');
    try {
      // If only the refresh token survived a reload, the interceptor will
      // transparently refresh the access token before this resolves.
      const currentUser = await authApi.getCurrentUser();
      setUser(currentUser);
      setStatus('authenticated');
    } catch {
      applyUnauthenticated();
    }
  }, [applyUnauthenticated]);

  /** Authenticate with credentials; on success populates the session. */
  const login = useCallback(async (credentials: LoginCredentials) => {
    const result = await authApi.login(credentials);
    tokenStorage.setAccessToken(result.accessToken);
    tokenStorage.setRefreshToken(result.refreshToken);

    // Trust the server, not the login payload: confirm the session via /auth/me.
    try {
      const currentUser = await authApi.getCurrentUser();
      setUser(currentUser);
      setStatus('authenticated');
    } catch (error) {
      tokenStorage.clear();
      setUser(null);
      setStatus('unauthenticated');
      throw error;
    }
  }, []);

  /** Revoke the session server-side (best-effort) and clear local state. */
  const logout = useCallback(async () => {
    const refreshToken = tokenStorage.getRefreshToken();
    if (refreshToken) {
      try {
        await authApi.logout(refreshToken);
      } catch {
        // Logout is best-effort: a failed revocation must not block sign-out.
      }
    }
    applyUnauthenticated();
  }, [applyUnauthenticated]);

  /** Force a token refresh; returns true if a valid session remains. */
  const refreshSession = useCallback(async (): Promise<boolean> => {
    const refreshToken = tokenStorage.getRefreshToken();
    if (!refreshToken) {
      applyUnauthenticated();
      return false;
    }
    try {
      const tokens = await authApi.refresh(refreshToken);
      tokenStorage.setAccessToken(tokens.accessToken);
      tokenStorage.setRefreshToken(tokens.refreshToken);
      return true;
    } catch {
      applyUnauthenticated();
      return false;
    }
  }, [applyUnauthenticated]);

  // Run session bootstrap exactly once on mount.
  const didBootstrap = useRef(false);
  useEffect(() => {
    if (didBootstrap.current) return;
    didBootstrap.current = true;
    void bootstrapSession();
  }, [bootstrapSession]);

  // React to unrecoverable 401s surfaced by the Axios interceptor.
  useEffect(() => {
    return sessionEvents.on('unauthorized', () => {
      setUser(null);
      setStatus('unauthenticated');
      queryClient.clear();
    });
  }, [queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      status,
      isAuthenticated: status === 'authenticated' && user !== null,
      isLoading: status === 'idle' || status === 'loading',
      login,
      logout,
      refreshSession,
      bootstrapSession,
    }),
    [user, status, login, logout, refreshSession, bootstrapSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
