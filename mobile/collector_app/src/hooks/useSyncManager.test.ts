import { renderHook, waitFor } from '@testing-library/react-native';
import { useSyncManager } from './useSyncManager';
import { syncQueueStorage } from '../storage/syncQueue';
import { deviceAiApi } from '../api/deviceAiApi';
import { ApiError } from '../api/ApiError';
import NetInfo from '@react-native-community/netinfo';
import type { SyncQueueItem } from '../types/syncQueue';

jest.mock('@react-native-community/netinfo', () => ({
  addEventListener: jest.fn(() => () => undefined),
  fetch: jest.fn().mockResolvedValue({ isConnected: true, isInternetReachable: true }),
}));
jest.mock('../storage/syncQueue');
jest.mock('../api/deviceAiApi');

const syncQueueMock = syncQueueStorage as jest.Mocked<typeof syncQueueStorage>;
const deviceAiApiMock = deviceAiApi as jest.Mocked<typeof deviceAiApi>;

function item(overrides: Partial<SyncQueueItem>): SyncQueueItem {
  return {
    id: 'q1',
    deviceId: 'dev-001',
    deviceType: 'laptop',
    status: 'pending',
    attempts: 0,
    lastError: null,
    createdAt: '2026-01-01T00:00:00.000Z',
    nextRetryAt: null,
    ...overrides,
  };
}

describe('useSyncManager', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    syncQueueMock.getAll.mockResolvedValue([]);
    syncQueueMock.update.mockResolvedValue(undefined);
    syncQueueMock.remove.mockResolvedValue(undefined);
  });

  it('successfully syncs a pending device confirmation and removes it from the queue', async () => {
    syncQueueMock.getAll.mockResolvedValue([item({ deviceId: 'dev-001' })]);
    deviceAiApiMock.finalize.mockResolvedValue({ success: true, device: {} as never, previous_state: 'CONFIRMED', current_state: 'REGISTERED' });

    const { result } = await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(deviceAiApiMock.finalize).toHaveBeenCalledWith('dev-001');
    });
    expect(syncQueueMock.remove).toHaveBeenCalledWith('q1');
    expect(result.current.failedCount).toBe(0);
    expect(result.current.conflictCount).toBe(0);
  });

  it('keeps a validation failure as pending with a backoff window and increments attempts (bounded retry)', async () => {
    syncQueueMock.getAll.mockResolvedValue([item({ deviceId: 'dev-002', attempts: 2 })]);
    deviceAiApiMock.finalize.mockRejectedValue(
      new ApiError('Device type is invalid', { code: 'VALIDATION_ERROR', status: 400 }),
    );

    await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(syncQueueMock.update).toHaveBeenCalledWith(
        'q1',
        expect.objectContaining({ attempts: 3, status: 'pending', nextRetryAt: expect.any(String) }),
      );
    });
    expect(syncQueueMock.remove).not.toHaveBeenCalled();
  });

  it('marks an item failed once a non-conflict error exceeds the maximum retry attempts', async () => {
    syncQueueMock.getAll.mockResolvedValue([item({ deviceId: 'dev-003', attempts: 4, lastError: 'prior error' })]);
    deviceAiApiMock.finalize.mockRejectedValue(
      new ApiError('Device type is invalid', { code: 'VALIDATION_ERROR', status: 400 }),
    );

    await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(syncQueueMock.update).toHaveBeenCalledWith('q1', expect.objectContaining({ attempts: 5, status: 'failed' }));
    });
  });

  it('marks a 409 conflict as terminal immediately, without waiting for the retry bound', async () => {
    syncQueueMock.getAll.mockResolvedValue([item({ deviceId: 'dev-006', attempts: 0 })]);
    deviceAiApiMock.finalize.mockRejectedValue(
      new ApiError('Device already finalized', { code: 'CONFLICT', status: 409 }),
    );

    await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(syncQueueMock.update).toHaveBeenCalledWith(
        'q1',
        expect.objectContaining({ status: 'conflict', attempts: 1, nextRetryAt: null }),
      );
    });
  });

  it('does not retry an item still inside its backoff window', async () => {
    const future = new Date(Date.now() + 60_000).toISOString();
    syncQueueMock.getAll.mockResolvedValue([item({ deviceId: 'dev-007', attempts: 1, nextRetryAt: future })]);

    await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(syncQueueMock.getAll).toHaveBeenCalled();
    });
    expect(deviceAiApiMock.finalize).not.toHaveBeenCalled();
  });

  it('retries an item whose backoff window has already elapsed', async () => {
    const past = new Date(Date.now() - 1000).toISOString();
    syncQueueMock.getAll.mockResolvedValue([item({ deviceId: 'dev-008', attempts: 1, nextRetryAt: past })]);
    deviceAiApiMock.finalize.mockResolvedValue({ success: true, device: {} as never, previous_state: 'CONFIRMED', current_state: 'REGISTERED' });

    await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(deviceAiApiMock.finalize).toHaveBeenCalledWith('dev-008');
    });
  });

  it('stops the batch (without marking failed) on a network error, leaving the item pending for the next reconnect', async () => {
    syncQueueMock.getAll.mockResolvedValue([item({ deviceId: 'dev-004' })]);
    deviceAiApiMock.finalize.mockRejectedValue(new ApiError('offline', { code: 'NETWORK_ERROR', status: null }));

    await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(syncQueueMock.update).toHaveBeenCalledWith('q1', expect.objectContaining({ status: 'pending' }));
    });
    expect(syncQueueMock.remove).not.toHaveBeenCalled();
  });

  it('does not attempt to sync while offline from cold start', async () => {
    (NetInfo.fetch as jest.Mock).mockResolvedValue({ isConnected: false, isInternetReachable: false });
    syncQueueMock.getAll.mockResolvedValue([item({ deviceId: 'dev-005' })]);

    await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(syncQueueMock.getAll).toHaveBeenCalled();
    });
    expect(deviceAiApiMock.finalize).not.toHaveBeenCalled();
  });
});
