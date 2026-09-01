import { apiClient } from './client';
import type { AuthResult, LoginInput, PublicUser } from '../types/auth';

/** Real backend routes — backend/src/modules/auth/auth.routes.ts. */
export const authApi = {
  login(input: LoginInput): Promise<AuthResult> {
    return apiClient<AuthResult>('/auth/login', { method: 'POST', body: input, skipAuth: true });
  },
  logout(refreshToken: string): Promise<{ loggedOut: true }> {
    return apiClient('/auth/logout', { method: 'POST', body: { refreshToken }, skipAuth: true });
  },
  me(): Promise<PublicUser> {
    return apiClient<PublicUser>('/auth/me');
  },
};
