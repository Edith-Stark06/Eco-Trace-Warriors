import 'dotenv/config';
import type { Server } from 'node:http';
import { getConfig } from '@shared/config';
import { createLogger } from '@shared/logging';
import { disconnectPrisma } from '@infrastructure/prisma';
import { createApp } from './app';

/**
 * Process entry point: load config, build the app, listen, handle shutdown.
 * Kept separate from app assembly so tests never bind a port.
 */
function main(): void {
  const config = getConfig();
  const logger = createLogger(config);

  const app = createApp({ config, logger });

  const server: Server = app.listen(config.port, () => {
    logger.info(
      { port: config.port, env: config.nodeEnv, apiPrefix: config.apiPrefix },
      'EcoTrace backend started',
    );
  });

  const shutdown = (signal: string): void => {
    logger.info({ signal }, 'Shutting down');
    server.close(() => {
      disconnectPrisma()
        .catch((err: unknown) => logger.error({ err }, 'Error during Prisma disconnect'))
        .finally(() => process.exit(0));
    });
    // Force-exit if connections refuse to drain.
    setTimeout(() => process.exit(1), 10_000).unref();
  };

  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));

  process.on('unhandledRejection', (reason) => {
    logger.fatal({ err: reason }, 'Unhandled promise rejection');
    process.exit(1);
  });
}

main();
