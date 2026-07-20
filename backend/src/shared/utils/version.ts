import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { existsSync } from 'node:fs';

/**
 * Resolves the application version from the nearest package.json.
 * Works from both src/ (tsx) and dist/ (compiled) without importing
 * package.json into the TypeScript build graph.
 */
export function getAppVersion(startDir: string = __dirname): string {
  let current = startDir;

  for (let depth = 0; depth < 6; depth += 1) {
    const candidate = join(current, 'package.json');
    if (existsSync(candidate)) {
      const parsed = JSON.parse(readFileSync(candidate, 'utf8')) as { version?: string };
      return parsed.version ?? '0.0.0';
    }
    const parent = dirname(current);
    if (parent === current) break;
    current = parent;
  }

  return '0.0.0';
}
