import { Router } from 'express';
import type { RequestHandler } from 'express';
import { validate } from '@shared/middleware';
import { loginSchema, logoutSchema, refreshSchema, registerSchema } from './auth.schemas';
import type { AuthController } from './auth.controller';

/** Middleware injected into the auth router. */
export interface AuthRouterDeps {
  /** Verifies the Bearer access token — guards /auth/me. */
  readonly authenticate: RequestHandler;
  /** Brute-force protection applied to all auth endpoints. */
  readonly rateLimiter: RequestHandler;
}

/**
 * Mounts the auth module routes. Register/login/refresh/logout are public;
 * /auth/me requires a valid access token. Async handlers forward rejections
 * to the global error middleware. The rate limiter guards every auth endpoint.
 */
export function createAuthRouter(controller: AuthController, deps: AuthRouterDeps): Router {
  const router = Router();

  // Brute-force protection scoped to the authentication endpoints only.
  // The path prefix matters: this router is mounted at the API prefix, so an
  // unpathed router.use() would apply to all traffic under it. Scoping to
  // '/auth' keeps the limiter off non-auth endpoints.
  router.use('/auth', deps.rateLimiter);

  router.post('/auth/register', validate({ body: registerSchema }), (req, res, next) => {
    controller.register(req, res).catch(next);
  });

  router.post('/auth/login', validate({ body: loginSchema }), (req, res, next) => {
    controller.login(req, res).catch(next);
  });

  router.post('/auth/refresh', validate({ body: refreshSchema }), (req, res, next) => {
    controller.refresh(req, res).catch(next);
  });

  router.post('/auth/logout', validate({ body: logoutSchema }), (req, res, next) => {
    controller.logout(req, res).catch(next);
  });

  router.get('/auth/me', deps.authenticate, (req, res, next) => {
    controller.getMe(req, res).catch(next);
  });

  return router;
}
