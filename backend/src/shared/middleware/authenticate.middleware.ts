import type { RequestHandler } from 'express';
import { UnauthorizedError } from '@shared/errors';
import type { TokenService } from '@modules/auth/token.service';

const BEARER_PREFIX = 'Bearer ';

/**
 * Verifies the Bearer access token and attaches the authenticated principal
 * to the request as `req.user`. Throws UnauthorizedError (→ 401) otherwise.
 */
export function authenticate(tokens: TokenService): RequestHandler {
  return (req, _res, next): void => {
    const header = req.headers.authorization;

    if (!header || !header.startsWith(BEARER_PREFIX)) {
      throw new UnauthorizedError('Authentication is required.');
    }

    const claims = tokens.verifyAccessToken(header.slice(BEARER_PREFIX.length));
    req.user = { userId: claims.sub, role: claims.role };
    next();
  };
}
