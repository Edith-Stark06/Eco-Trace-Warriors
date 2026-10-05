import { readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';

interface PackageManifest {
  readonly name?: string;
  readonly version?: string;
}

/**
 * Reads the nearest package.json, walking up from `startDir`.
 * Works from both src/ (tsx) and dist/ (compiled) without importing
 * package.json into the TypeScript build graph. Returns an empty
 * manifest if none is found within the search depth.
 */
function readManifest(startDir: string): PackageManifest {
  let current = startDir;

  for (let depth = 0; depth < 6; depth += 1) {
    const candidate = join(current, 'package.json');
    if (existsSync(candidate)) {
      return JSON.parse(readFileSync(candidate, 'utf8')) as PackageManifest;
    }
    const parent = dirname(current);
    if (parent === current) break;
    current = parent;
  }

  return {};
}

/** Resolves the application version from the nearest package.json. */
export function getAppVersion(startDir: string = __dirname): string {
  return readManifest(startDir).version ?? '0.0.0';
}

/** Resolves the application (service) name from the nearest package.json. */
export function getAppName(startDir: string = __dirname): string {
  return readManifest(startDir).name ?? 'unknown';
}
