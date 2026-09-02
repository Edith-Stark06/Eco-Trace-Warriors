import { useCallback, useEffect, useRef, useState } from 'react';
import { submissionsApi } from '../api/submissionsApi';
import { syncQueueStorage } from '../storage/syncQueue';
import { useKnownNetworkStatus } from './useNetworkStatus';
import { ApiError } from '../api/ApiError';
import type { SyncQueueItem } from '../types/syncQueue';

const MAX_ATTEMPTS = 5;

/**
 * Drains the offline waste-report queue whenever the app is online.
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
      for (const item of items.filter((i) => i.status !== 'failed')) {
        await syncQueueStorage.update(item.id, { status: 'syncing' });
        try {
          await submissionsApi.create(item.input);
          await syncQueueStorage.remove(item.id);
        } catch (err) {
          const isNetwork = err instanceof ApiError && err.isNetworkError;
          const attempts = item.attempts + 1;
          await syncQueueStorage.update(item.id, {
            status: !isNetwork && attempts >= MAX_ATTEMPTS ? 'failed' : 'pending',
            attempts,
            lastError: err instanceof Error ? err.message : 'Unknown sync error',
          });
          if (isNetwork) break;
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

  return { queue, isOnline: knownIsOnline ?? true, isSyncing, pendingCount, failedCount, syncNow, refresh };
}
