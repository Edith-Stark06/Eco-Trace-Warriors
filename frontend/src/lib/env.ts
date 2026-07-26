/**
 * Typed, centralized access to Vite environment variables.
 *
 * All `import.meta.env.VITE_*` reads happen here so the rest of the app
 * never touches raw env strings (see CLAUDE.md → no hardcoded values).
 */

interface AppEnv {
  apiBaseUrl: string;
  apiTimeout: number;
  appName: string;
  isDev: boolean;
  isProd: boolean;
}

function readNumber(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export const env: AppEnv = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:3000/api/v1',
  apiTimeout: readNumber(import.meta.env.VITE_API_TIMEOUT, 15000),
  appName: import.meta.env.VITE_APP_NAME ?? 'EcoTrace India',
  isDev: import.meta.env.DEV,
  isProd: import.meta.env.PROD,
};
