import { randomUUID } from 'node:crypto';
import type { Pagination } from '@shared/pagination';
import type {
  CreateNotificationInput,
  NotificationRecord,
  NotificationRepository,
} from '@modules/notification';

/**
 * In-memory notification repository for tests — mirrors
 * in-memory-reward-repository.ts's role for the rewards module. Lets the
 * full HTTP stack (and the submission service's best-effort notification
 * hooks) run through Supertest without a real database.
 */
export function createInMemoryNotificationRepository(): NotificationRepository {
  const byId = new Map<string, NotificationRecord>();
  // Mirrors the real Prisma unique constraint (userId, submissionId, type),
  // so idempotency is genuinely exercised by tests, not just assumed.
  const byUniqueKey = new Map<string, string>();
  let clock = 0;
  const nextDate = (): Date => new Date(Date.UTC(2026, 6, 22, 0, 0, 0, clock++));

  const uniqueKey = (userId: string, submissionId: string, type: string): string =>
    `${userId}:${submissionId}:${type}`;

  return {
    create(input: CreateNotificationInput): Promise<NotificationRecord> {
      const key = uniqueKey(input.userId, input.submissionId, input.type);
      const existingId = byUniqueKey.get(key);
      if (existingId) {
        // Idempotent: matches the real upsert-with-empty-update behavior.
        return Promise.resolve(byId.get(existingId)!);
      }

      const record: NotificationRecord = {
        id: randomUUID(),
        userId: input.userId,
        submissionId: input.submissionId,
        type: input.type,
        message: input.message,
        createdAt: nextDate(),
        readAt: null,
      };
      byId.set(record.id, record);
      byUniqueKey.set(key, record.id);
      return Promise.resolve(record);
    },

    findByUser(userId: string, pagination?: Pagination): Promise<NotificationRecord[]> {
      const rows = [...byId.values()]
        .filter((r) => r.userId === userId)
        .sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime());
      const windowed = pagination
        ? rows.slice(pagination.offset, pagination.offset + pagination.limit)
        : rows;
      return Promise.resolve(windowed);
    },

    findById(id: string): Promise<NotificationRecord | null> {
      return Promise.resolve(byId.get(id) ?? null);
    },

    markRead(id: string): Promise<NotificationRecord> {
      const existing = byId.get(id);
      if (!existing) {
        throw new Error(`Notification ${id} not found`);
      }
      const updated: NotificationRecord = { ...existing, readAt: nextDate() };
      byId.set(id, updated);
      return Promise.resolve(updated);
    },
  };
}
