/* eslint-disable @typescript-eslint/unbound-method -- jest.fn() mocks carry no `this`; referencing them in expect() is safe */
import type { Request, Response } from 'express';
import { UserRole } from '@prisma/client';
import { createNotificationController } from '@modules/notification';
import type { NotificationService, PublicNotification } from '@modules/notification';

const publicNotification: PublicNotification = {
  id: 'notif-1',
  submissionId: 'sub-1',
  type: 'COLLECTOR_ASSIGNED',
  message: 'Your collector has been assigned for your Laptop submission.',
  createdAt: '2026-07-20T00:00:00.000Z',
  readAt: null,
  isRead: false,
};

function buildService(
  overrides: Partial<NotificationService> = {},
): jest.Mocked<NotificationService> {
  return {
    createNotification: jest.fn().mockResolvedValue(publicNotification),
    listForUser: jest.fn().mockResolvedValue([publicNotification]),
    markRead: jest
      .fn()
      .mockResolvedValue({
        ...publicNotification,
        readAt: '2026-07-21T00:00:00.000Z',
        isRead: true,
      }),
    ...overrides,
  } as jest.Mocked<NotificationService>;
}

function buildRes(): jest.Mocked<Response> {
  const res = {} as jest.Mocked<Response>;
  res.status = jest.fn().mockReturnValue(res);
  res.json = jest.fn().mockReturnValue(res);
  return res;
}

function buildReq(overrides: Partial<Request> = {}): Request {
  return {
    user: { userId: 'user-1', role: UserRole.CONSUMER },
    params: {},
    query: {},
    ...overrides,
  } as Request;
}

describe('createNotificationController', () => {
  it('list → 200 with the caller-scoped notification array, using the token userId', async () => {
    const service = buildService();
    const res = buildRes();
    const query = { limit: 20, offset: 0 } as unknown as Request['query'];

    await createNotificationController(service).list(buildReq({ query }), res);

    expect(service.listForUser).toHaveBeenCalledWith('user-1', { limit: 20, offset: 0 });
    expect(res.status).toHaveBeenCalledWith(200);
    expect(res.json).toHaveBeenCalledWith({ success: true, data: [publicNotification] });
  });

  it('markRead → 200 and forwards the token userId + path id to the service', async () => {
    const service = buildService();
    const res = buildRes();

    await createNotificationController(service).markRead(
      buildReq({ params: { id: 'notif-1' } }),
      res,
    );

    expect(service.markRead).toHaveBeenCalledWith('user-1', 'notif-1');
    expect(res.status).toHaveBeenCalledWith(200);
  });

  it('never reads a userId from params/query — only from the authenticated request context', async () => {
    const service = buildService();
    const res = buildRes();
    // Even if a client tried to smuggle a different id in via params/query,
    // the controller must never look there for the recipient identity.
    const req = buildReq({
      params: { id: 'notif-1', userId: 'someone-else' } as unknown as Request['params'],
      query: { userId: 'someone-else' } as unknown as Request['query'],
    });

    await createNotificationController(service).markRead(req, res);

    expect(service.markRead).toHaveBeenCalledWith('user-1', 'notif-1');
  });
});
