import express from 'express';
import type { Express } from 'express';
import request from 'supertest';
import { UserRole } from '@prisma/client';
import { createApp } from '../../src/app';
import { loadConfig } from '@shared/config';
import { createLogger } from '@shared/logging';
import { createTokenService } from '@modules/auth';
import { authenticate, authorize, errorHandler } from '@shared/middleware';
import { createInMemoryAuthRepositories } from '../helpers/in-memory-auth-repositories';

const TEST_ENV = {
  NODE_ENV: 'test',
  LOG_LEVEL: 'fatal',
  // Low cost keeps bcrypt fast in tests.
  BCRYPT_ROUNDS: '4',
} as const;

function buildTestApp(): ReturnType<typeof createApp> {
  const config = loadConfig(TEST_ENV);
  const logger = createLogger(config);
  return createApp({ config, logger, authRepositories: createInMemoryAuthRepositories() });
}

const registerBody = {
  email: 'asha@example.com',
  password: 'password123',
  confirmPassword: 'password123',
  fullName: 'Asha Kumar',
};

describe('POST /api/v1/auth/register', () => {
  it('returns 201 with the user profile and a token pair', async () => {
    const res = await request(buildTestApp()).post('/api/v1/auth/register').send(registerBody);

    expect(res.status).toBe(201);
    expect(res.body).toEqual({
      success: true,
      data: {
        user: {
          id: expect.any(String),
          fullName: 'Asha Kumar',
          email: 'asha@example.com',
          phone: null,
          region: null,
          role: 'CONSUMER',
          emailVerified: false,
          createdAt: expect.any(String),
        },
        accessToken: expect.any(String),
        refreshToken: expect.any(String),
      },
    });
    expect(JSON.stringify(res.body)).not.toContain('passwordHash');
  });

  it('returns 409 for a duplicate email', async () => {
    const app = buildTestApp();
    await request(app).post('/api/v1/auth/register').send(registerBody);

    const res = await request(app).post('/api/v1/auth/register').send(registerBody);

    expect(res.status).toBe(409);
    expect(res.body.error.code).toBe('CONFLICT');
  });

  it('returns 400 with field details for an invalid body', async () => {
    const res = await request(buildTestApp())
      .post('/api/v1/auth/register')
      .send({ email: 'not-an-email', password: 'short', confirmPassword: 'other', fullName: 'A' });

    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('VALIDATION_ERROR');
    const fields = (res.body.error.details as { field: string }[]).map((d) => d.field);
    expect(fields).toEqual(
      expect.arrayContaining(['email', 'password', 'confirmPassword', 'fullName']),
    );
  });
});

describe('POST /api/v1/auth/login', () => {
  it('returns 200 with tokens for valid credentials', async () => {
    const app = buildTestApp();
    await request(app).post('/api/v1/auth/register').send(registerBody);

    const res = await request(app)
      .post('/api/v1/auth/login')
      .send({ email: 'asha@example.com', password: 'password123' });

    expect(res.status).toBe(200);
    expect(res.body.data.accessToken).toEqual(expect.any(String));
    expect(res.body.data.refreshToken).toEqual(expect.any(String));
    expect(res.body.data.user.email).toBe('asha@example.com');
  });

  it('returns 401 with a generic message for a wrong password', async () => {
    const app = buildTestApp();
    await request(app).post('/api/v1/auth/register').send(registerBody);

    const res = await request(app)
      .post('/api/v1/auth/login')
      .send({ email: 'asha@example.com', password: 'wrong-password' });

    expect(res.status).toBe(401);
    expect(res.body.error).toEqual({
      code: 'UNAUTHORIZED',
      message: 'Invalid email or password.',
    });
  });

  it('returns 401 for an unknown email with the same message', async () => {
    const res = await request(buildTestApp())
      .post('/api/v1/auth/login')
      .send({ email: 'ghost@example.com', password: 'password123' });

    expect(res.status).toBe(401);
    expect(res.body.error.message).toBe('Invalid email or password.');
  });
});

describe('GET /api/v1/auth/me', () => {
  it('returns 200 with the profile for a valid access token', async () => {
    const app = buildTestApp();
    const registered = await request(app).post('/api/v1/auth/register').send(registerBody);

    const res = await request(app)
      .get('/api/v1/auth/me')
      .set('Authorization', `Bearer ${registered.body.data.accessToken}`);

    expect(res.status).toBe(200);
    expect(res.body.data.email).toBe('asha@example.com');
    expect(res.body.data).not.toHaveProperty('passwordHash');
  });

  it('returns 401 without a token', async () => {
    const res = await request(buildTestApp()).get('/api/v1/auth/me');

    expect(res.status).toBe(401);
    expect(res.body.error.code).toBe('UNAUTHORIZED');
  });

  it('returns 401 for a malformed token', async () => {
    const res = await request(buildTestApp())
      .get('/api/v1/auth/me')
      .set('Authorization', 'Bearer not-a-jwt');

    expect(res.status).toBe(401);
  });
});

describe('POST /api/v1/auth/refresh', () => {
  it('returns 200 with a rotated token pair', async () => {
    const app = buildTestApp();
    const registered = await request(app).post('/api/v1/auth/register').send(registerBody);
    const oldRefresh = registered.body.data.refreshToken as string;

    const res = await request(app).post('/api/v1/auth/refresh').send({ refreshToken: oldRefresh });

    expect(res.status).toBe(200);
    expect(res.body.data.accessToken).toEqual(expect.any(String));
    expect(res.body.data.refreshToken).toEqual(expect.any(String));
    expect(res.body.data.refreshToken).not.toBe(oldRefresh);
  });

  it('returns 401 when the previous (rotated) token is reused', async () => {
    const app = buildTestApp();
    const registered = await request(app).post('/api/v1/auth/register').send(registerBody);
    const oldRefresh = registered.body.data.refreshToken as string;
    await request(app).post('/api/v1/auth/refresh').send({ refreshToken: oldRefresh });

    const res = await request(app).post('/api/v1/auth/refresh').send({ refreshToken: oldRefresh });

    expect(res.status).toBe(401);
  });

  it('returns 401 for a garbage refresh token', async () => {
    const res = await request(buildTestApp())
      .post('/api/v1/auth/refresh')
      .send({ refreshToken: 'garbage' });

    expect(res.status).toBe(401);
  });
});

describe('POST /api/v1/auth/logout', () => {
  it('returns 200 and invalidates the refresh token', async () => {
    const app = buildTestApp();
    const registered = await request(app).post('/api/v1/auth/register').send(registerBody);
    const refreshToken = registered.body.data.refreshToken as string;

    const logout = await request(app).post('/api/v1/auth/logout').send({ refreshToken });
    expect(logout.status).toBe(200);
    expect(logout.body).toEqual({ success: true, data: { loggedOut: true } });

    const res = await request(app).post('/api/v1/auth/refresh').send({ refreshToken });
    expect(res.status).toBe(401);
  });

  it('returns 200 for an unknown token (idempotent)', async () => {
    const res = await request(buildTestApp())
      .post('/api/v1/auth/logout')
      .send({ refreshToken: 'already-dead' });

    expect(res.status).toBe(200);
  });
});

describe('RBAC — authorize middleware over HTTP', () => {
  /**
   * The auth phase ships no role-restricted endpoints yet, so RBAC is
   * exercised over HTTP against a minimal app with an ADMIN-only probe route
   * wired exactly as production routes will be: authenticate → authorize.
   */
  function buildRbacFixture(): {
    app: Express;
    tokenFor: (role: UserRole) => string;
  } {
    const config = loadConfig(TEST_ENV);
    const tokens = createTokenService({
      accessSecret: config.jwtSecret,
      refreshSecret: config.jwtRefreshSecret,
      accessExpiry: config.jwtAccessExpiry,
      refreshExpiry: config.jwtRefreshExpiry,
    });

    const app = express();
    app.get('/admin-only', authenticate(tokens), authorize(UserRole.ADMIN), (_req, res) => {
      res.status(200).json({ success: true, data: { ok: true } });
    });
    app.use(errorHandler(createLogger(config)));

    const tokenFor = (role: UserRole): string =>
      tokens.signAccessToken({ userId: `${role}-1`, email: `${role}@example.com`, role });

    return { app, tokenFor };
  }

  it('returns 403 when a CONSUMER token hits an ADMIN-only route', async () => {
    const { app, tokenFor } = buildRbacFixture();

    const res = await request(app)
      .get('/admin-only')
      .set('Authorization', `Bearer ${tokenFor(UserRole.CONSUMER)}`);

    expect(res.status).toBe(403);
    expect(res.body.error.code).toBe('FORBIDDEN');
  });

  it('returns 401 when the route is hit without a token', async () => {
    const { app } = buildRbacFixture();

    const res = await request(app).get('/admin-only');

    expect(res.status).toBe(401);
    expect(res.body.error.code).toBe('UNAUTHORIZED');
  });

  it('returns 200 when an ADMIN token hits the same route', async () => {
    const { app, tokenFor } = buildRbacFixture();

    const res = await request(app)
      .get('/admin-only')
      .set('Authorization', `Bearer ${tokenFor(UserRole.ADMIN)}`);

    expect(res.status).toBe(200);
    expect(res.body.data.ok).toBe(true);
  });
});
