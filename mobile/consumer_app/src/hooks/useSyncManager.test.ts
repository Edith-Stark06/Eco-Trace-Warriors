import { renderHook, waitFor } from '@testing-library/react-native';
import { useSyncManager } from './useSyncManager';
import { syncQueueStorage } from '../storage/syncQueue';
import { submissionsApi } from '../api/submissionsApi';
import { ApiError } from '../api/ApiError';
import NetInfo from '@react-native-community/netinfo';
import type { CreateSubmissionInput } from '../types/submission';

jest.mock('@react-native-community/netinfo', () => ({
  addEventListener: jest.fn(() => () => undefined),
  fetch: jest.fn().mockResolvedValue({ isConnected: true, isInternetReachable: true }),
}));
jest.mock('../storage/syncQueue');
jest.mock('../api/submissionsApi');

const syncQueueMock = syncQueueStorage as jest.Mocked<typeof syncQueueStorage>;
const submissionsApiMock = submissionsApi as jest.Mocked<typeof submissionsApi>;

const SAMPLE_INPUT: CreateSubmissionInput = {
  category: 'laptop',
  estimatedWeight: 2.5,
  address: '12 Green Street',
  latitude: 13.08,
  longitude: 80.27,
};

const SAMPLE_SUBMISSION = {
  id: 'sub-1',
  userId: 'user-1',
  category: 'laptop',
  description: null,
  estimatedWeight: 2.5,
  address: '12 Green Street',
  latitude: 13.08,
  longitude: 80.27,
  imageUrls: [],
  status: 'PENDING' as const,
  assignedCollectorId: null,
  assignedRecyclerId: null,
  pickupScheduledAt: null,
  completedAt: null,
  processingStartedAt: null,
  recycledAt: null,
  recyclerNotes: null,
  recoveredWeight: null,
  materialRecovery: null,
  createdAt: '2026-01-01T00:00:00.000Z',
  updatedAt: '2026-01-01T00:00:00.000Z',
};

describe('useSyncManager', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    syncQueueMock.getAll.mockResolvedValue([]);
    syncQueueMock.update.mockResolvedValue(undefined);
    syncQueueMock.remove.mockResolvedValue(undefined);
  });

  it('successfully syncs a queued waste report and removes it from the queue', async () => {
    syncQueueMock.getAll.mockResolvedValue([
      { id: 'q1', input: SAMPLE_INPUT, status: 'pending', attempts: 0, lastError: null, createdAt: '2026-01-01T00:00:00.000Z' },
    ]);
    submissionsApiMock.create.mockResolvedValue(SAMPLE_SUBMISSION);

    const { result } = await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(submissionsApiMock.create).toHaveBeenCalledWith(SAMPLE_INPUT);
    });
    expect(syncQueueMock.remove).toHaveBeenCalledWith('q1');
    expect(result.current.failedCount).toBe(0);
  });

  it('keeps a validation failure as pending and increments attempts (bounded retry)', async () => {
    syncQueueMock.getAll.mockResolvedValue([
      { id: 'q1', input: SAMPLE_INPUT, status: 'pending', attempts: 2, lastError: null, createdAt: '2026-01-01T00:00:00.000Z' },
    ]);
    submissionsApiMock.create.mockRejectedValue(
      new ApiError('estimatedWeight must be positive', { code: 'VALIDATION_ERROR', status: 400 }),
    );

    await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(syncQueueMock.update).toHaveBeenCalledWith('q1', expect.objectContaining({ attempts: 3, status: 'pending' }));
    });
    expect(syncQueueMock.remove).not.toHaveBeenCalled();
  });

  it('marks an item failed once it exceeds the maximum retry attempts', async () => {
    syncQueueMock.getAll.mockResolvedValue([
      { id: 'q1', input: SAMPLE_INPUT, status: 'pending', attempts: 4, lastError: 'prior error', createdAt: '2026-01-01T00:00:00.000Z' },
    ]);
    submissionsApiMock.create.mockRejectedValue(
      new ApiError('estimatedWeight must be positive', { code: 'VALIDATION_ERROR', status: 400 }),
    );

    await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(syncQueueMock.update).toHaveBeenCalledWith('q1', expect.objectContaining({ attempts: 5, status: 'failed' }));
    });
  });

  it('stops the batch (without marking failed) on a network error, leaving the item pending for the next reconnect', async () => {
    syncQueueMock.getAll.mockResolvedValue([
      { id: 'q1', input: SAMPLE_INPUT, status: 'pending', attempts: 0, lastError: null, createdAt: '2026-01-01T00:00:00.000Z' },
    ]);
    submissionsApiMock.create.mockRejectedValue(new ApiError('offline', { code: 'NETWORK_ERROR', status: null }));

    await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(syncQueueMock.update).toHaveBeenCalledWith('q1', expect.objectContaining({ status: 'pending' }));
    });
    expect(syncQueueMock.remove).not.toHaveBeenCalled();
  });

  it('does not attempt to sync while offline from cold start', async () => {
    (NetInfo.fetch as jest.Mock).mockResolvedValue({ isConnected: false, isInternetReachable: false });
    syncQueueMock.getAll.mockResolvedValue([
      { id: 'q1', input: SAMPLE_INPUT, status: 'pending', attempts: 0, lastError: null, createdAt: '2026-01-01T00:00:00.000Z' },
    ]);

    await renderHook(() => useSyncManager());

    await waitFor(() => {
      expect(syncQueueMock.getAll).toHaveBeenCalled();
    });
    expect(submissionsApiMock.create).not.toHaveBeenCalled();
  });
});
