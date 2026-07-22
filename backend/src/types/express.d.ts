import type { UserRole } from '@prisma/client';

/**
 * Ambient augmentation of Express's Request with the authenticated principal.
 * Populated exclusively by the authenticate middleware; absent on public routes.
 */
declare global {
  namespace Express {
    interface Request {
      user?: {
        userId: string;
        role: UserRole;
      };
    }
  }
}

export {};
