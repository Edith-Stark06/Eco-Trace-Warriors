import request from 'supertest';
import type { Express } from 'express';
import { UserRole } from '@prisma/client';
import { createApp } from '../../src/app';
import { loadConfig } from '@shared/config';
import { createLogger } from '@shared/logging';
import { createTokenService } from '@modules/auth';
import type { AnalyticsRepository } from '@modules/analytics';

const TEST_ENV = { NODE_ENV: 'test', LOG_LEVEL: 'fatal', BCRYPT_ROUNDS: '4' } as const;
const config = loadConfig(TEST_ENV);
const tokens = createTokenService({
  accessSecret: config.jwtSecret,
  refreshSecret: config.jwtRefreshSecret,
  accessExpiry: config.jwtAccessExpiry,
  refreshExpiry: config.jwtRefreshExpiry,
});

function tokenFor(userId: string, role: UserRole): string {
  return tokens.signAccessToken({ userId, email: `${userId}@example.com`, role });
}

const auth = (token: string): string => `Bearer ${token}`;

const GOVERNMENT = tokenFor('gov-1', UserRole.GOVERNMENT);
const ADMIN = tokenFor('admin-1', UserRole.ADMIN);
const CONSUMER = tokenFor('consumer-1', UserRole.CONSUMER);
const COLLECTOR = tokenFor('collector-1', UserRole.COLLECTOR);
const RECYCLER = tokenFor('recycler-1', UserRole.RECYCLER);

function fakeAnalyticsRepository(): AnalyticsRepository {
  return {
    getSubmissionStatusCounts: jest.fn().mockResolvedValue({
      total: 5,
      pending: 1,
      inProgress: 1,
      collected: 1,
      recycled: 2,
    }),
    getWeightTotals: jest.fn().mockResolvedValue({ estimatedWeight: 12, recoveredWeight: 8 }),
    getUserCounts: jest.fn().mockResolvedValue({ total: 6, collectors: 2, recyclers: 1 }),
    getTotalRewardPoints: jest.fn().mockResolvedValue(220),
    getEnvironmentalImpactTotals: jest
      .fn()
      .mockResolvedValue({ co2Saved: 50, energySaved: 30, landfillDiverted: 2 }),
    getRegionalBreakdown: jest.fn().mockResolvedValue([
      {
        region: 'Bengaluru',
        totalSubmissions: 5,
        totalWeight: 12,
        recycledWeight: 8,
        activeCollectors: 2,
        activeRecyclers: 1,
      },
    ]),
    getDailyRecycledWeightSeries: jest.fn().mockResolvedValue([
      { date: '2026-08-01', weightKg: 4 },
      { date: '2026-08-02', weightKg: 6 },
    ]),
  };
}

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

/** Fake device_ai /forecast/ewaste response used by the forecast tests below. */
function fakeForecastFetch(): typeof fetch {
  return jest.fn().mockResolvedValue(
    jsonResponse(200, {
      success: true,
      status: 'INSUFFICIENT_HISTORICAL_DATA',
      points: [],
      history: [],
      evaluation: null,
      model: null,
      history_days: 2,
      min_history_days_required: 30,
      lookback: 14,
      horizon: 30,
      reason: 'Only 2 day(s) of historical data are available.',
    }),
  );
}

function buildApp(opts: { fetchImpl?: typeof fetch } = {}): Express {
  const logger = createLogger(config);
  return createApp({
    config,
    logger,
    analyticsRepository: fakeAnalyticsRepository(),
    analyticsFetchImpl: opts.fetchImpl ?? fakeForecastFetch(),
  });
}

describe('Government Analytics — role access', () => {
  it.each([
    ['GOVERNMENT', GOVERNMENT],
    ['ADMIN', ADMIN],
  ])('%s can read /analytics/overview', async (_label, token) => {
    const app = buildApp();
    const res = await request(app)
      .get('/api/v1/analytics/overview')
      .set('Authorization', auth(token));

    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.data).toMatchObject({
      totalSubmissions: 5,
      pendingSubmissions: 1,
      inProgressSubmissions: 1,
      collectedSubmissions: 1,
      recycledSubmissions: 2,
      totalUsers: 6,
      totalCollectors: 2,
      totalRecyclers: 1,
      totalRewardsIssued: 220,
      weightUnit: 'kg',
    });
  });

  it.each([
    ['CONSUMER', CONSUMER],
    ['COLLECTOR', COLLECTOR],
    ['RECYCLER', RECYCLER],
  ])('%s is denied with 403, not logged out', async (_label, token) => {
    const app = buildApp();
    const res = await request(app)
      .get('/api/v1/analytics/overview')
      .set('Authorization', auth(token));

    expect(res.status).toBe(403);
  });

  it('rejects unauthenticated requests with 401', async () => {
    const app = buildApp();
    const res = await request(app).get('/api/v1/analytics/overview');
    expect(res.status).toBe(401);
  });

  it('returns the regional breakdown without fabricated state/lat/long', async () => {
    const app = buildApp();
    const res = await request(app)
      .get('/api/v1/analytics/regions')
      .set('Authorization', auth(GOVERNMENT));

    expect(res.status).toBe(200);
    expect(res.body.data.regions[0]).toMatchObject({
      region: 'Bengaluru',
      state: null,
      latitude: null,
      longitude: null,
    });
  });

  it('returns environmental impact with treesEquivalent left null', async () => {
    const app = buildApp();
    const res = await request(app)
      .get('/api/v1/analytics/environmental-impact')
      .set('Authorization', auth(GOVERNMENT));

    expect(res.status).toBe(200);
    expect(res.body.data).toMatchObject({
      co2Saved: 50,
      energySaved: 30,
      landfillDiverted: 2,
      treesEquivalent: null,
    });
  });

  it('proxies a real forecast from device_ai, honestly reporting insufficient data', async () => {
    const app = buildApp();
    const res = await request(app)
      .get('/api/v1/analytics/forecast')
      .set('Authorization', auth(GOVERNMENT));

    expect(res.status).toBe(200);
    expect(res.body.data).toMatchObject({
      status: 'INSUFFICIENT_HISTORICAL_DATA',
      points: [],
      model: null,
      weightUnit: 'kg',
    });
    expect(res.body.data.reason).toContain('2 day(s)');
  });

  it('accepts a horizon query parameter', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(
      jsonResponse(200, {
        success: true,
        status: 'INSUFFICIENT_HISTORICAL_DATA',
        points: [],
        history: [],
        evaluation: null,
        model: null,
        history_days: 2,
        min_history_days_required: 30,
        lookback: 14,
        horizon: 7,
        reason: 'not enough data',
      }),
    ) as unknown as typeof fetch;
    const app = buildApp({ fetchImpl });

    const res = await request(app)
      .get('/api/v1/analytics/forecast?horizon=7')
      .set('Authorization', auth(GOVERNMENT));

    expect(res.status).toBe(200);
    const [, init] = (fetchImpl as jest.Mock).mock.calls[0] as [string, RequestInit];
    const sentBody = JSON.parse(init.body as string) as { horizon: number };
    expect(sentBody.horizon).toBe(7);
  });

  it.each([0, -1, 91, 'abc'])('rejects an invalid horizon (%s) with 400', async (horizon) => {
    const app = buildApp();
    const res = await request(app)
      .get(`/api/v1/analytics/forecast?horizon=${horizon}`)
      .set('Authorization', auth(GOVERNMENT));

    expect(res.status).toBe(400);
  });

  it.each([
    ['CONSUMER', CONSUMER],
    ['COLLECTOR', COLLECTOR],
    ['RECYCLER', RECYCLER],
  ])('%s is denied /analytics/forecast with 403, not logged out', async (_label, token) => {
    const app = buildApp();
    const res = await request(app)
      .get('/api/v1/analytics/forecast')
      .set('Authorization', auth(token));

    expect(res.status).toBe(403);
  });
});
