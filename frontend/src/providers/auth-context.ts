import { createContext } from 'react';
import type { AuthState, LoginCredentials } from '@/types';

/**
 * Auth context contract.
 *
 * Exposes reactive auth state plus the async actions that mutate it. All
 * network work (login, logout, refresh, bootstrap) lives in the provider so
 * components depend only on this small surface.
 */
export interface AuthContextValue extends AuthState {
  /** Authenticate with credentials; on success populates the session. */
  login: (credentials: LoginCredentials) => Promise<void>;
  /** Revoke the session server-side (best-effort) and clear local state. */
  logout: () => Promise<void>;
  /** Force a token refresh; returns true if a valid session remains. */
  refreshSession: () => Promise<boolean>;
  /** Resolve the current user from a stored token on app start. */
  bootstrapSession: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);
