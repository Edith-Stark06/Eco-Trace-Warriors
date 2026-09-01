import * as SecureStore from 'expo-secure-store';

/**
 * Thin wrapper over expo-secure-store (Keychain on iOS, Keystore-backed
 * EncryptedSharedPreferences on Android) — mirrors the Flutter app's
 * flutter_secure_storage-backed SecureStorageService (P8.7): access/refresh
 * tokens never touch plain AsyncStorage.
 */
const ACCESS_TOKEN_KEY = 'ecotrace_collector_access_token';
const REFRESH_TOKEN_KEY = 'ecotrace_collector_refresh_token';

export const secureStorage = {
  async getAccessToken(): Promise<string | null> {
    return SecureStore.getItemAsync(ACCESS_TOKEN_KEY);
  },
  async getRefreshToken(): Promise<string | null> {
    return SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
  },
  async setTokens(accessToken: string, refreshToken: string): Promise<void> {
    await Promise.all([
      SecureStore.setItemAsync(ACCESS_TOKEN_KEY, accessToken),
      SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refreshToken),
    ]);
  },
  async clearTokens(): Promise<void> {
    await Promise.all([
      SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
      SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY),
    ]);
  },
};
