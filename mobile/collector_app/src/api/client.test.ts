import { apiClient } from './client';
import { ApiError } from './ApiError';
import NetInfo from '@react-native-community/netinfo';
import { secureStorage } from '../storage/secureStorage';

jest.mock('@react-native-community/netinfo', () => ({
  fetch: jest.fn(),
}));
jest.mock('../storage/secureStorage', () => ({
  secureStorage: {
    getAccessToken: jest.fn().mockResolvedValue('access-token-123'),
    getRefreshToken: jest.fn().mockResolvedValue('refresh-token-456'),
    setTokens: jest.fn(),
    clearTokens: jest.fn(),
  },
}));

const netInfoFetchMock = NetInfo.fetch as jest.Mock;
const secureStorageMock = secureStorage as jest.Mocked<typeof secureStorage>;

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

describe('apiClient', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    netInfoFetchMock.mockResolvedValue({ isConnected: true, isInternetReachable: true });
    secureStorageMock.getAccessToken.mockResolvedValue('access-token-123');
    secureStorageMock.getRefreshToken.mockResolvedValue('refresh-token-456');
    globalThis.fetch = jest.fn();
  });

  it('attaches the stored access token as a Bearer header', async () => {
    (globalThis.fetch as jest.Mock).mockResolvedValue(jsonResponse(200, { success: true, data: { ok: true } }));

    await apiClient('/collector/submissions');

    const [, init] = (globalThis.fetch as jest.Mock).mock.calls[0];
    expect(init.headers.Authorization).toBe('Bearer access-token-123');
  });

  it('fails fast with a NETWORK_ERROR without calling fetch when NetInfo reports offline', async () => {
    netInfoFetchMock.mockResolvedValue({ isConnected: false, isInternetReachable: false });

    await expect(apiClient('/collector/submissions')).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
    });
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('surfaces a TIMEOUT ApiError when the request exceeds timeoutMs', async () => {
    (globalThis.fetch as jest.Mock).mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => {
            const err = new Error('Aborted');
            err.name = 'AbortError';
            reject(err);
          });
        }),
    );

    await expect(apiClient('/collector/submissions', { timeoutMs: 20 })).rejects.toMatchObject({
      code: 'TIMEOUT',
    });
  });

  it('retries a GET request up to twice on a network error, then succeeds', async () => {
    (globalThis.fetch as jest.Mock)
      .mockRejectedValueOnce(new TypeError('Network request failed'))
      .mockRejectedValueOnce(new TypeError('Network request failed'))
      .mockResolvedValueOnce(jsonResponse(200, { success: true, data: [] }));

    const result = await apiClient('/collector/submissions');

    expect(result).toEqual([]);
    expect(globalThis.fetch).toHaveBeenCalledTimes(3);
  });

  it('does not retry a POST request on a network error (left to the offline sync queue instead)', async () => {
    (globalThis.fetch as jest.Mock).mockRejectedValue(new TypeError('Network request failed'));

    await expect(apiClient('/submissions/x/accept', { method: 'PATCH' })).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
    });
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  it('does not retry on a real server error response (4xx/5xx)', async () => {
    (globalThis.fetch as jest.Mock).mockResolvedValue(
      jsonResponse(500, { success: false, error: { code: 'INTERNAL', message: 'boom' } }),
    );

    await expect(apiClient('/collector/submissions')).rejects.toMatchObject({ code: 'INTERNAL', status: 500 });
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  it('refreshes the access token exactly once on a 401 and retries the original request', async () => {
    (globalThis.fetch as jest.Mock)
      .mockResolvedValueOnce(jsonResponse(401, { success: false, error: { code: 'UNAUTHORIZED', message: 'expired' } }))
      .mockResolvedValueOnce(jsonResponse(200, { success: true, data: { accessToken: 'new-access', refreshToken: 'new-refresh' } }))
      .mockResolvedValueOnce(jsonResponse(200, { success: true, data: [] }));

    const result = await apiClient('/collector/submissions');

    expect(result).toEqual([]);
    expect(secureStorageMock.setTokens).toHaveBeenCalledWith('new-access', 'new-refresh');
    expect(globalThis.fetch).toHaveBeenCalledTimes(3);
  });

  it('clears tokens and surfaces the original 401 when refresh itself fails', async () => {
    (globalThis.fetch as jest.Mock)
      .mockResolvedValueOnce(jsonResponse(401, { success: false, error: { code: 'UNAUTHORIZED', message: 'expired' } }))
      .mockResolvedValueOnce(jsonResponse(401, { success: false, error: { code: 'UNAUTHORIZED', message: 'bad refresh' } }));

    await expect(apiClient('/collector/submissions')).rejects.toBeInstanceOf(ApiError);
    expect(secureStorageMock.clearTokens).toHaveBeenCalled();
  });

  it('merges custom headers without dropping Content-Type or Authorization', async () => {
    (globalThis.fetch as jest.Mock).mockResolvedValue(jsonResponse(200, { success: true, data: {} }));

    await apiClient('/collector/submissions', { headers: { 'X-Custom': 'value' } });

    const [, init] = (globalThis.fetch as jest.Mock).mock.calls[0];
    expect(init.headers['X-Custom']).toBe('value');
    expect(init.headers['Content-Type']).toBe('application/json');
    expect(init.headers.Authorization).toBe('Bearer access-token-123');
  });
});
