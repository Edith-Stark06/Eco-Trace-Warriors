/**
 * Runtime configuration for the Collector app.
 *
 * Mirrors the Flutter app's `AppConfig`/`assertSecureApiUrl` pattern (P8.7):
 * the API base URL is read from an Expo public env var at build time
 * (`EXPO_PUBLIC_API_BASE_URL`), never hardcoded, and a release build must
 * never point at plaintext HTTP.
 */
const DEFAULT_DEV_API_BASE_URL = 'http://localhost:3000/api/v1';
const DEFAULT_DEV_DEVICE_AI_BASE_URL = 'http://localhost:8100';

export class InsecureApiUrlError extends Error {
  constructor(url: string) {
    super(`Refusing to use insecure API URL in a release build: ${url}`);
    this.name = 'InsecureApiUrlError';
  }
}

/** Throws in a release build if `url` is not HTTPS (loopback/private-LAN dev hosts excepted). */
export function assertSecureApiUrl(url: string, isReleaseBuild: boolean): void {
  if (!isReleaseBuild) {
    return;
  }
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new InsecureApiUrlError(url);
  }
  if (parsed.protocol !== 'https:') {
    throw new InsecureApiUrlError(url);
  }
}

const isReleaseBuild = !__DEV__;

export const env = {
  apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? DEFAULT_DEV_API_BASE_URL,
  deviceAiBaseUrl: process.env.EXPO_PUBLIC_DEVICE_AI_BASE_URL ?? DEFAULT_DEV_DEVICE_AI_BASE_URL,
  isReleaseBuild,
};

assertSecureApiUrl(env.apiBaseUrl, env.isReleaseBuild);
assertSecureApiUrl(env.deviceAiBaseUrl, env.isReleaseBuild);
