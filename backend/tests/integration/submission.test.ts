import request from 'supertest';
import type { Express } from 'express';
import { UserRole } from '@prisma/client';
import { createApp } from '../../src/app';
import { loadConfig } from '@shared/config';
import { createLogger } from '@shared/logging';
import { createTokenService } from '@modules/auth';
import { createInMemorySubmissionRepository } from '../helpers/in-memory-submission-repository';

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

const OWNER = tokenFor('user-1', UserRole.CONSUMER);
const OTHER = tokenFor('user-2', UserRole.CONSUMER);
const ADMIN = tokenFor('admin-1', UserRole.ADMIN);
const COLLECTOR = tokenFor('collector-1', UserRole.COLLECTOR);

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
