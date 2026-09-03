import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

/**
 * Thin wrapper over platform-appropriate token storage. Callers only ever
 * see `getAccessToken`/`getRefreshToken`/`setTokens`/`clearTokens` — which
 * backend answers them is an internal, platform-selected detail.
 *
 * Native (iOS/Android): expo-secure-store (Keychain on iOS, Keystore-backed
 * EncryptedSharedPreferences on Android) — mirrors the Flutter app's
 * flutter_secure_storage-backed SecureStorageService (P8.7): access/refresh
 * tokens never touch plain AsyncStorage.
 *
 * Web: expo-secure-store ships no real web backend — its web module
 * (`ExpoSecureStore.web.js`) is an empty stub — so calling it there throws
 * `getValueWithKeyAsync is not a function` (Collector's CHANGE-007; same
 * defect confirmed here for Consumer Web). Falls back to the browser's
 * `localStorage`, which does NOT provide the same security properties as a
 * native secure enclave/keystore: it is plain, unencrypted, per-origin
 * storage readable by any script running on the page (e.g. an XSS vector)
 * and by browser devtools. This is a deliberate, web-only trade-off —
 * native platforms are unaffected and unchanged.
 */
const ACCESS_TOKEN_KEY = 'ecotrace_consumer_access_token';
const REFRESH_TOKEN_KEY = 'ecotrace_consumer_refresh_token';

/**
 * `localStorage` access guarded against environments where it is absent or
 * throws (a locked-down browsing context, private-mode quota limits, or a
 * non-browser JS runtime evaluating this module). A storage failure on web
 * degrades to "no persisted session" rather than crashing app startup —
 * never logs the key or value involved.
 */
const webStorage = {
  getItem(key: string): string | null {
    try {
      return globalThis.localStorage?.getItem(key) ?? null;
    } catch {
      return null;
    }
  },
  setItem(key: string, value: string): void {
    try {
      globalThis.localStorage?.setItem(key, value);
    } catch {
      // Storage unavailable or full — session won't persist across reloads.
    }
  },
  removeItem(key: string): void {
    try {
      globalThis.localStorage?.removeItem(key);
    } catch {
      // Nothing to clean up if storage was never reachable.
    }
  },
};

// Checked per call (not cached at module scope) so tests can select a
// platform per case; production behavior is unaffected since Platform.OS
// never changes within a running app instance.
async function getItem(key: string): Promise<string | null> {
  return Platform.OS === 'web' ? webStorage.getItem(key) : SecureStore.getItemAsync(key);
}

async function setItem(key: string, value: string): Promise<void> {
  if (Platform.OS === 'web') {
    webStorage.setItem(key, value);
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

async function removeItem(key: string): Promise<void> {
  if (Platform.OS === 'web') {
    webStorage.removeItem(key);
    return;
  }
  await SecureStore.deleteItemAsync(key);
}

export const secureStorage = {
  async getAccessToken(): Promise<string | null> {
    return getItem(ACCESS_TOKEN_KEY);
  },
  async getRefreshToken(): Promise<string | null> {
    return getItem(REFRESH_TOKEN_KEY);
  },
  async setTokens(accessToken: string, refreshToken: string): Promise<void> {
    await Promise.all([setItem(ACCESS_TOKEN_KEY, accessToken), setItem(REFRESH_TOKEN_KEY, refreshToken)]);
  },
  async clearTokens(): Promise<void> {
    await Promise.all([removeItem(ACCESS_TOKEN_KEY), removeItem(REFRESH_TOKEN_KEY)]);
  },
};
