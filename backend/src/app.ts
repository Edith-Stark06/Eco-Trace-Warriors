import express from 'express';
import type { Express } from 'express';
import type { AppConfig } from '@shared/config';
import type { Logger } from '@shared/logging';
import {
  authenticate,
  authorize,
  errorHandler,
  notFoundHandler,
  requestId,
  requestLogger,
} from '@shared/middleware';
import { getAppName, getAppVersion } from '@shared/utils';
import { getPrismaClient, pingDatabase } from '@infrastructure/prisma';
import { createHealthController, createHealthRouter, createHealthService } from '@modules/health';
import {
  API_NAME,
  createApiInfoController,
  createApiInfoRouter,
  createApiInfoService,
} from '@modules/api-info';
import {
  createAuthController,
  createAuthRouter,
  createAuthService,
  createPasswordService,
  createRefreshTokenRepository,
  createTokenService,
  createUserRepository,
} from '@modules/auth';
import type { RefreshTokenRepository, UserRepository } from '@modules/auth';
import {
  createSubmissionController,
  createSubmissionRepository,
  createSubmissionRouter,
  createSubmissionService,
} from '@modules/submission';
import type { SubmissionRepository } from '@modules/submission';
import {
  createRewardController,
  createRewardRepository,
  createRewardRouter,
  createRewardService,
} from '@modules/rewards';
import type { RewardRepository } from '@modules/rewards';

/** Everything the app needs from the outside world, injected explicitly. */
export interface AppDeps {
  readonly config: AppConfig;
  readonly logger: Logger;
  /** Test seam: database connectivity probe override for deterministic readiness tests. */
  readonly pingDatabase?: () => Promise<boolean>;
  /** Test seam: repository overrides so integration tests run without a database. */
  readonly authRepositories?: {
    readonly users: UserRepository;
    readonly refreshTokens: RefreshTokenRepository;
  };
  /** Test seam: submission repository override so integration tests run without a database. */
  readonly submissionRepository?: SubmissionRepository;
  /** Test seam: reward repository override so integration tests run without a database. */
  readonly rewardRepository?: RewardRepository;
}

/**
 * Assembles the Express application: middleware, module routers, error handling.
 * Pure assembly — no listening, no environment access — so tests can build
 * an app instance directly (see docs/engineering/06_BACKEND.md).
 */
export function createApp({
  config,
  logger,
  pingDatabase: pingDatabaseOverride,
  authRepositories,
  submissionRepository,
  rewardRepository,
}: AppDeps): Express {
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
    pingDatabase: pingDatabaseOverride ?? pingDatabase,
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

  // Auth module — repositories default to Prisma; tests may inject fakes.
  const users = authRepositories?.users ?? createUserRepository({ prisma: getPrismaClient() });
  const refreshTokens =
    authRepositories?.refreshTokens ?? createRefreshTokenRepository({ prisma: getPrismaClient() });
  const tokenService = createTokenService({
    accessSecret: config.jwtSecret,
    refreshSecret: config.jwtRefreshSecret,
    accessExpiry: config.jwtAccessExpiry,
    refreshExpiry: config.jwtRefreshExpiry,
  });
  const authService = createAuthService({
    users,
    refreshTokens,
    passwords: createPasswordService({ rounds: config.bcryptRounds }),
    tokens: tokenService,
    logger,
  });
  const authRouter = createAuthRouter(createAuthController(authService), {
    authenticate: authenticate(tokenService),
  });
  app.use(config.apiPrefix, authRouter);

  // Submission module — repository defaults to Prisma; tests may inject a fake.
  // Reuses the shared authenticate/authorize middleware — no new auth logic.
  const submissions =
    submissionRepository ?? createSubmissionRepository({ prisma: getPrismaClient() });
  const submissionService = createSubmissionService({ submissions, logger });
  const submissionRouter = createSubmissionRouter(createSubmissionController(submissionService), {
    authenticate: authenticate(tokenService),
    authorize,
  });
  app.use(config.apiPrefix, submissionRouter);

  // Rewards module — repository defaults to Prisma; tests may inject a fake.
  const rewards = rewardRepository ?? createRewardRepository({ prisma: getPrismaClient() });
  const rewardService = createRewardService({ rewards, submissions, logger });
  const rewardRouter = createRewardRouter(createRewardController(rewardService), {
    authenticate: authenticate(tokenService),
  });
  app.use(config.apiPrefix, rewardRouter);

  // Terminal handlers — must stay last
  app.use(notFoundHandler());
  app.use(errorHandler(logger));

  return app;
}
