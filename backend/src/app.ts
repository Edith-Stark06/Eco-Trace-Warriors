import express from 'express';
import type { Express } from 'express';
import type { AppConfig } from '@shared/config';
import type { Logger } from '@shared/logging';
import {
  apiRateLimiter,
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
import { createMetricsRegistry, metricsMiddleware } from '@shared/metrics';
import type { MetricsRegistry } from '@shared/metrics';
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
  createNotificationController,
  createNotificationRepository,
  createNotificationRouter,
  createNotificationService,
} from '@modules/notification';
import type { NotificationRepository } from '@modules/notification';
import {
  createBlockchainController,
  createBlockchainRouter,
  createBlockchainService,
} from '@modules/blockchain';
import type { BlockchainService } from '@modules/blockchain';
import { createMetricsController, createMetricsRouter } from '@modules/metrics';
import {
  createAnalyticsController,
  createAnalyticsRepository,
  createAnalyticsRouter,
  createAnalyticsService,
} from '@modules/analytics';
import type { AnalyticsRepository } from '@modules/analytics';

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
  /** Test seam: notification repository override so integration tests run without a database. */
  readonly notificationRepository?: NotificationRepository;
  /** Test seam: blockchain service override so tests don't make a real HTTP call. */
  readonly blockchainService?: BlockchainService;
  /** Test seam: metrics registry override so tests can assert on recorded metrics directly. */
  readonly metricsRegistry?: MetricsRegistry;
  /** Test seam: analytics repository override so integration tests run without a database. */
  readonly analyticsRepository?: AnalyticsRepository;
  /** Test seam: fetch implementation for the analytics module's device_ai forecast
   *  proxy call, so tests don't make a real HTTP request. */
  readonly analyticsFetchImpl?: typeof fetch;
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
  notificationRepository,
  blockchainService: blockchainServiceOverride,
  metricsRegistry: metricsRegistryOverride,
  analyticsRepository: analyticsRepositoryOverride,
  analyticsFetchImpl,
}: AppDeps): Express {
  const app = express();
  const metricsRegistry = metricsRegistryOverride ?? createMetricsRegistry();

  app.disable('x-powered-by');
  app.use(securityHeaders());
  app.use(cors(config.corsOrigins));
  app.use(express.json({ limit: '1mb' }));
  app.use(requestId());
  app.use(requestLogger(logger));
  app.use(metricsMiddleware(metricsRegistry));

  // Module routers
  const healthService = createHealthService({
    version: getAppVersion(),
    serviceName: getAppName(),
    environment: config.nodeEnv,
    pingDatabase: pingDatabaseOverride ?? pingDatabase,
  });
  const healthRouter = createHealthRouter(createHealthController(healthService));
  app.use(config.apiPrefix, healthRouter);

  // General-purpose rate limiting (P7.4) — mounted after the health router
  // so liveness/readiness polling (frequent, from orchestrators/load
  // balancers) is never throttled; applies to every route registered below.
  app.use(config.apiPrefix, apiRateLimiter(config.apiRateLimit));

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
  const passwordService = createPasswordService({ rounds: config.bcryptRounds });
  const authService = createAuthService({
    users,
    refreshTokens,
    passwords: passwordService,
    tokens: tokenService,
    logger,
  });
  const authRouter = createAuthRouter(createAuthController(authService), {
    authenticate: authenticate(tokenService),
    rateLimiter: authRateLimiter(config.authRateLimit),
  });
  app.use(config.apiPrefix, authRouter);

  // Users module — directory lookup for assignment workflows, plus ADMIN-only
  // provisioning of operational accounts (POST /users). Reuses the auth
  // module's user repository and password service (single owner of the user
  // table) so no second Prisma access point is introduced.
  const usersService = createUsersService({ users, passwords: passwordService, logger });
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

  // Notification module (P10.3) — in-app, Consumer-only. Repository defaults
  // to Prisma; tests may inject a fake. Constructed before the submission
  // service, which calls it (best-effort) at the three approved lifecycle
  // hooks — see submission.service.ts.
  const notifications =
    notificationRepository ?? createNotificationRepository({ prisma: getPrismaClient() });
  const notificationService = createNotificationService({ notifications, logger });

  const submissionService = createSubmissionService({
    submissions,
    logger,
    rewards: rewardService,
    notifications: notificationService,
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

  const notificationRouter = createNotificationRouter(
    createNotificationController(notificationService),
    { authenticate: authenticate(tokenService), authorize },
  );
  app.use(config.apiPrefix, notificationRouter);

  // Blockchain module — read-only proxy to the Python intelligence/device_ai
  // service's Fabric Gateway health check (P6.5). This backend does not
  // hold its own Fabric connection; see modules/blockchain/blockchain.service.ts.
  const blockchainService =
    blockchainServiceOverride ??
    createBlockchainService({
      deviceAiServiceUrl: config.deviceAiServiceUrl,
      timeoutMs: config.deviceAiTimeoutMs,
      logger,
      onCheck: (status) => metricsRegistry.recordBlockchainCheck(status),
    });
  const blockchainRouter = createBlockchainRouter(createBlockchainController(blockchainService));
  app.use(config.apiPrefix, blockchainRouter);

  // Metrics module (P7.3) — in-process request/blockchain-check counters,
  // no external scrape target required (see shared/metrics/metrics.ts).
  const metricsRouter = createMetricsRouter(createMetricsController(metricsRegistry));
  app.use(config.apiPrefix, metricsRouter);

  // Analytics module (Government oversight dashboard) — read-only reporting
  // over the existing submission/user/reward tables; repository defaults to
  // Prisma, tests may inject a fake. `/analytics/forecast` is not mounted —
  // see analytics.routes.ts for why.
  const analytics =
    analyticsRepositoryOverride ?? createAnalyticsRepository({ prisma: getPrismaClient() });
  const analyticsService = createAnalyticsService({
    analytics,
    logger,
    deviceAiServiceUrl: config.deviceAiServiceUrl,
    deviceAiTimeoutMs: config.deviceAiTimeoutMs,
    fetchImpl: analyticsFetchImpl,
  });
  const analyticsRouter = createAnalyticsRouter(createAnalyticsController(analyticsService), {
    authenticate: authenticate(tokenService),
    authorize,
  });
  app.use(config.apiPrefix, analyticsRouter);

  // Terminal handlers — must stay last
  app.use(notFoundHandler());
  app.use(errorHandler(logger));

  return app;
}
