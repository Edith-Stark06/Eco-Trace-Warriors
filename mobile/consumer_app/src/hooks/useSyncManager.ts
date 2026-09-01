import { useCallback, useEffect, useRef, useState } from 'react';
import { submissionsApi } from '../api/submissionsApi';
import { syncQueueStorage } from '../storage/syncQueue';
import { useNetworkStatus } from './useNetworkStatus';
import { ApiError } from '../api/ApiError';
import type { SyncQueueItem } from '../types/syncQueue';

const MAX_ATTEMPTS = 5;

/** Drains the offline waste-report queue whenever the app is online. */
export function useSyncManager() {
  const isOnline = useNetworkStatus();
  const [queue, setQueue] = useState<SyncQueueItem[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const syncingRef = useRef(false);

  const refresh = useCallback(async () => {
    setQueue(await syncQueueStorage.getAll());
  }, []);

  const syncNow = useCallback(async () => {
    if (syncingRef.current || !isOnline) return;
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
  }, [isOnline, refresh]);

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
    if (isOnline) {
      void syncNow();
    }
  }, [isOnline, syncNow]);

  const pendingCount = queue.filter((i) => i.status === 'pending' || i.status === 'syncing').length;
  const failedCount = queue.filter((i) => i.status === 'failed').length;

  return { queue, isOnline, isSyncing, pendingCount, failedCount, syncNow, refresh };
}
