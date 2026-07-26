import { useCallback, useMemo, useState } from 'react';
import { tokenStorage } from '@/services/token.service';
import type { AuthSession, User } from '@/types';
import { AuthContext, type AuthContextValue } from '@/providers/auth-context';

/**
 * Provides authentication state to the app.
 *
 * Sprint 9.1: infrastructure only. This holds the in-memory user/session
 * state and coordinates with the token storage abstraction, but performs no
 * network calls (no login, no JWT parsing, no refresh integration). A future
 * sprint will bootstrap the session on mount via GET /auth/me and wire the
 * refresh flow.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  // Starts unauthenticated in this sprint; session bootstrap arrives later.
  const [status, setStatus] = useState<AuthContextValue['status']>('unauthenticated');

  const setSession = useCallback((session: AuthSession) => {
    tokenStorage.setAccessToken(session.accessToken);
    tokenStorage.setRefreshToken(session.refreshToken);
    setUser(session.user);
    setStatus('authenticated');
  }, []);

  const clearSession = useCallback(() => {
    tokenStorage.clear();
    setUser(null);
    setStatus('unauthenticated');
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      status,
      isAuthenticated: status === 'authenticated' && user !== null,
      setSession,
      clearSession,
    }),
    [user, status, setSession, clearSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
