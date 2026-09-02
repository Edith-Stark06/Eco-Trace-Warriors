import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react-native';
import { AuthProvider, useAuth } from './AuthContext';
import { secureStorage } from '../storage/secureStorage';
import { triggerSessionExpired } from '../api/client';

jest.mock('../storage/secureStorage', () => ({
  secureStorage: {
    getAccessToken: jest.fn(),
    getRefreshToken: jest.fn(),
    setTokens: jest.fn(),
    clearTokens: jest.fn(),
  },
}));
jest.mock('../api/authApi', () => ({
  authApi: {
    me: jest.fn().mockResolvedValue({ id: 'u1', fullName: 'Test Collector', email: 'c@test.com', phone: null, region: null, role: 'COLLECTOR', emailVerified: true, createdAt: '2026-01-01' }),
    login: jest.fn(),
    logout: jest.fn(),
  },
}));

const secureStorageMock = secureStorage as jest.Mocked<typeof secureStorage>;

const wrapper = ({ children }: { children: React.ReactNode }) => <AuthProvider>{children}</AuthProvider>;

describe('AuthContext session-expired handling', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('flips an authenticated session to unauthenticated with a clear message when apiClient reports a real expiry', async () => {
    // Session restores successfully on mount (a token exists and GET
    // /auth/me succeeds), so we start genuinely authenticated.
    secureStorageMock.getAccessToken.mockResolvedValue('valid-access-token');

    const { result } = await renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.status).toBe('authenticated');
    });

    // Simulate what apiClient.refreshTokens() does when the server
    // genuinely rejects the refresh token (not a network error) — this
    // is the exact function it calls internally.
    await act(async () => {
      triggerSessionExpired();
    });

    await waitFor(() => {
      expect(result.current.status).toBe('unauthenticated');
    });
    expect(result.current.user).toBeNull();
    expect(result.current.error).toBe('Your session has expired. Please sign in again.');
  });

  it('does not register a handler that fires for an app that was never logged in', async () => {
    secureStorageMock.getAccessToken.mockResolvedValue(null);

    const { result } = await renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.status).toBe('unauthenticated');
    });
    expect(result.current.error).toBeNull();
  });
});
