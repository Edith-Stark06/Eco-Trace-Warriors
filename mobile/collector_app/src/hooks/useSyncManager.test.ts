import { renderHook, waitFor } from '@testing-library/react-native';
import { useSyncManager } from './useSyncManager';
import { syncQueueStorage } from '../storage/syncQueue';
import { deviceAiApi } from '../api/deviceAiApi';
import { ApiError } from '../api/ApiError';
import NetInfo from '@react-native-community/netinfo';

jest.mock('@react-native-community/netinfo', () => ({
  addEventListener: jest.fn(() => () => undefined),
  fetch: jest.fn().mockResolvedValue({ isConnected: true, isInternetReachable: true }),
}));
jest.mock('../storage/syncQueue');
jest.mock('../api/deviceAiApi');

const syncQueueMock = syncQueueStorage as jest.Mocked<typeof syncQueueStorage>;
const deviceAiApiMock = deviceAiApi as jest.Mocked<typeof deviceAiApi>;

describe('useSyncManager', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    syncQueueMock.getAll.mockResolvedValue([]);
    syncQueueMock.update.mockResolvedValue(undefined);
    syncQueueMock.remove.mockResolvedValue(undefined);
  });

  it('successfully syncs a pending device confirmation and removes it from the queue', async () => {
    syncQueueMock.getAll.mockResolvedValue([
      { id: 'q1', deviceId: 'dev-001', deviceType: 'laptop', status: 'pending', attempts: 0, lastError: null, createdAt: '2026-01-01T00:00:00.000Z' },
    ]);
    deviceAiApiMock.finalize.mockResolvedValue({ success: true, device: {} as never, previous_state: 'CONFIRMED', current_state: 'REGISTERED' });

    const { result } = await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(deviceAiApiMock.finalize).toHaveBeenCalledWith('dev-001');
    });
    expect(syncQueueMock.remove).toHaveBeenCalledWith('q1');
    expect(result.current.failedCount).toBe(0);
  });

  it('keeps a failed sync as pending and increments attempts (bounded retry)', async () => {
    syncQueueMock.getAll.mockResolvedValue([
      { id: 'q1', deviceId: 'dev-002', deviceType: 'monitor', status: 'pending', attempts: 2, lastError: null, createdAt: '2026-01-01T00:00:00.000Z' },
    ]);
    deviceAiApiMock.finalize.mockRejectedValue(
      new ApiError('Device already finalized', { code: 'CONFLICT', status: 409 }),
    );

    await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(syncQueueMock.update).toHaveBeenCalledWith('q1', expect.objectContaining({ attempts: 3, status: 'pending' }));
    });
    expect(syncQueueMock.remove).not.toHaveBeenCalled();
  });

  it('marks an item failed once it exceeds the maximum retry attempts', async () => {
    syncQueueMock.getAll.mockResolvedValue([
      { id: 'q1', deviceId: 'dev-003', deviceType: 'printer', status: 'pending', attempts: 4, lastError: 'prior error', createdAt: '2026-01-01T00:00:00.000Z' },
    ]);
    deviceAiApiMock.finalize.mockRejectedValue(
      new ApiError('Device already finalized', { code: 'CONFLICT', status: 409 }),
    );

    await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(syncQueueMock.update).toHaveBeenCalledWith('q1', expect.objectContaining({ attempts: 5, status: 'failed' }));
    });
  });

  it('stops the batch (without marking failed) on a network error, leaving the item pending for the next reconnect', async () => {
    syncQueueMock.getAll.mockResolvedValue([
      { id: 'q1', deviceId: 'dev-004', deviceType: 'router', status: 'pending', attempts: 0, lastError: null, createdAt: '2026-01-01T00:00:00.000Z' },
    ]);
    deviceAiApiMock.finalize.mockRejectedValue(new ApiError('offline', { code: 'NETWORK_ERROR', status: null }));

    await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(syncQueueMock.update).toHaveBeenCalledWith('q1', expect.objectContaining({ status: 'pending' }));
    });
    expect(syncQueueMock.remove).not.toHaveBeenCalled();
  });

  it('does not attempt to sync while offline from cold start', async () => {
    (NetInfo.fetch as jest.Mock).mockResolvedValue({ isConnected: false, isInternetReachable: false });
    syncQueueMock.getAll.mockResolvedValue([
      { id: 'q1', deviceId: 'dev-005', deviceType: 'laptop', status: 'pending', attempts: 0, lastError: null, createdAt: '2026-01-01T00:00:00.000Z' },
    ]);

    await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(syncQueueMock.getAll).toHaveBeenCalled();
    });
    expect(deviceAiApiMock.finalize).not.toHaveBeenCalled();
  });
});
