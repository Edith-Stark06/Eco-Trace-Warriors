import express from 'express';
import type { Express } from 'express';
import type { AppConfig } from '@shared/config';
import type { Logger } from '@shared/logging';
import {
  authenticate,
  authorize,
  authRateLimiter,
  cors,
  errorHandler,
  notFoundHandler,
  requestId,
  requestLogger,
  securityHeaders,
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
import { createUsersController, createUsersRouter, createUsersService } from '@modules/users';
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
import {
  createBlockchainController,
  createBlockchainRouter,
  createBlockchainService,
} from '@modules/blockchain';
import type { BlockchainService } from '@modules/blockchain';

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
  /** Test seam: blockchain service override so tests don't make a real HTTP call. */
  readonly blockchainService?: BlockchainService;
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
  blockchainService: blockchainServiceOverride,
}: AppDeps): Express {
  const app = express();

  app.disable('x-powered-by');
  app.use(securityHeaders());
  app.use(cors(config.corsOrigins));
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
    rateLimiter: authRateLimiter(config.authRateLimit),
  });
  app.use(config.apiPrefix, authRouter);

  // Users module — directory lookup for assignment workflows. Reuses the auth
  // module's user repository (single owner of the user table) so no second
  // Prisma access point is introduced.
  const usersService = createUsersService({ users });
  const usersRouter = createUsersRouter(createUsersController(usersService), {
    authenticate: authenticate(tokenService),
    authorize,
  });
  app.use(config.apiPrefix, usersRouter);

  // Submission module — repository defaults to Prisma; tests may inject a fake.
  // Reuses the shared authenticate/authorize middleware — no new auth logic.
  const submissions =
    submissionRepository ?? createSubmissionRepository({ prisma: getPrismaClient() });

  // Rewards module — repository defaults to Prisma; tests may inject a fake.
  const rewards = rewardRepository ?? createRewardRepository({ prisma: getPrismaClient() });
  const rewardService = createRewardService({ rewards, submissions, logger });

  const submissionService = createSubmissionService({
    submissions,
    logger,
    rewards: rewardService,
  });
  const submissionRouter = createSubmissionRouter(createSubmissionController(submissionService), {
    authenticate: authenticate(tokenService),
    authorize,
  });
  app.use(config.apiPrefix, submissionRouter);

  const rewardRouter = createRewardRouter(createRewardController(rewardService), {
    authenticate: authenticate(tokenService),
    authorize,
  });
  app.use(config.apiPrefix, rewardRouter);

  // Blockchain module — read-only proxy to the Python intelligence/device_ai
  // service's Fabric Gateway health check (P6.5). This backend does not
  // hold its own Fabric connection; see modules/blockchain/blockchain.service.ts.
  const blockchainService =
    blockchainServiceOverride ??
    createBlockchainService({
      deviceAiServiceUrl: config.deviceAiServiceUrl,
      timeoutMs: config.deviceAiTimeoutMs,
      logger,
    });
  const blockchainRouter = createBlockchainRouter(createBlockchainController(blockchainService));
  app.use(config.apiPrefix, blockchainRouter);

  // Terminal handlers — must stay last
  app.use(notFoundHandler());
  app.use(errorHandler(logger));

  return app;
}
