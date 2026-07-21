import express from 'express';
import type { Express } from 'express';
import type { AppConfig } from '@shared/config';
import type { Logger } from '@shared/logging';
import { errorHandler, notFoundHandler, requestId, requestLogger } from '@shared/middleware';
import { getAppName, getAppVersion } from '@shared/utils';
import { pingDatabase } from '@infrastructure/prisma';
import { createHealthController, createHealthRouter, createHealthService } from '@modules/health';
import {
  API_NAME,
  createApiInfoController,
  createApiInfoRouter,
  createApiInfoService,
} from '@modules/api-info';

/** Everything the app needs from the outside world, injected explicitly. */
export interface AppDeps {
  readonly config: AppConfig;
  readonly logger: Logger;
}

/**
 * Assembles the Express application: middleware, module routers, error handling.
 * Pure assembly — no listening, no environment access — so tests can build
 * an app instance directly (see docs/engineering/06_BACKEND.md).
 */
export function createApp({ config, logger }: AppDeps): Express {
  const app = express();

  app.disable('x-powered-by');
  app.use(express.json({ limit: '1mb' }));
  app.use(requestId());
  app.use(requestLogger(logger));

  // Module routers
  const healthService = createHealthService({
    version: getAppVersion(),
    serviceName: getAppName(),
    environment: config.nodeEnv,
    pingDatabase,
  });
  const healthRouter = createHealthRouter(createHealthController(healthService));
  app.use(config.apiPrefix, healthRouter);

  const apiInfoService = createApiInfoService({
    name: API_NAME,
    // API version label is the last segment of the mounted prefix (e.g. "/api/v1" → "v1").
    version: config.apiPrefix.split('/').filter(Boolean).at(-1) ?? 'v1',
    environment: config.nodeEnv,
    documentationPath: `${config.apiPrefix}/docs`,
  });
  const apiInfoRouter = createApiInfoRouter(createApiInfoController(apiInfoService));
  app.use(config.apiPrefix, apiInfoRouter);

  // Terminal handlers — must stay last
  app.use(notFoundHandler());
  app.use(errorHandler(logger));

  return app;
}
