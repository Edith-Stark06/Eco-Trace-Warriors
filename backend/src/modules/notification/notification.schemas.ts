import { z } from 'zod';

/**
 * Request schemas for the notification module. Applied by the validate
 * middleware before controllers run — see docs/engineering/05_API.md
 * (Validation Rules).
 */

export const notificationIdSchema = z.object({
  id: z.string().uuid('A valid notification id is required'),
});

export type NotificationIdParams = z.infer<typeof notificationIdSchema>;
