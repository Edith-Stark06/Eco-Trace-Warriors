import type { NotificationType, PrismaClient } from '@prisma/client';
import type { Pagination } from '@shared/pagination';

/**
 * Repositories are the only place Prisma is used for the notification
 * module. Services depend on this interface, never on Prisma directly —
 * see docs/engineering/06_BACKEND.md (Layering).
 */

/** Input for creating (or idempotently re-using) a notification row. */
export interface CreateNotificationInput {
  readonly userId: string;
  readonly submissionId: string;
  readonly type: NotificationType;
  readonly message: string;
}

/** Notification row as read by the module. */
export interface NotificationRecord {
  readonly id: string;
  readonly userId: string;
  readonly submissionId: string;
  readonly type: NotificationType;
  readonly message: string;
  readonly createdAt: Date;
  readonly readAt: Date | null;
}

export interface NotificationRepository {
  /**
   * Idempotently records a notification: at most one row ever exists per
   * (userId, submissionId, type) — see the `@@unique` constraint on the
   * Prisma model. A second call with the same three values is a no-op that
   * returns the existing row rather than creating a duplicate or erroring.
   */
  create(input: CreateNotificationInput): Promise<NotificationRecord>;
  /** The user's own notifications, newest first. Paginated when a window is given. */
  findByUser(userId: string, pagination?: Pagination): Promise<NotificationRecord[]>;
  /** A single notification by id, or null if it doesn't exist. No ownership check here — the service enforces that. */
  findById(id: string): Promise<NotificationRecord | null>;
  /** Stamps `readAt` if not already set. Returns the (possibly unchanged) row. */
  markRead(id: string): Promise<NotificationRecord>;
}

const notificationSelect = {
  id: true,
  userId: true,
  submissionId: true,
  type: true,
  message: true,
  createdAt: true,
  readAt: true,
} as const;

/**
 * Translates validated pagination into Prisma `take`/`skip`. Returns an empty
 * object when no window is supplied, so unpaginated callers are unaffected.
 */
function toPage(pagination?: Pagination): { take?: number; skip?: number } {
  if (!pagination) return {};
  return { take: pagination.limit, skip: pagination.offset };
}

/** Creates the notification repository backed by Prisma. */
export function createNotificationRepository(deps: {
  readonly prisma: PrismaClient;
}): NotificationRepository {
  const { prisma } = deps;

  return {
    async create(input: CreateNotificationInput): Promise<NotificationRecord> {
      // upsert with an empty `update` is Prisma's standard "insert if not
      // exists" idiom: the unique constraint on (userId, submissionId, type)
      // guarantees this is atomic and race-safe at the database level, not
      // just a check-then-insert in application code.
      return prisma.notification.upsert({
        where: {
          userId_submissionId_type: {
            userId: input.userId,
            submissionId: input.submissionId,
            type: input.type,
          },
        },
        create: {
          userId: input.userId,
          submissionId: input.submissionId,
          type: input.type,
          message: input.message,
        },
        update: {},
        select: notificationSelect,
      });
    },

    async findByUser(userId: string, pagination?: Pagination): Promise<NotificationRecord[]> {
      return prisma.notification.findMany({
        where: { userId },
        orderBy: { createdAt: 'desc' },
        select: notificationSelect,
        ...toPage(pagination),
      });
    },

    async findById(id: string): Promise<NotificationRecord | null> {
      return prisma.notification.findUnique({ where: { id }, select: notificationSelect });
    },

    async markRead(id: string): Promise<NotificationRecord> {
      return prisma.notification.update({
        where: { id },
        data: { readAt: new Date() },
        select: notificationSelect,
      });
    },
  };
}
