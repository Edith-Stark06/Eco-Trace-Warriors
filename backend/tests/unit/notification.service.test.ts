/* eslint-disable @typescript-eslint/unbound-method -- jest.fn() mocks carry no `this`; referencing them in expect() is safe */
import { createNotificationService } from '@modules/notification';
import type { NotificationRecord, NotificationRepository } from '@modules/notification';
import { NotFoundError } from '@shared/errors';
import { createLogger } from '@shared/logging';

const unreadRecord: NotificationRecord = {
  id: 'notif-1',
  userId: 'user-1',
  submissionId: 'sub-1',
  type: 'COLLECTOR_ASSIGNED',
  message: 'Your collector has been assigned for your Laptop submission.',
  createdAt: new Date('2026-07-20T00:00:00.000Z'),
  readAt: null,
};

const readRecord: NotificationRecord = {
  ...unreadRecord,
  id: 'notif-2',
  readAt: new Date('2026-07-21T00:00:00.000Z'),
};

function buildRepo(
  overrides: Partial<NotificationRepository> = {},
): jest.Mocked<NotificationRepository> {
  return {
    create: jest.fn().mockResolvedValue(unreadRecord),
    findByUser: jest.fn().mockResolvedValue([unreadRecord]),
    findById: jest.fn().mockResolvedValue(unreadRecord),
    markRead: jest
      .fn()
      .mockResolvedValue({ ...unreadRecord, readAt: new Date('2026-07-22T00:00:00.000Z') }),
    ...overrides,
  } as jest.Mocked<NotificationRepository>;
}

function buildService(repo: jest.Mocked<NotificationRepository> = buildRepo()): {
  service: ReturnType<typeof createNotificationService>;
  repo: jest.Mocked<NotificationRepository>;
} {
  const service = createNotificationService({
    notifications: repo,
    logger: createLogger({ logLevel: 'fatal', nodeEnv: 'test' }),
  });
  return { service, repo };
}

describe('createNotificationService', () => {
  describe('createNotification', () => {
    it('creates a notification via the repository and returns the public shape', async () => {
      const { service, repo } = buildService();

      const result = await service.createNotification(
        'user-1',
        'sub-1',
        'COLLECTOR_ASSIGNED',
        'Your collector has been assigned for your Laptop submission.',
      );

      expect(repo.create).toHaveBeenCalledWith({
        userId: 'user-1',
        submissionId: 'sub-1',
        type: 'COLLECTOR_ASSIGNED',
        message: 'Your collector has been assigned for your Laptop submission.',
      });
      expect(result).toEqual({
        id: 'notif-1',
        submissionId: 'sub-1',
        type: 'COLLECTOR_ASSIGNED',
        message: 'Your collector has been assigned for your Laptop submission.',
        createdAt: '2026-07-20T00:00:00.000Z',
        readAt: null,
        isRead: false,
      });
    });

    it('never exposes userId on the public shape', async () => {
      const { service } = buildService();

      const result = await service.createNotification(
        'user-1',
        'sub-1',
        'COLLECTOR_ASSIGNED',
        'msg',
      );

      expect(result).not.toHaveProperty('userId');
    });
  });

  describe('listForUser', () => {
    it("returns the user's notifications, newest first, as delegated by the repository", async () => {
      const { service, repo } = buildService();

      const result = await service.listForUser('user-1');

      expect(repo.findByUser).toHaveBeenCalledWith('user-1', undefined);
      expect(result).toHaveLength(1);
      expect(result[0]?.id).toBe('notif-1');
    });

    it('forwards pagination to the repository', async () => {
      const { service, repo } = buildService();

      await service.listForUser('user-1', { limit: 10, offset: 0 });

      expect(repo.findByUser).toHaveBeenCalledWith('user-1', { limit: 10, offset: 0 });
    });

    it('marks isRead correctly for both read and unread rows', async () => {
      const repo = buildRepo({
        findByUser: jest.fn().mockResolvedValue([unreadRecord, readRecord]),
      });
      const { service } = buildService(repo);

      const result = await service.listForUser('user-1');

      expect(result[0]?.isRead).toBe(false);
      expect(result[1]?.isRead).toBe(true);
    });

    it('returns an empty array, not an error, when the user has no notifications', async () => {
      const repo = buildRepo({ findByUser: jest.fn().mockResolvedValue([]) });
      const { service } = buildService(repo);

      const result = await service.listForUser('user-1');

      expect(result).toEqual([]);
    });
  });

  describe('markRead', () => {
    it('marks an unread notification read when it belongs to the caller', async () => {
      const { service, repo } = buildService();

      const result = await service.markRead('user-1', 'notif-1');

      expect(repo.markRead).toHaveBeenCalledWith('notif-1');
      expect(result.isRead).toBe(true);
    });

    it('is a no-op success (does not call repo.markRead) when already read', async () => {
      const repo = buildRepo({ findById: jest.fn().mockResolvedValue(readRecord) });
      const { service } = buildService(repo);

      const result = await service.markRead('user-1', 'notif-2');

      expect(repo.markRead).not.toHaveBeenCalled();
      expect(result.isRead).toBe(true);
    });

    it('throws NotFoundError (never Forbidden) when the notification does not exist', async () => {
      const repo = buildRepo({ findById: jest.fn().mockResolvedValue(null) });
      const { service } = buildService(repo);

      await expect(service.markRead('user-1', 'ghost')).rejects.toBeInstanceOf(NotFoundError);
    });

    it('throws NotFoundError (never Forbidden, never leaking ownership) when the notification belongs to a different user', async () => {
      const repo = buildRepo({
        findById: jest.fn().mockResolvedValue({ ...unreadRecord, userId: 'user-2' }),
      });
      const { service } = buildService(repo);

      await expect(service.markRead('user-1', 'notif-1')).rejects.toBeInstanceOf(NotFoundError);
      expect(repo.markRead).not.toHaveBeenCalled();
    });
  });
});
