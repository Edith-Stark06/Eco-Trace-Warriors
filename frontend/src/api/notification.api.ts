/**
 * Notification API module.
 *
 * Typed, Consumer-only wrappers around the in-app notification endpoints
 * (backend/src/modules/notification/, docs/engineering/05_API.md). Built on
 * the single shared Axios instance; each method unwraps the success
 * envelope and returns the resource directly.
 *
 * This is a persistent, authenticated, in-app notification center — no push
 * token, no email, no SMS. `userId` is never sent from the client; the
 * backend derives the recipient exclusively from the access token.
 */
import { apiClient } from '@/api/axios';
import { unwrap } from '@/api/client';
import type { ApiSuccess, AppNotification, PaginationParams } from '@/types';

export const notificationApi = {
  /** GET /notifications — the authenticated consumer's own notifications, newest first. */
  getNotifications: (params?: PaginationParams): Promise<AppNotification[]> =>
    unwrap<AppNotification[]>(
      apiClient.get<ApiSuccess<AppNotification[]>>('/notifications', { params }),
    ),

  /** PATCH /notifications/:id/read — marks one of the caller's own notifications read. */
  markRead: (id: string): Promise<AppNotification> =>
    unwrap<AppNotification>(apiClient.patch<ApiSuccess<AppNotification>>(`/notifications/${id}/read`)),
};
