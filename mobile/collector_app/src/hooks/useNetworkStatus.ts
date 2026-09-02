import { useEffect, useState } from 'react';
import NetInfo, { type NetInfoState } from '@react-native-community/netinfo';

function toIsOnline(state: Pick<NetInfoState, 'isConnected' | 'isInternetReachable'>): boolean {
  return Boolean(state.isConnected && state.isInternetReachable !== false);
}

/** True when the device has real, usable internet connectivity. */
export function useNetworkStatus(): boolean {
  const [isOnline, setIsOnline] = useState(true);

  useEffect(() => {
    let cancelled = false;
    NetInfo.fetch().then((state) => {
      if (!cancelled) setIsOnline(toIsOnline(state));
    });

    const unsubscribe = NetInfo.addEventListener((state) => {
      setIsOnline(toIsOnline(state));
    });
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  return isOnline;
}

/**
 * Like `useNetworkStatus`, but starts as `null` ("not yet known") instead
 * of assuming online, and resolves the real state via `NetInfo.fetch()` on
 * mount. `useNetworkStatus` defaults optimistic-true so UI (e.g. the
 * offline banner) never flickers "offline" for online users during the
 * brief window before the real state arrives; this variant is for logic
 * that must never act on an unconfirmed connectivity guess — such as
 * `useSyncManager`, which should not spend a sync attempt (and its
 * associated retry-count) while the real state is still unknown,
 * especially on a cold start while genuinely offline.
 */
export function useKnownNetworkStatus(): boolean | null {
  const [isOnline, setIsOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    NetInfo.fetch().then((state) => {
      if (!cancelled) setIsOnline(toIsOnline(state));
    });

    const unsubscribe = NetInfo.addEventListener((state) => {
      setIsOnline(toIsOnline(state));
    });
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  return isOnline;
}
