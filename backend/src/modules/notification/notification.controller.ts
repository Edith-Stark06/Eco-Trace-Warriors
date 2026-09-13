import type { Request, Response } from 'express';
import { getAuthContext } from '@modules/auth';
import type { Pagination } from '@shared/pagination';
import type { NotificationService } from './notification.service';
import type { NotificationListResponse, NotificationResponse } from './notification.types';

export interface NotificationController {
  list(req: Request, res: Response): Promise<void>;
  markRead(req: Request, res: Response): Promise<void>;
}

/** Reads the validated, coerced pagination window from the request query. */
function paginationOf(req: Request): Pagination {
  return req.query as unknown as Pagination;
}

/**
 * Thin controller: delegates to the service and shapes the HTTP response.
 * `userId` always comes from `getAuthContext(req)` (the verified access
 * token) — no route here accepts a client-supplied recipient/owner id.
 */
export function createNotificationController(service: NotificationService): NotificationController {
  return {
    async list(req: Request, res: Response): Promise<void> {
      const { userId } = getAuthContext(req);
      const result = await service.listForUser(userId, paginationOf(req));
      const body: NotificationListResponse = { success: true, data: result };
      res.status(200).json(body);
    },

    async markRead(req: Request, res: Response): Promise<void> {
      const { userId } = getAuthContext(req);
      const { id } = req.params as { id: string };
      const result = await service.markRead(userId, id);
      const body: NotificationResponse = { success: true, data: result };
      res.status(200).json(body);
    },
  };
}
