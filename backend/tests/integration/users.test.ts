import request from 'supertest';
import type { Express } from 'express';
import { UserRole } from '@prisma/client';
import { createApp } from '../../src/app';
import { loadConfig } from '@shared/config';
import { createLogger } from '@shared/logging';
import { createTokenService } from '@modules/auth';
import { createInMemoryAuthRepositories } from '../helpers/in-memory-auth-repositories';

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

function auth(token: string): string {
  return `Bearer ${token}`;
}

function buildApp(): Express {
  const logger = createLogger(config);
  return createApp({
    config,
    logger,
    authRepositories: createInMemoryAuthRepositories(),
  });
}

const ADMIN = tokenFor('admin-1', UserRole.ADMIN);
const GOVERNMENT = tokenFor('gov-1', UserRole.GOVERNMENT);
const COLLECTOR = tokenFor('collector-1', UserRole.COLLECTOR);
const CONSUMER = tokenFor('consumer-1', UserRole.CONSUMER);

describe('POST /api/v1/users (P10.5 Admin create-user)', () => {
  it('returns 401 when no authentication is provided', async () => {
    const res = await request(buildApp())
      .post('/api/v1/users')
      .send({ email: 'new.collector@example.com', role: 'COLLECTOR' });

    expect(res.status).toBe(401);
  });

  it('returns 403 for GOVERNMENT (this endpoint is ADMIN only, unlike GET /users)', async () => {
    const res = await request(buildApp())
      .post('/api/v1/users')
      .set('Authorization', auth(GOVERNMENT))
      .send({ email: 'new.collector@example.com', role: 'COLLECTOR' });

    expect(res.status).toBe(403);
  });

  it.each([
    ['COLLECTOR', COLLECTOR],
    ['CONSUMER', CONSUMER],
  ])('returns 403 for a non-admin caller (%s)', async (_label, token) => {
    const res = await request(buildApp())
      .post('/api/v1/users')
      .set('Authorization', auth(token))
      .send({ email: 'new.collector@example.com', role: 'COLLECTOR' });

    expect(res.status).toBe(403);
  });

  it.each([UserRole.COLLECTOR, UserRole.RECYCLER, UserRole.GOVERNMENT])(
    'creates a %s user and returns 201 with the generated password',
    async (role) => {
      const app = buildApp();
      const res = await request(app)
        .post('/api/v1/users')
        .set('Authorization', auth(ADMIN))
        .send({ email: `new.${role.toLowerCase()}@example.com`, role });

      expect(res.status).toBe(201);
      expect(res.body).toEqual({
        success: true,
        data: {
          user: {
            id: expect.any(String),
            email: `new.${role.toLowerCase()}@example.com`,
            role,
            createdAt: expect.any(String),
          },
          generatedPassword: expect.any(String),
        },
      });
      expect(res.body.data.generatedPassword.length).toBeGreaterThanOrEqual(12);
    },
  );

  it('never returns passwordHash or any hash-shaped field in the response', async () => {
    const res = await request(buildApp())
      .post('/api/v1/users')
      .set('Authorization', auth(ADMIN))
      .send({ email: 'no.hash@example.com', role: 'COLLECTOR' });

    expect(res.status).toBe(201);
    expect(JSON.stringify(res.body)).not.toContain('passwordHash');
  });

  it('returns 409 for a duplicate email and does not create a second account', async () => {
    const app = buildApp();
    const body = { email: 'duplicate@example.com', role: 'COLLECTOR' };

    const first = await request(app)
      .post('/api/v1/users')
      .set('Authorization', auth(ADMIN))
      .send(body);
    expect(first.status).toBe(201);

    const second = await request(app)
      .post('/api/v1/users')
      .set('Authorization', auth(ADMIN))
      .send(body);

    expect(second.status).toBe(409);
    expect(second.body.error.code).toBe('CONFLICT');
  });

  it.each(['ADMIN', 'CONSUMER', 'NOT_A_REAL_ROLE'])(
    'rejects role=%s with a 400 validation error',
    async (role) => {
      const res = await request(buildApp())
        .post('/api/v1/users')
        .set('Authorization', auth(ADMIN))
        .send({ email: 'rejected.role@example.com', role });

      expect(res.status).toBe(400);
      expect(res.body.error.code).toBe('VALIDATION_ERROR');
    },
  );

  it('rejects an empty/invalid email with a 400 validation error', async () => {
    const res = await request(buildApp())
      .post('/api/v1/users')
      .set('Authorization', auth(ADMIN))
      .send({ email: 'not-an-email', role: 'COLLECTOR' });

    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('VALIDATION_ERROR');
  });
});
