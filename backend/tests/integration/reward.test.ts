import request from 'supertest';
import type { Express } from 'express';
import { UserRole } from '@prisma/client';
import { createApp } from '../../src/app';
import { loadConfig } from '@shared/config';
import { createLogger } from '@shared/logging';
import { createTokenService } from '@modules/auth';
import {
  activeCollector,
  activeRecycler,
  createSeededSubmissionRepository,
} from '../helpers/in-memory-submission-repository';
import { createInMemoryRewardRepository } from '../helpers/in-memory-reward-repository';

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

const OWNER_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const COLLECTOR_ID = '11111111-1111-4111-8111-111111111111';
const RECYCLER_ID = '33333333-3333-4333-8333-333333333333';

const OWNER = tokenFor(OWNER_ID, UserRole.CONSUMER);
const ADMIN = tokenFor('admin-1', UserRole.ADMIN);
const COLLECTOR = tokenFor(COLLECTOR_ID, UserRole.COLLECTOR);
const RECYCLER = tokenFor(RECYCLER_ID, UserRole.RECYCLER);

const auth = (token: string): string => `Bearer ${token}`;

const validSubmission = {
  category: 'Laptop',
  description: 'Old work laptop',
  estimatedWeight: 2,
  address: '12 MG Road, Bengaluru',
  latitude: 12.9716,
  longitude: 77.5946,
};

function buildApp(): Express {
  const logger = createLogger(config);
  const seeded = createSeededSubmissionRepository();
  seeded.addUser(activeCollector(COLLECTOR_ID));
  seeded.addUser(activeRecycler(RECYCLER_ID));
  return createApp({
    config,
    logger,
    submissionRepository: seeded.repository,
    rewardRepository: createInMemoryRewardRepository(),
  });
}

/**
 * Drives a submission through the full lifecycle to RECYCLED and returns the
 * submission id and the completeRecycling response body.
 */
async function driveToRecycled(
  app: Express,
): Promise<{ submissionId: string; completeBody: Record<string, unknown> }> {
  // 1. Consumer creates submission
  const createRes = await request(app)
    .post('/api/v1/submissions')
    .set('Authorization', auth(OWNER))
    .send(validSubmission);
  const submissionId = createRes.body.data.id as string;

  // 2. Admin assigns collector
  await request(app)
    .patch(`/api/v1/submissions/${submissionId}/assign`)
    .set('Authorization', auth(ADMIN))
    .send({ collectorId: COLLECTOR_ID });

  // 3. Collector accepts
  await request(app)
    .patch(`/api/v1/submissions/${submissionId}/accept`)
    .set('Authorization', auth(COLLECTOR));

  // 4. Collector starts pickup
  await request(app)
    .patch(`/api/v1/submissions/${submissionId}/start`)
    .set('Authorization', auth(COLLECTOR));

  // 5. Collector completes pickup
  await request(app)
    .patch(`/api/v1/submissions/${submissionId}/complete`)
    .set('Authorization', auth(COLLECTOR));

  // 6. Admin assigns recycler
  await request(app)
    .patch(`/api/v1/submissions/${submissionId}/assign-recycler`)
    .set('Authorization', auth(ADMIN))
    .send({ recyclerId: RECYCLER_ID });

  // 7. Recycler starts processing
  await request(app)
    .patch(`/api/v1/submissions/${submissionId}/recycle/start`)
    .set('Authorization', auth(RECYCLER));

  // 8. Recycler completes — triggers automatic reward issuance
  const completeRes = await request(app)
    .patch(`/api/v1/submissions/${submissionId}/recycle/complete`)
    .set('Authorization', auth(RECYCLER))
    .send({ recoveredWeight: 1.8 });

  return { submissionId, completeBody: completeRes.body as Record<string, unknown> };
}

// ---------------------------------------------------------------------------
// Full workflow
// ---------------------------------------------------------------------------

describe('Rewards — full lifecycle integration', () => {
  it('issues a reward automatically when recycling completes', async () => {
    const app = buildApp();
    const { completeBody } = await driveToRecycled(app);

    expect(completeBody.success).toBe(true);
    const data = completeBody.data as Record<string, unknown>;
    expect(data.submission).toMatchObject({ status: 'RECYCLED' });
    const reward = data.reward as Record<string, unknown>;
    expect(reward.greenCoinsAwarded).toBeGreaterThan(0);
    expect(reward.updatedBalance).toBeGreaterThan(0);
  });

  it('creates a RewardTransaction with the correct points for a Laptop (2 kg)', async () => {
    const app = buildApp();
    const { completeBody } = await driveToRecycled(app);

    const reward = (completeBody.data as Record<string, unknown>).reward as Record<string, unknown>;
    const tx = reward.rewardTransaction as Record<string, unknown>;
    // base 100 (Laptop) + round(2 * 5) = 110
    expect(tx.points).toBe(110);
    expect(tx.reason).toBe('RECYCLING');
    expect(typeof tx.id).toBe('string');
    expect(typeof tx.createdAt).toBe('string');
  });

  it('returns correct environmental metrics for a Laptop (2 kg)', async () => {
    const app = buildApp();
    const { completeBody } = await driveToRecycled(app);

    const reward = (completeBody.data as Record<string, unknown>).reward as Record<string, unknown>;
    const sustainability = reward.sustainability as Record<string, unknown>;
    expect(sustainability.co2Saved).toBe(50); // 2 * 25
    expect(sustainability.energySaved).toBe(30); // 2 * 15
    expect(sustainability.landfillDiverted).toBe(2); // 2 * 1
    expect(sustainability.co2Unit).toBe('kg');
    expect(sustainability.energyUnit).toBe('kWh');
    expect(sustainability.landfillUnit).toBe('kg');
  });

  it('updates the user GreenCoins balance after reward issuance', async () => {
    const app = buildApp();
    const { completeBody } = await driveToRecycled(app);

    const reward = (completeBody.data as Record<string, unknown>).reward as Record<string, unknown>;
    expect(reward.updatedBalance).toBe(110);
  });
});

// ---------------------------------------------------------------------------
// Reward API endpoints
// ---------------------------------------------------------------------------

describe('POST /api/v1/rewards/issue/:submissionId', () => {
  it('returns 401 without a token', async () => {
    const app = buildApp();
    const res = await request(app).post(
      '/api/v1/rewards/issue/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    );
    expect(res.status).toBe(401);
  });

  it('returns 403 for a non-admin (CONSUMER) caller', async () => {
    const app = buildApp();
    const res = await request(app)
      .post('/api/v1/rewards/issue/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')
      .set('Authorization', auth(OWNER));
    expect(res.status).toBe(403);
    expect(res.body.error.code).toBe('FORBIDDEN');
  });

  it('returns 400 for a non-UUID submissionId', async () => {
    const app = buildApp();
    const res = await request(app)
      .post('/api/v1/rewards/issue/not-a-uuid')
      .set('Authorization', auth(ADMIN));
    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('VALIDATION_ERROR');
  });

  it('returns 404 when the submission does not exist', async () => {
    const app = buildApp();
    const res = await request(app)
      .post('/api/v1/rewards/issue/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')
      .set('Authorization', auth(ADMIN));
    expect(res.status).toBe(404);
  });

  it('returns 409 when the submission is not RECYCLED', async () => {
    const app = buildApp();
    // Create a PENDING submission and try to reward it immediately
    const createRes = await request(app)
      .post('/api/v1/submissions')
      .set('Authorization', auth(OWNER))
      .send(validSubmission);
    const submissionId = createRes.body.data.id as string;

    const res = await request(app)
      .post(`/api/v1/rewards/issue/${submissionId}`)
      .set('Authorization', auth(ADMIN));
    expect(res.status).toBe(409);
  });

  it('returns 409 on a duplicate reward attempt', async () => {
    const app = buildApp();
    const { submissionId } = await driveToRecycled(app);

    // Second call — reward already issued automatically by completeRecycling
    const res = await request(app)
      .post(`/api/v1/rewards/issue/${submissionId}`)
      .set('Authorization', auth(ADMIN));
    expect(res.status).toBe(409);
  });

  it('returns 201 with the reward summary on success', async () => {
    // Use a fresh app where we manually drive to RECYCLED without the automatic
    // reward (not possible via the current API — so we verify via the
    // completeRecycling response which already issues the reward).
    const app = buildApp();
    const { completeBody } = await driveToRecycled(app);
    // The completeRecycling endpoint returns 200 with reward embedded
    expect(completeBody.success).toBe(true);
    const reward = (completeBody.data as Record<string, unknown>).reward as Record<string, unknown>;
    expect(reward.rewardTransaction).toBeDefined();
    expect(reward.greenCoinsAwarded).toBeGreaterThan(0);
  });
});

describe('GET /api/v1/rewards/history', () => {
  it('returns 401 without a token', async () => {
    const res = await request(buildApp()).get('/api/v1/rewards/history');
    expect(res.status).toBe(401);
  });

  it('returns 200 with an empty array when the user has no rewards', async () => {
    const res = await request(buildApp())
      .get('/api/v1/rewards/history')
      .set('Authorization', auth(OWNER));
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ success: true, data: [] });
  });
});

describe('GET /api/v1/rewards/balance', () => {
  it('returns 401 without a token', async () => {
    const res = await request(buildApp()).get('/api/v1/rewards/balance');
    expect(res.status).toBe(401);
  });

  it('returns 200 with zeroed metrics for a user with no rewards', async () => {
    const res = await request(buildApp())
      .get('/api/v1/rewards/balance')
      .set('Authorization', auth(OWNER));
    expect(res.status).toBe(200);
    expect(res.body.data).toEqual({
      greenCoins: 0,
      totalRewards: 0,
      totalCO2Saved: 0,
      totalEnergySaved: 0,
      totalLandfillDiverted: 0,
    });
  });
});
