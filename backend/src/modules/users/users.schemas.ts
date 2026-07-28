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
