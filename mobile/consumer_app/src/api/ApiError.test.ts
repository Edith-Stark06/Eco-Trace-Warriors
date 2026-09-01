import { ApiError } from './ApiError';

describe('ApiError', () => {
  it('carries code, status, and message', () => {
    const err = new ApiError('Invalid credentials', { code: 'UNAUTHORIZED', status: 401 });
    expect(err.message).toBe('Invalid credentials');
    expect(err.code).toBe('UNAUTHORIZED');
    expect(err.status).toBe(401);
  });

  it('reports isNetworkError only for the NETWORK_ERROR code', () => {
    const network = new ApiError('offline', { code: 'NETWORK_ERROR', status: null });
    const server = new ApiError('boom', { code: 'INTERNAL', status: 500 });
    expect(network.isNetworkError).toBe(true);
    expect(server.isNetworkError).toBe(false);
  });

  it('is a real Error instance usable with instanceof', () => {
    const err = new ApiError('x', { code: 'X', status: null });
    expect(err).toBeInstanceOf(Error);
    expect(err).toBeInstanceOf(ApiError);
  });
});
