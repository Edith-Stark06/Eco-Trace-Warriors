import { useEffect, useState } from 'react';
import NetInfo from '@react-native-community/netinfo';

/** True when the device has real, usable internet connectivity. */
export function useNetworkStatus(): boolean {
  const [isOnline, setIsOnline] = useState(true);

  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener((state) => {
      setIsOnline(Boolean(state.isConnected && state.isInternetReachable !== false));
    });
    return unsubscribe;
  }, []);

  return isOnline;
}
