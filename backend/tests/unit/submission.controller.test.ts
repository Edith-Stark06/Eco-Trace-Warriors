/* eslint-disable @typescript-eslint/unbound-method -- jest.fn() mocks carry no `this`; referencing them in expect() is safe */
import type { Request, Response } from 'express';
import { UserRole } from '@prisma/client';
import { createSubmissionController } from '@modules/submission';
import type { PublicSubmission, SubmissionService } from '@modules/submission';

const publicSubmission: PublicSubmission = {
  id: 'sub-1',
  userId: 'user-1',
  category: 'Laptop',
  description: null,
  estimatedWeight: 2.5,
  address: '12 MG Road, Bengaluru',
  latitude: 12.9716,
  longitude: 77.5946,
  imageUrls: [],
  status: 'PENDING',
  assignedCollectorId: null,
  assignedRecyclerId: null,
  pickupScheduledAt: null,
  completedAt: null,
  processingStartedAt: null,
  recycledAt: null,
  recyclerNotes: null,
  recoveredWeight: null,
  materialRecovery: null,
  createdAt: '2026-07-20T00:00:00.000Z',
  updatedAt: '2026-07-20T00:00:00.000Z',
};

function buildService(overrides: Partial<SubmissionService> = {}): jest.Mocked<SubmissionService> {
  return {
    create: jest.fn().mockResolvedValue(publicSubmission),
    list: jest.fn().mockResolvedValue([publicSubmission]),
    getById: jest.fn().mockResolvedValue(publicSubmission),
    update: jest.fn().mockResolvedValue(publicSubmission),
    delete: jest.fn().mockResolvedValue(undefined),
    assignCollector: jest.fn().mockResolvedValue(publicSubmission),
    acceptAssignment: jest.fn().mockResolvedValue(publicSubmission),
    startPickup: jest.fn().mockResolvedValue(publicSubmission),
    completePickup: jest.fn().mockResolvedValue(publicSubmission),
    getCollectorDashboard: jest.fn().mockResolvedValue([publicSubmission]),
    assignRecycler: jest.fn().mockResolvedValue(publicSubmission),
    startRecycling: jest.fn().mockResolvedValue(publicSubmission),
    completeRecycling: jest.fn().mockResolvedValue(publicSubmission),
    getRecyclerDashboard: jest.fn().mockResolvedValue([publicSubmission]),
    ...overrides,
  } as jest.Mocked<SubmissionService>;
}

function buildRes(): jest.Mocked<Response> {
  const res = {} as jest.Mocked<Response>;
  res.status = jest.fn().mockReturnValue(res);
  res.json = jest.fn().mockReturnValue(res);
  res.send = jest.fn().mockReturnValue(res);
  return res;
}

function buildReq(overrides: Partial<Request> = {}): Request {
  return {
    user: { userId: 'user-1', role: UserRole.CONSUMER },
    params: {},
    body: {},
    query: {},
    ...overrides,
  } as Request;
}

describe('createSubmissionController', () => {
  it('create → 201 with the success envelope and the actor as service caller', async () => {
    const service = buildService();
    const controller = createSubmissionController(service);
    const res = buildRes();
    const body = {
      category: 'Laptop',
      estimatedWeight: 2.5,
      address: 'x',
      latitude: 0,
      longitude: 0,
    };

    await controller.create(buildReq({ body }), res);

    expect(service.create).toHaveBeenCalledWith(
      { userId: 'user-1', role: UserRole.CONSUMER },
      body,
    );
    expect(res.status).toHaveBeenCalledWith(201);
    expect(res.json).toHaveBeenCalledWith({ success: true, data: publicSubmission });
  });

  it('list → 200 with an array payload and forwards pagination', async () => {
    const service = buildService();
    const res = buildRes();
    const query = { limit: 25, offset: 10 } as unknown as Request['query'];

    await createSubmissionController(service).list(buildReq({ query }), res);

    expect(service.list).toHaveBeenCalledWith(expect.anything(), { limit: 25, offset: 10 });
    expect(res.status).toHaveBeenCalledWith(200);
    expect(res.json).toHaveBeenCalledWith({ success: true, data: [publicSubmission] });
  });

  it('getById → 200 and passes the path id to the service', async () => {
    const service = buildService();
    const res = buildRes();

    await createSubmissionController(service).getById(buildReq({ params: { id: 'sub-1' } }), res);

    expect(service.getById).toHaveBeenCalledWith(expect.anything(), 'sub-1');
    expect(res.status).toHaveBeenCalledWith(200);
  });

  it('update → 200 and forwards id + body to the service', async () => {
    const service = buildService();
    const res = buildRes();
    const body = { category: 'Phone' };

    await createSubmissionController(service).update(
      buildReq({ params: { id: 'sub-1' }, body }),
      res,
    );

    expect(service.update).toHaveBeenCalledWith(expect.anything(), 'sub-1', body);
    expect(res.status).toHaveBeenCalledWith(200);
  });

  it('delete → 204 with no body', async () => {
    const service = buildService();
    const res = buildRes();

    await createSubmissionController(service).delete(buildReq({ params: { id: 'sub-1' } }), res);

    expect(service.delete).toHaveBeenCalledWith(expect.anything(), 'sub-1');
    expect(res.status).toHaveBeenCalledWith(204);
    expect(res.send).toHaveBeenCalled();
  });

  it('assignCollector → 200 and forwards id + collectorId', async () => {
    const service = buildService();
    const res = buildRes();

    await createSubmissionController(service).assignCollector(
      buildReq({ params: { id: 'sub-1' }, body: { collectorId: 'collector-1' } }),
      res,
    );

    expect(service.assignCollector).toHaveBeenCalledWith(expect.anything(), 'sub-1', 'collector-1');
    expect(res.status).toHaveBeenCalledWith(200);
    expect(res.json).toHaveBeenCalledWith({ success: true, data: publicSubmission });
  });

  it('acceptAssignment → 200 and passes the path id', async () => {
    const service = buildService();
    const res = buildRes();

    await createSubmissionController(service).acceptAssignment(
      buildReq({ params: { id: 'sub-1' } }),
      res,
    );

    expect(service.acceptAssignment).toHaveBeenCalledWith(expect.anything(), 'sub-1');
    expect(res.status).toHaveBeenCalledWith(200);
  });

  it('startPickup → 200 and passes the path id', async () => {
    const service = buildService();
    const res = buildRes();

    await createSubmissionController(service).startPickup(
      buildReq({ params: { id: 'sub-1' } }),
      res,
    );

    expect(service.startPickup).toHaveBeenCalledWith(expect.anything(), 'sub-1');
    expect(res.status).toHaveBeenCalledWith(200);
  });

  it('completePickup → 200 and passes the path id', async () => {
    const service = buildService();
    const res = buildRes();

    await createSubmissionController(service).completePickup(
      buildReq({ params: { id: 'sub-1' } }),
      res,
    );

    expect(service.completePickup).toHaveBeenCalledWith(expect.anything(), 'sub-1');
    expect(res.status).toHaveBeenCalledWith(200);
  });

  it('collectorDashboard → 200 with an array payload and forwards pagination', async () => {
    const service = buildService();
    const res = buildRes();
    const query = { limit: 5, offset: 0 } as unknown as Request['query'];

    await createSubmissionController(service).collectorDashboard(buildReq({ query }), res);

    expect(service.getCollectorDashboard).toHaveBeenCalledWith(expect.anything(), {
      limit: 5,
      offset: 0,
    });
    expect(res.status).toHaveBeenCalledWith(200);
    expect(res.json).toHaveBeenCalledWith({ success: true, data: [publicSubmission] });
  });

  it('assignRecycler → 200 and forwards id + recyclerId', async () => {
    const service = buildService();
    const res = buildRes();

    await createSubmissionController(service).assignRecycler(
      buildReq({ params: { id: 'sub-1' }, body: { recyclerId: 'recycler-1' } }),
      res,
    );

    expect(service.assignRecycler).toHaveBeenCalledWith(expect.anything(), 'sub-1', 'recycler-1');
    expect(res.status).toHaveBeenCalledWith(200);
    expect(res.json).toHaveBeenCalledWith({ success: true, data: publicSubmission });
  });

  it('startRecycling → 200 and passes the path id', async () => {
    const service = buildService();
    const res = buildRes();

    await createSubmissionController(service).startRecycling(
      buildReq({ params: { id: 'sub-1' } }),
      res,
    );

    expect(service.startRecycling).toHaveBeenCalledWith(expect.anything(), 'sub-1');
    expect(res.status).toHaveBeenCalledWith(200);
  });

  it('completeRecycling → 200 and forwards id + body', async () => {
    const service = buildService();
    const res = buildRes();
    const body = { recoveredWeight: 12.5, recyclerNotes: 'done' };

    await createSubmissionController(service).completeRecycling(
      buildReq({ params: { id: 'sub-1' }, body }),
      res,
    );

    expect(service.completeRecycling).toHaveBeenCalledWith(expect.anything(), 'sub-1', body);
    expect(res.status).toHaveBeenCalledWith(200);
  });

  it('recyclerDashboard → 200 with an array payload and forwards pagination', async () => {
    const service = buildService();
    const res = buildRes();
    const query = { limit: 5, offset: 0 } as unknown as Request['query'];

    await createSubmissionController(service).recyclerDashboard(buildReq({ query }), res);

    expect(service.getRecyclerDashboard).toHaveBeenCalledWith(expect.anything(), {
      limit: 5,
      offset: 0,
    });
    expect(res.status).toHaveBeenCalledWith(200);
    expect(res.json).toHaveBeenCalledWith({ success: true, data: [publicSubmission] });
  });
});
