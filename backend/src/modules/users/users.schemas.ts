import { z } from 'zod';
import { UserRole } from '@prisma/client';

/**
 * Query schema for GET /users. Only COLLECTOR and RECYCLER are valid lookup
 * targets — callers have no reason to enumerate other roles via this endpoint.
 */
export const listUsersQuerySchema = z.object({
  role: z.enum([UserRole.COLLECTOR, UserRole.RECYCLER], {
    errorMap: () => ({ message: 'role must be COLLECTOR or RECYCLER' }),
  }),
});

export type ListUsersQuery = z.infer<typeof listUsersQuerySchema>;

/**
 * Body schema for POST /users (admin-provisioned operational accounts).
 * ADMIN and CONSUMER are intentionally excluded from the allowed set — ADMIN
 * accounts are not self-service, and CONSUMER accounts are created only via
 * public registration (POST /auth/register).
 */
export const createUserSchema = z.object({
  email: z.string().trim().toLowerCase().email('A valid email address is required'),
  role: z.enum([UserRole.COLLECTOR, UserRole.RECYCLER, UserRole.GOVERNMENT], {
    errorMap: () => ({ message: 'role must be COLLECTOR, RECYCLER, or GOVERNMENT' }),
  }),
});

export type CreateUserRequest = z.infer<typeof createUserSchema>;
