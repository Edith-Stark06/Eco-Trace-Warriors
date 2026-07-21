import { PrismaClient } from '@prisma/client';

/**
 * Prisma Client singleton — the only place a PrismaClient is constructed.
 * Repositories receive it via injection; nothing else imports @prisma/client.
 * Connection is lazy: no database is required until the first query (Phase 3+).
 */
let prismaClient: PrismaClient | undefined;

export function getPrismaClient(): PrismaClient {
  prismaClient ??= new PrismaClient();
  return prismaClient;
}

/** Disconnects the client during graceful shutdown. Safe to call when never connected. */
export async function disconnectPrisma(): Promise<void> {
  if (prismaClient) {
    await prismaClient.$disconnect();
    prismaClient = undefined;
  }
}

/**
 * Lightweight connectivity probe for readiness checks.
 * Runs Prisma's recommended `SELECT 1` round-trip and resolves `true` only
 * when the database answers. Never throws — failures resolve to `false` so
 * callers can map the outcome to an HTTP status without try/catch.
 */
export async function pingDatabase(): Promise<boolean> {
  try {
    await getPrismaClient().$queryRaw`SELECT 1`;
    return true;
  } catch {
    return false;
  }
}
