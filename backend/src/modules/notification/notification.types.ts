import type { NotificationType } from '@prisma/client';
import type { SuccessResponse } from '../../types';

/**
 * The notification shape returned to clients. Dates are serialized to ISO
 * strings at the service boundary — the raw Date/record never leaves the
 * module. `isRead` is derived from `readAt` here so the frontend never has
 * to re-derive it from a nullable timestamp itself.
 */
export interface PublicNotification {
  readonly id: string;
  readonly submissionId: string;
  readonly type: NotificationType;
  readonly message: string;
  readonly createdAt: string;
  readonly readAt: string | null;
  readonly isRead: boolean;
}

export type NotificationResponse = SuccessResponse<PublicNotification>;
export type NotificationListResponse = SuccessResponse<readonly PublicNotification[]>;
