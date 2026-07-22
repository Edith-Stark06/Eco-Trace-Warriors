import request from 'supertest';
import type { Express } from 'express';
import { UserRole } from '@prisma/client';
import { createApp } from '../../src/app';
import { loadConfig } from '@shared/config';
import { createLogger } from '@shared/logging';
import { createTokenService } from '@modules/auth';
import {
  activeCollector,
  createInMemorySubmissionRepository,
  createSeededSubmissionRepository,
} from '../helpers/in-memory-submission-repository';

const TEST_ENV = { NODE_ENV: 'test', LOG_LEVEL: 'fatal', BCRYPT_ROUNDS: '4' } as const;

const config = loadConfig(TEST_ENV);
const tokens = createTokenService({
  accessSecret: config.jwtSecret,
  refreshSecret: config.jwtRefreshSecret,
  accessExpiry: config.jwtAccessExpiry,
  refreshExpiry: config.jwtRefreshExpiry,
});

/** Mints an access token for an arbitrary principal — submissions do not require a user row. */
function tokenFor(userId: string, role: UserRole): string {
  return tokens.signAccessToken({ userId, email: `${userId}@example.com`, role });
}

function buildApp(): Express {
  const logger = createLogger(config);
  return createApp({
    config,
    logger,
    submissionRepository: createInMemorySubmissionRepository(),
  });
}

/**
 * App backed by a repository preloaded with a known collector, so the assign
 * endpoint's collector-existence check succeeds. Returns the collector id.
 */
function buildAppWithCollector(collectorId = COLLECTOR_ID): { app: Express; collectorId: string } {
  const logger = createLogger(config);
  const seeded = createSeededSubmissionRepository();
  seeded.addUser(activeCollector(collectorId));
  const app = createApp({ config, logger, submissionRepository: seeded.repository });
  return { app, collectorId };
}

const OWNER = tokenFor('user-1', UserRole.CONSUMER);
const OTHER = tokenFor('user-2', UserRole.CONSUMER);
const ADMIN = tokenFor('admin-1', UserRole.ADMIN);
const GOVERNMENT = tokenFor('gov-1', UserRole.GOVERNMENT);

// Collector ids must be UUIDs — the assign endpoint validates collectorId as a
// UUID, and the token's userId must equal the assigned id for ownership checks.
const COLLECTOR_ID = '11111111-1111-4111-8111-111111111111';
const OTHER_COLLECTOR_ID = '22222222-2222-4222-8222-222222222222';
const COLLECTOR = tokenFor(COLLECTOR_ID, UserRole.COLLECTOR);
const OTHER_COLLECTOR = tokenFor(OTHER_COLLECTOR_ID, UserRole.COLLECTOR);

const validBody = {
  category: 'Laptop',
  description: 'Old work laptop',
  estimatedWeight: 2.5,
  address: '12 MG Road, Bengaluru',
  latitude: 12.9716,
  longitude: 77.5946,
  imageUrls: ['https://cdn.example.com/a.jpg'],
};

const auth = (token: string): string => `Bearer ${token}`;

async function createSubmission(app: Express, token = OWNER): Promise<string> {
  const res = await request(app)
    .post('/api/v1/submissions')
    .set('Authorization', auth(token))
    .send(validBody);
  return res.body.data.id as string;
}

describe('POST /api/v1/submissions', () => {
  it('returns 201 with a PENDING submission owned by the consumer', async () => {
    const res = await request(buildApp())
      .post('/api/v1/submissions')
      .set('Authorization', auth(OWNER))
      .send(validBody);

    expect(res.status).toBe(201);
    expect(res.body).toEqual({
      success: true,
      data: expect.objectContaining({
        id: expect.any(String),
        userId: 'user-1',
        category: 'Laptop',
        status: 'PENDING',
        imageUrls: ['https://cdn.example.com/a.jpg'],
      }),
    });
  });

  it('returns 401 without a token', async () => {
    const res = await request(buildApp()).post('/api/v1/submissions').send(validBody);
    expect(res.status).toBe(401);
    expect(res.body.error.code).toBe('UNAUTHORIZED');
  });

  it('returns 403 when a non-consumer (collector) attempts to create', async () => {
    const res = await request(buildApp())
      .post('/api/v1/submissions')
      .set('Authorization', auth(COLLECTOR))
      .send(validBody);

    expect(res.status).toBe(403);
    expect(res.body.error.code).toBe('FORBIDDEN');
  });

  it('returns 400 with field details for an invalid body', async () => {
    const res = await request(buildApp())
      .post('/api/v1/submissions')
      .set('Authorization', auth(OWNER))
      .send({ category: '', estimatedWeight: -1, address: '', latitude: 200, longitude: 0 });

    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('VALIDATION_ERROR');
    const fields = (res.body.error.details as { field: string }[]).map((d) => d.field);
    expect(fields).toEqual(
      expect.arrayContaining(['category', 'estimatedWeight', 'address', 'latitude']),
    );
  });
});

describe('GET /api/v1/submissions', () => {
  it('returns only the caller’s own submissions', async () => {
    const app = buildApp();
    await createSubmission(app, OWNER);
    await createSubmission(app, OTHER);

    const res = await request(app).get('/api/v1/submissions').set('Authorization', auth(OWNER));

    expect(res.status).toBe(200);
    expect(res.body.data).toHaveLength(1);
    expect(res.body.data[0].userId).toBe('user-1');
  });

  it('returns every submission for an admin', async () => {
    const app = buildApp();
    await createSubmission(app, OWNER);
    await createSubmission(app, OTHER);

    const res = await request(app).get('/api/v1/submissions').set('Authorization', auth(ADMIN));

    expect(res.status).toBe(200);
    expect(res.body.data).toHaveLength(2);
  });

  it('returns 401 without a token', async () => {
    const res = await request(buildApp()).get('/api/v1/submissions');
    expect(res.status).toBe(401);
  });
});

describe('GET /api/v1/submissions/:id', () => {
  it('returns the submission for its owner', async () => {
    const app = buildApp();
    const id = await createSubmission(app);

    const res = await request(app)
      .get(`/api/v1/submissions/${id}`)
      .set('Authorization', auth(OWNER));

    expect(res.status).toBe(200);
    expect(res.body.data.id).toBe(id);
  });

  it('returns the submission for an admin', async () => {
    const app = buildApp();
    const id = await createSubmission(app);

    const res = await request(app)
      .get(`/api/v1/submissions/${id}`)
      .set('Authorization', auth(ADMIN));

    expect(res.status).toBe(200);
  });

  it('returns 404 when another consumer requests it (no existence leak)', async () => {
    const app = buildApp();
    const id = await createSubmission(app);

    const res = await request(app)
      .get(`/api/v1/submissions/${id}`)
      .set('Authorization', auth(OTHER));

    expect(res.status).toBe(404);
    expect(res.body.error.code).toBe('NOT_FOUND');
  });

  it('returns 404 for an unknown id', async () => {
    const res = await request(buildApp())
      .get('/api/v1/submissions/11111111-1111-1111-1111-111111111111')
      .set('Authorization', auth(OWNER));

    expect(res.status).toBe(404);
  });

  it('returns 400 for a non-uuid id', async () => {
    const res = await request(buildApp())
      .get('/api/v1/submissions/not-a-uuid')
      .set('Authorization', auth(OWNER));

    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('VALIDATION_ERROR');
  });
});

describe('PATCH /api/v1/submissions/:id', () => {
  it('lets the owner edit a PENDING submission', async () => {
    const app = buildApp();
    const id = await createSubmission(app);

    const res = await request(app)
      .patch(`/api/v1/submissions/${id}`)
      .set('Authorization', auth(OWNER))
      .send({ category: 'Smartphone' });

    expect(res.status).toBe(200);
    expect(res.body.data.category).toBe('Smartphone');
  });

  it('returns 404 when a non-owner edits', async () => {
    const app = buildApp();
    const id = await createSubmission(app);

    const res = await request(app)
      .patch(`/api/v1/submissions/${id}`)
      .set('Authorization', auth(OTHER))
      .send({ category: 'Smartphone' });

    expect(res.status).toBe(404);
  });

  it('returns 400 for an empty update body', async () => {
    const app = buildApp();
    const id = await createSubmission(app);

    const res = await request(app)
      .patch(`/api/v1/submissions/${id}`)
      .set('Authorization', auth(OWNER))
      .send({});

    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('VALIDATION_ERROR');
  });
});

describe('DELETE /api/v1/submissions/:id', () => {
  it('lets the owner delete a PENDING submission (204)', async () => {
    const app = buildApp();
    const id = await createSubmission(app);

    const res = await request(app)
      .delete(`/api/v1/submissions/${id}`)
      .set('Authorization', auth(OWNER));

    expect(res.status).toBe(204);
    expect(res.body).toEqual({});

    const after = await request(app)
      .get(`/api/v1/submissions/${id}`)
      .set('Authorization', auth(OWNER));
    expect(after.status).toBe(404);
  });

  it('lets an admin delete any submission (204)', async () => {
    const app = buildApp();
    const id = await createSubmission(app);

    const res = await request(app)
      .delete(`/api/v1/submissions/${id}`)
      .set('Authorization', auth(ADMIN));

    expect(res.status).toBe(204);
  });

  it('returns 404 when a non-owner deletes', async () => {
    const app = buildApp();
    const id = await createSubmission(app);

    const res = await request(app)
      .delete(`/api/v1/submissions/${id}`)
      .set('Authorization', auth(OTHER));

    expect(res.status).toBe(404);
  });
});

describe('Collector workflow', () => {
  /** Assigns the collector and returns the submission id, asserting success. */
  async function createAndAssign(app: Express): Promise<string> {
    const id = await createSubmission(app, OWNER);
    const res = await request(app)
      .patch(`/api/v1/submissions/${id}/assign`)
      .set('Authorization', auth(ADMIN))
      .send({ collectorId: COLLECTOR_ID });
    expect(res.status).toBe(200);
    return id;
  }

  describe('PATCH /api/v1/submissions/:id/assign', () => {
    it('lets an admin assign a collector (PENDING → ASSIGNED)', async () => {
      const { app } = buildAppWithCollector();
      const id = await createSubmission(app, OWNER);

      const res = await request(app)
        .patch(`/api/v1/submissions/${id}/assign`)
        .set('Authorization', auth(ADMIN))
        .send({ collectorId: COLLECTOR_ID });

      expect(res.status).toBe(200);
      expect(res.body.data.status).toBe('ASSIGNED');
      expect(res.body.data.assignedCollectorId).toBe(COLLECTOR_ID);
    });

    it('lets a government actor assign a collector', async () => {
      const { app } = buildAppWithCollector();
      const id = await createSubmission(app, OWNER);

      const res = await request(app)
        .patch(`/api/v1/submissions/${id}/assign`)
        .set('Authorization', auth(GOVERNMENT))
        .send({ collectorId: COLLECTOR_ID });

      expect(res.status).toBe(200);
    });

    it('returns 403 when a collector tries to assign (no self-assign)', async () => {
      const { app } = buildAppWithCollector();
      const id = await createSubmission(app, OWNER);

      const res = await request(app)
        .patch(`/api/v1/submissions/${id}/assign`)
        .set('Authorization', auth(COLLECTOR))
        .send({ collectorId: COLLECTOR_ID });

      expect(res.status).toBe(403);
      expect(res.body.error.code).toBe('FORBIDDEN');
    });

    it('returns 403 when a consumer tries to assign', async () => {
      const { app } = buildAppWithCollector();
      const id = await createSubmission(app, OWNER);

      const res = await request(app)
        .patch(`/api/v1/submissions/${id}/assign`)
        .set('Authorization', auth(OWNER))
        .send({ collectorId: COLLECTOR_ID });

      expect(res.status).toBe(403);
    });

    it('returns 404 when the collector id is unknown', async () => {
      const { app } = buildAppWithCollector();
      const id = await createSubmission(app, OWNER);

      const res = await request(app)
        .patch(`/api/v1/submissions/${id}/assign`)
        .set('Authorization', auth(ADMIN))
        .send({ collectorId: '99999999-9999-9999-9999-999999999999' });

      expect(res.status).toBe(404);
      expect(res.body.error.code).toBe('NOT_FOUND');
    });

    it('returns 400 for a non-uuid collectorId', async () => {
      const { app } = buildAppWithCollector();
      const id = await createSubmission(app, OWNER);

      const res = await request(app)
        .patch(`/api/v1/submissions/${id}/assign`)
        .set('Authorization', auth(ADMIN))
        .send({ collectorId: 'not-a-uuid' });

      expect(res.status).toBe(400);
      expect(res.body.error.code).toBe('VALIDATION_ERROR');
    });

    it('returns 401 without a token', async () => {
      const { app } = buildAppWithCollector();
      const id = await createSubmission(app, OWNER);

      const res = await request(app)
        .patch(`/api/v1/submissions/${id}/assign`)
        .send({ collectorId: COLLECTOR_ID });

      expect(res.status).toBe(401);
    });
  });

  describe('full lifecycle: accept → start → complete', () => {
    it('drives a submission through the whole collector workflow', async () => {
      const { app } = buildAppWithCollector();
      const id = await createAndAssign(app);

      const accepted = await request(app)
        .patch(`/api/v1/submissions/${id}/accept`)
        .set('Authorization', auth(COLLECTOR));
      expect(accepted.status).toBe(200);
      expect(accepted.body.data.status).toBe('ACCEPTED');

      const started = await request(app)
        .patch(`/api/v1/submissions/${id}/start`)
        .set('Authorization', auth(COLLECTOR));
      expect(started.status).toBe(200);
      expect(started.body.data.status).toBe('IN_PROGRESS');
      expect(started.body.data.pickupScheduledAt).not.toBeNull();

      const completed = await request(app)
        .patch(`/api/v1/submissions/${id}/complete`)
        .set('Authorization', auth(COLLECTOR));
      expect(completed.status).toBe(200);
      expect(completed.body.data.status).toBe('COLLECTED');
    });
  });

  describe('workflow guards', () => {
    it('returns 404 when a different collector accepts (not the assignee)', async () => {
      const { app } = buildAppWithCollector();
      const id = await createAndAssign(app);

      const res = await request(app)
        .patch(`/api/v1/submissions/${id}/accept`)
        .set('Authorization', auth(OTHER_COLLECTOR));

      expect(res.status).toBe(404);
      expect(res.body.error.code).toBe('NOT_FOUND');
    });

    it('returns 409 when starting before accepting (wrong status)', async () => {
      const { app } = buildAppWithCollector();
      const id = await createAndAssign(app);

      const res = await request(app)
        .patch(`/api/v1/submissions/${id}/start`)
        .set('Authorization', auth(COLLECTOR));

      expect(res.status).toBe(409);
      expect(res.body.error.code).toBe('CONFLICT');
    });

    it('returns 409 when completing before starting', async () => {
      const { app } = buildAppWithCollector();
      const id = await createAndAssign(app);

      await request(app)
        .patch(`/api/v1/submissions/${id}/accept`)
        .set('Authorization', auth(COLLECTOR));

      const res = await request(app)
        .patch(`/api/v1/submissions/${id}/complete`)
        .set('Authorization', auth(COLLECTOR));

      expect(res.status).toBe(409);
    });

    it('returns 403 when a consumer hits a collector-only transition', async () => {
      const { app } = buildAppWithCollector();
      const id = await createAndAssign(app);

      const res = await request(app)
        .patch(`/api/v1/submissions/${id}/accept`)
        .set('Authorization', auth(OWNER));

      expect(res.status).toBe(403);
    });
  });

  describe('GET /api/v1/collector/submissions', () => {
    it('returns only the active assignments for the authenticated collector, newest first', async () => {
      const { app } = buildAppWithCollector();
      const first = await createAndAssign(app);
      const second = await createAndAssign(app);

      const res = await request(app)
        .get('/api/v1/collector/submissions')
        .set('Authorization', auth(COLLECTOR));

      expect(res.status).toBe(200);
      expect(res.body.data).toHaveLength(2);
      // Newest first: the second-created submission leads.
      expect(res.body.data[0].id).toBe(second);
      expect(res.body.data[1].id).toBe(first);
    });

    it('excludes COLLECTED submissions from the dashboard', async () => {
      const { app } = buildAppWithCollector();
      const id = await createAndAssign(app);
      await request(app)
        .patch(`/api/v1/submissions/${id}/accept`)
        .set('Authorization', auth(COLLECTOR));
      await request(app)
        .patch(`/api/v1/submissions/${id}/start`)
        .set('Authorization', auth(COLLECTOR));
      await request(app)
        .patch(`/api/v1/submissions/${id}/complete`)
        .set('Authorization', auth(COLLECTOR));

      const res = await request(app)
        .get('/api/v1/collector/submissions')
        .set('Authorization', auth(COLLECTOR));

      expect(res.status).toBe(200);
      expect(res.body.data).toHaveLength(0);
    });

    it('returns an empty list for a collector with no assignments', async () => {
      const { app } = buildAppWithCollector();

      const res = await request(app)
        .get('/api/v1/collector/submissions')
        .set('Authorization', auth(OTHER_COLLECTOR));

      expect(res.status).toBe(200);
      expect(res.body.data).toEqual([]);
    });

    it('returns 403 for a non-collector', async () => {
      const { app } = buildAppWithCollector();

      const res = await request(app)
        .get('/api/v1/collector/submissions')
        .set('Authorization', auth(OWNER));

      expect(res.status).toBe(403);
    });

    it('returns 401 without a token', async () => {
      const { app } = buildAppWithCollector();

      const res = await request(app).get('/api/v1/collector/submissions');

      expect(res.status).toBe(401);
    });
  });
});
