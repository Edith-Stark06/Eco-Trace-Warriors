import { useCallback, useEffect, useRef, useState } from 'react';
import { deviceAiApi } from '../api/deviceAiApi';
import { syncQueueStorage } from '../storage/syncQueue';
import { useKnownNetworkStatus } from './useNetworkStatus';
import { ApiError } from '../api/ApiError';
import type { SyncQueueItem } from '../types/syncQueue';

const MAX_ATTEMPTS = 5;
/** Exponential backoff: 5s, 10s, 20s, 40s, capped at 2 minutes. */
const BACKOFF_BASE_MS = 5000;
const BACKOFF_MAX_MS = 2 * 60 * 1000;

function backoffDelayMs(attempts: number): number {
  return Math.min(BACKOFF_BASE_MS * 2 ** attempts, BACKOFF_MAX_MS);
}

function isDueForRetry(item: SyncQueueItem): boolean {
  if (item.status === 'failed' || item.status === 'conflict') return false;
  if (!item.nextRetryAt) return true;
  return new Date(item.nextRetryAt).getTime() <= Date.now();
}

/**
 * Drains the offline device-confirmation queue whenever the app is
 * online, retrying `finalize` for each queued device that is due (not
 * still inside its backoff window). A non-network ApiError marks the
 * item 'failed' after MAX_ATTEMPTS; a 409 CONFLICT (the device was
 * likely already finalized elsewhere) is terminal immediately —
 * retrying it would only conflict again, so it never counts toward or
 * respects the attempt bound, it just needs the user's attention.
 *
 * Uses `useKnownNetworkStatus` (not the optimistic-default
 * `useNetworkStatus`) to gate sync attempts: `knownIsOnline === true` is
 * required, so a cold app start never burns a sync attempt (and its
 * associated retry count) against a still-unconfirmed "probably online"
 * guess. The `isOnline` returned to callers still defaults to `true`
 * while unknown, so a UI banner never flickers "offline" for an
 * actually-online user during that same brief window.
 */
export function useSyncManager() {
  const knownIsOnline = useKnownNetworkStatus();
  const [queue, setQueue] = useState<SyncQueueItem[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const syncingRef = useRef(false);

  const refresh = useCallback(async () => {
    setQueue(await syncQueueStorage.getAll());
  }, []);

  const syncNow = useCallback(async () => {
    if (syncingRef.current || knownIsOnline !== true) return;
    syncingRef.current = true;
    setIsSyncing(true);
    try {
      const items = await syncQueueStorage.getAll();
      for (const item of items.filter(isDueForRetry)) {
        await syncQueueStorage.update(item.id, { status: 'syncing' });
        try {
          await deviceAiApi.finalize(item.deviceId);
          await syncQueueStorage.remove(item.id);
        } catch (err) {
          const isNetwork = err instanceof ApiError && err.isNetworkError;
          const isConflict = err instanceof ApiError && err.status === 409;
          const attempts = item.attempts + 1;
          await syncQueueStorage.update(item.id, {
            status: isConflict
              ? 'conflict'
              : !isNetwork && attempts >= MAX_ATTEMPTS
                ? 'failed'
                : 'pending',
            attempts,
            lastError: err instanceof Error ? err.message : 'Unknown sync error',
            nextRetryAt: isConflict ? null : new Date(Date.now() + backoffDelayMs(attempts)).toISOString(),
          });
          if (isNetwork) break; // stop the batch; we're offline again
        }
      }
    } finally {
      syncingRef.current = false;
      setIsSyncing(false);
      await refresh();
    }
  }, [knownIsOnline, refresh]);

  useEffect(() => {
    let cancelled = false;
    syncQueueStorage.getAll().then((items) => {
      if (!cancelled) setQueue(items);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (knownIsOnline === true) {
      void syncNow();
    }
  }, [knownIsOnline, syncNow]);

  const pendingCount = queue.filter((i) => i.status === 'pending' || i.status === 'syncing').length;
  const failedCount = queue.filter((i) => i.status === 'failed').length;
  const conflictCount = queue.filter((i) => i.status === 'conflict').length;

  return {
    queue,
    isOnline: knownIsOnline ?? true,
    isSyncing,
    pendingCount,
    failedCount,
    conflictCount,
    syncNow,
    refresh,
  };
}
