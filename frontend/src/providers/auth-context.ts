import { createContext } from 'react';
import type { AuthSession, AuthState } from '@/types';

/**
 * Auth context contract.
 *
 * Sprint 9.1 exposes the shape and no-op-friendly seams only. Concrete
 * login/logout/refresh wiring lands in a later sprint; the methods below are
 * placeholders that update client session state once implemented.
 */
export interface AuthContextValue extends AuthState {
  /** Persist a session (tokens + user) obtained from the auth API. */
  setSession: (session: AuthSession) => void;
  /** Clear the current session and stored tokens. */
  clearSession: () => void;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);
