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
import { createInMemoryNotificationRepository } from '../helpers/in-memory-notification-repository';

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
const OTHER_OWNER_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const COLLECTOR_ID = '11111111-1111-4111-8111-111111111111';
const RECYCLER_ID = '33333333-3333-4333-8333-333333333333';

const OWNER = tokenFor(OWNER_ID, UserRole.CONSUMER);
const OTHER_OWNER = tokenFor(OTHER_OWNER_ID, UserRole.CONSUMER);
const ADMIN = tokenFor('admin-1', UserRole.ADMIN);
const COLLECTOR = tokenFor(COLLECTOR_ID, UserRole.COLLECTOR);
const RECYCLER = tokenFor(RECYCLER_ID, UserRole.RECYCLER);

const auth = (token: string): string => `Bearer ${token}`;

/** Minimal shape used by these tests — mirrors `PublicNotification`. */
interface NotificationBody {
  id: string;
  submissionId: string;
  type: string;
  message: string;
  readAt: string | null;
  isRead: boolean;
}

/** Typed accessor for a notification-list response body, to avoid `any`-typed array calls. */
function notificationsOf(res: request.Response): NotificationBody[] {
  return res.body.data as NotificationBody[];
}

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
    // Every integration test in this codebase injects a fake for each
    // repository it touches so the suite never depends on a real database
    // (see reward.test.ts, submission.test.ts) — the notification module
    // gets the same treatment here.
    notificationRepository: createInMemoryNotificationRepository(),
  });
}

async function createSubmission(app: Express, token = OWNER): Promise<string> {
  const res = await request(app)
    .post('/api/v1/submissions')
    .set('Authorization', auth(token))
    .send(validSubmission);
  return res.body.data.id as string;
}

async function assignCollector(app: Express, submissionId: string): Promise<void> {
  await request(app)
    .patch(`/api/v1/submissions/${submissionId}/assign`)
    .set('Authorization', auth(ADMIN))
    .send({ collectorId: COLLECTOR_ID });
}

async function driveToCollected(app: Express, submissionId: string): Promise<void> {
  await assignCollector(app, submissionId);
  await request(app)
    .patch(`/api/v1/submissions/${submissionId}/accept`)
    .set('Authorization', auth(COLLECTOR));
  await request(app)
    .patch(`/api/v1/submissions/${submissionId}/start`)
    .set('Authorization', auth(COLLECTOR));
  await request(app)
    .patch(`/api/v1/submissions/${submissionId}/complete`)
    .set('Authorization', auth(COLLECTOR));
}

async function driveToRecycled(
  app: Express,
  submissionId: string,
): Promise<{ greenCoinsAwarded: number }> {
  await request(app)
    .patch(`/api/v1/submissions/${submissionId}/assign-recycler`)
    .set('Authorization', auth(ADMIN))
    .send({ recyclerId: RECYCLER_ID });
  await request(app)
    .patch(`/api/v1/submissions/${submissionId}/recycle/start`)
    .set('Authorization', auth(RECYCLER));
  const res = await request(app)
    .patch(`/api/v1/submissions/${submissionId}/recycle/complete`)
    .set('Authorization', auth(RECYCLER))
    .send({ recoveredWeight: 1.8 });
  return { greenCoinsAwarded: res.body.data.reward.greenCoinsAwarded as number };
}

describe('Notifications (P10.3) — real lifecycle-triggered, in-app, consumer-only', () => {
  describe('lifecycle hooks create real notifications', () => {
    it('creates a COLLECTOR_ASSIGNED notification for the owner when a collector is assigned', async () => {
      const app = buildApp();
      const submissionId = await createSubmission(app);
      await assignCollector(app, submissionId);

      const res = await request(app).get('/api/v1/notifications').set('Authorization', auth(OWNER));

      expect(res.status).toBe(200);
      expect(res.body.data).toHaveLength(1);
      expect(res.body.data[0]).toMatchObject({
        submissionId,
        type: 'COLLECTOR_ASSIGNED',
        message: 'Your collector has been assigned for your Laptop submission.',
        isRead: false,
        readAt: null,
      });
      // Never leaks the collector's identity.
      expect(res.body.data[0].message).not.toContain(COLLECTOR_ID);
      expect(res.body.data[0]).not.toHaveProperty('userId');
    });

    it('creates an ITEM_COLLECTED notification once the item is actually collected', async () => {
      const app = buildApp();
      const submissionId = await createSubmission(app);
      await driveToCollected(app, submissionId);

      const res = await request(app).get('/api/v1/notifications').set('Authorization', auth(OWNER));

      const collected = notificationsOf(res).find((n) => n.type === 'ITEM_COLLECTED');
      expect(collected).toMatchObject({
        submissionId,
        message: 'Your Laptop has been collected and is ready for recycling.',
      });
    });

    it('creates a RECYCLING_COMPLETED notification with the real, backend-issued GreenCoins amount', async () => {
      const app = buildApp();
      const submissionId = await createSubmission(app);
      await driveToCollected(app, submissionId);
      const { greenCoinsAwarded } = await driveToRecycled(app, submissionId);

      const res = await request(app).get('/api/v1/notifications').set('Authorization', auth(OWNER));

      const recycled = notificationsOf(res).find((n) => n.type === 'RECYCLING_COMPLETED');
      expect(recycled).toMatchObject({
        submissionId,
        message: `Your Laptop has been recycled and ${greenCoinsAwarded} GreenCoins have been issued.`,
      });
    });

    it('returns exactly 3 notifications (one per real event) after the full lifecycle, newest first', async () => {
      const app = buildApp();
      const submissionId = await createSubmission(app);
      await driveToCollected(app, submissionId);
      await driveToRecycled(app, submissionId);

      const res = await request(app).get('/api/v1/notifications').set('Authorization', auth(OWNER));

      const notifications = notificationsOf(res);
      expect(notifications).toHaveLength(3);
      expect(notifications.map((n) => n.type)).toEqual([
        'RECYCLING_COMPLETED',
        'ITEM_COLLECTED',
        'COLLECTOR_ASSIGNED',
      ]);
    });
  });

  describe('duplicate prevention', () => {
    it('never creates a second COLLECTOR_ASSIGNED notification when an admin re-assigns (override)', async () => {
      const app = buildApp();
      const submissionId = await createSubmission(app);
      await assignCollector(app, submissionId);
      // Admin override re-assign — same submission, same event type.
      await request(app)
        .patch(`/api/v1/submissions/${submissionId}/assign`)
        .set('Authorization', auth(ADMIN))
        .send({ collectorId: COLLECTOR_ID });

      const res = await request(app).get('/api/v1/notifications').set('Authorization', auth(OWNER));

      const assigned = notificationsOf(res).filter((n) => n.type === 'COLLECTOR_ASSIGNED');
      expect(assigned).toHaveLength(1);
    });
  });

  describe('GET /api/v1/notifications — security scoping', () => {
    it("never returns another consumer's notifications", async () => {
      const app = buildApp();
      const submissionId = await createSubmission(app, OWNER);
      await assignCollector(app, submissionId);

      const res = await request(app)
        .get('/api/v1/notifications')
        .set('Authorization', auth(OTHER_OWNER));

      expect(res.status).toBe(200);
      expect(res.body.data).toHaveLength(0);
    });

    it('returns 403 for a non-consumer role (collector)', async () => {
      const app = buildApp();

      const res = await request(app)
        .get('/api/v1/notifications')
        .set('Authorization', auth(COLLECTOR));

      expect(res.status).toBe(403);
    });

    it('returns 403 for a non-consumer role (admin)', async () => {
      const app = buildApp();

      const res = await request(app).get('/api/v1/notifications').set('Authorization', auth(ADMIN));

      expect(res.status).toBe(403);
    });

    it('returns 401 without a token', async () => {
      const app = buildApp();

      const res = await request(app).get('/api/v1/notifications');

      expect(res.status).toBe(401);
    });
  });

  describe('PATCH /api/v1/notifications/:id/read', () => {
    async function getFirstNotificationId(app: Express, token: string): Promise<string> {
      const res = await request(app).get('/api/v1/notifications').set('Authorization', auth(token));
      return res.body.data[0].id as string;
    }

    it("marks the caller's own notification read", async () => {
      const app = buildApp();
      const submissionId = await createSubmission(app);
      await assignCollector(app, submissionId);
      const id = await getFirstNotificationId(app, OWNER);

      const res = await request(app)
        .patch(`/api/v1/notifications/${id}/read`)
        .set('Authorization', auth(OWNER));

      expect(res.status).toBe(200);
      expect(res.body.data.isRead).toBe(true);
      expect(res.body.data.readAt).not.toBeNull();
    });

    it('returns success without changing anything when already read', async () => {
      const app = buildApp();
      const submissionId = await createSubmission(app);
      await assignCollector(app, submissionId);
      const id = await getFirstNotificationId(app, OWNER);

      const first = await request(app)
        .patch(`/api/v1/notifications/${id}/read`)
        .set('Authorization', auth(OWNER));
      const second = await request(app)
        .patch(`/api/v1/notifications/${id}/read`)
        .set('Authorization', auth(OWNER));

      expect(second.status).toBe(200);
      expect(second.body.data.readAt).toBe(first.body.data.readAt);
    });

    it("never allows marking another consumer's notification as read (404, not 403 — no ownership leak)", async () => {
      const app = buildApp();
      const submissionId = await createSubmission(app, OWNER);
      await assignCollector(app, submissionId);
      const id = await getFirstNotificationId(app, OWNER);

      const res = await request(app)
        .patch(`/api/v1/notifications/${id}/read`)
        .set('Authorization', auth(OTHER_OWNER));

      expect(res.status).toBe(404);
      expect(res.body.error.code).toBe('NOT_FOUND');
    });

    it('returns 404 for an unknown notification id', async () => {
      const app = buildApp();

      const res = await request(app)
        .patch('/api/v1/notifications/00000000-0000-4000-8000-000000000000/read')
        .set('Authorization', auth(OWNER));

      expect(res.status).toBe(404);
    });

    it('returns 400 for a non-uuid id', async () => {
      const app = buildApp();

      const res = await request(app)
        .patch('/api/v1/notifications/not-a-uuid/read')
        .set('Authorization', auth(OWNER));

      expect(res.status).toBe(400);
    });

    it('returns 403 for a non-consumer role', async () => {
      const app = buildApp();

      const res = await request(app)
        .patch('/api/v1/notifications/00000000-0000-4000-8000-000000000000/read')
        .set('Authorization', auth(RECYCLER));

      expect(res.status).toBe(403);
    });

    it('returns 401 without a token', async () => {
      const app = buildApp();

      const res = await request(app).patch(
        '/api/v1/notifications/00000000-0000-4000-8000-000000000000/read',
      );

      expect(res.status).toBe(401);
    });
  });
});
