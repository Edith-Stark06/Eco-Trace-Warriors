import type { NotificationType } from '@prisma/client';
import { NotFoundError } from '@shared/errors';
import type { Logger } from '@shared/logging';
import type { Pagination } from '@shared/pagination';
import type { NotificationRecord, NotificationRepository } from './notification.repository';
import type { PublicNotification } from './notification.types';

/** Dependencies injected into the notification service. */
export interface NotificationServiceDeps {
  readonly notifications: NotificationRepository;
  readonly logger: Logger;
}

export interface NotificationService {
  /**
   * Records a real lifecycle-event notification for a submission's owner.
   * Idempotent: at most one notification ever exists per (userId,
   * submissionId, type) — a repeated call for the same event is a silent
   * no-op, never a duplicate row or an error. Callers (submission.service.ts)
   * treat this as best-effort: a failure here must never fail or roll back
   * the business transition that triggered it.
   */
  createNotification(
    userId: string,
    submissionId: string,
    type: NotificationType,
    message: string,
  ): Promise<PublicNotification>;

  /** The authenticated user's own notifications, newest first. */
  listForUser(userId: string, pagination?: Pagination): Promise<PublicNotification[]>;

  /**
   * Marks one notification read. Scoped strictly to `userId` — a notification
   * that doesn't exist, or exists but belongs to someone else, both surface
   * as NotFoundError (never Forbidden), so a caller can never learn whether a
   * given id belongs to another user. Already-read is a no-op success, not
   * an error.
   */
  markRead(userId: string, id: string): Promise<PublicNotification>;
}

function toPublicNotification(record: NotificationRecord): PublicNotification {
  return {
    id: record.id,
    submissionId: record.submissionId,
    type: record.type,
    message: record.message,
    createdAt: record.createdAt.toISOString(),
    readAt: record.readAt?.toISOString() ?? null,
    isRead: record.readAt !== null,
  };
}

/** Creates the notification service. Framework-agnostic and fully unit-testable. */
export function createNotificationService(deps: NotificationServiceDeps): NotificationService {
  return {
    async createNotification(
      userId: string,
      submissionId: string,
      type: NotificationType,
      message: string,
    ): Promise<PublicNotification> {
      const record = await deps.notifications.create({ userId, submissionId, type, message });
      deps.logger.info({ userId, submissionId, type }, 'Notification recorded');
      return toPublicNotification(record);
    },

    async listForUser(userId: string, pagination?: Pagination): Promise<PublicNotification[]> {
      const records = await deps.notifications.findByUser(userId, pagination);
      return records.map(toPublicNotification);
    },

    async markRead(userId: string, id: string): Promise<PublicNotification> {
      const record = await deps.notifications.findById(id);
      // A missing notification and someone else's notification both surface
      // as NotFound — never Forbidden — so a caller cannot distinguish "this
      // id doesn't exist" from "this id belongs to another user."
      if (!record || record.userId !== userId) {
        throw new NotFoundError('Notification not found.');
      }

      if (record.readAt !== null) {
        // Already read — return success without changing anything.
        return toPublicNotification(record);
      }

      const updated = await deps.notifications.markRead(id);
      return toPublicNotification(updated);
    },
  };
}
