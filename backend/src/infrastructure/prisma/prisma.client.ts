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
