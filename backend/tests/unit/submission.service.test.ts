/* eslint-disable @typescript-eslint/unbound-method -- jest.fn() mocks carry no `this`; referencing them in expect() is safe */
import { UserRole } from '@prisma/client';
import { createSubmissionService } from '@modules/submission';
import type {
  SubmissionActor,
  SubmissionRecord,
  SubmissionRepository,
  SubmissionServiceDeps,
} from '@modules/submission';
import { ForbiddenError, NotFoundError } from '@shared/errors';
import { createLogger } from '@shared/logging';

const OWNER: SubmissionActor = { userId: 'user-1', role: UserRole.CONSUMER };
const OTHER: SubmissionActor = { userId: 'user-2', role: UserRole.CONSUMER };
const ADMIN: SubmissionActor = { userId: 'admin-1', role: UserRole.ADMIN };

const pendingRecord: SubmissionRecord = {
  id: 'sub-1',
  userId: 'user-1',
  category: 'Laptop',
  description: 'Old work laptop',
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
  createdAt: new Date('2026-07-20T00:00:00.000Z'),
  updatedAt: new Date('2026-07-20T00:00:00.000Z'),
};

const assignedRecord: SubmissionRecord = {
  ...pendingRecord,
  id: 'sub-2',
  status: 'ASSIGNED',
  assignedCollectorId: 'collector-1',
};

function buildRepo(
  overrides: Partial<SubmissionRepository> = {},
): jest.Mocked<SubmissionRepository> {
  return {
    create: jest.fn().mockResolvedValue(pendingRecord),
    findById: jest.fn().mockResolvedValue(pendingRecord),
    findByUser: jest.fn().mockResolvedValue([pendingRecord]),
    findAll: jest.fn().mockResolvedValue([pendingRecord, assignedRecord]),
    update: jest.fn().mockResolvedValue(pendingRecord),
    delete: jest.fn().mockResolvedValue(undefined),
    ...overrides,
  } as jest.Mocked<SubmissionRepository>;
}

function buildService(repo: jest.Mocked<SubmissionRepository> = buildRepo()): {
  service: ReturnType<typeof createSubmissionService>;
  repo: jest.Mocked<SubmissionRepository>;
} {
  const deps: SubmissionServiceDeps = {
    submissions: repo,
    logger: createLogger({ logLevel: 'fatal', nodeEnv: 'test' }),
  };
  return { service: createSubmissionService(deps), repo };
}

const createInput = {
  category: 'Laptop',
  description: 'Old work laptop',
  estimatedWeight: 2.5,
  address: '12 MG Road, Bengaluru',
  latitude: 12.9716,
  longitude: 77.5946,
};

describe('createSubmissionService', () => {
  describe('create', () => {
    it('creates a submission owned by the actor with PENDING status', async () => {
      const { service, repo } = buildService();

      const result = await service.create(OWNER, createInput);

      expect(repo.create).toHaveBeenCalledWith(
        expect.objectContaining({ ...createInput, userId: 'user-1' }),
      );
      expect(result).toEqual(
        expect.objectContaining({ id: 'sub-1', userId: 'user-1', status: 'PENDING' }),
      );
    });

    it('serializes dates to ISO strings and never leaks Date objects', async () => {
      const { service } = buildService();

      const result = await service.create(OWNER, createInput);

      expect(result.createdAt).toBe('2026-07-20T00:00:00.000Z');
      expect(result.pickupScheduledAt).toBeNull();
      expect(result.completedAt).toBeNull();
    });
  });

  describe('list', () => {
    it('returns only the actor’s own submissions for a consumer', async () => {
      const { service, repo } = buildService();

      const result = await service.list(OWNER);

      expect(repo.findByUser).toHaveBeenCalledWith('user-1');
      expect(repo.findAll).not.toHaveBeenCalled();
      expect(result).toHaveLength(1);
    });

    it('returns every submission for an admin', async () => {
      const { service, repo } = buildService();

      const result = await service.list(ADMIN);

      expect(repo.findAll).toHaveBeenCalled();
      expect(repo.findByUser).not.toHaveBeenCalled();
      expect(result).toHaveLength(2);
    });
  });

  describe('getById', () => {
    it('returns the submission for its owner', async () => {
      const { service } = buildService();

      const result = await service.getById(OWNER, 'sub-1');

      expect(result.id).toBe('sub-1');
    });

    it('returns the submission for an admin regardless of owner', async () => {
      const { service } = buildService();

      const result = await service.getById(ADMIN, 'sub-1');

      expect(result.id).toBe('sub-1');
    });

    it('throws NotFoundError when the submission does not exist', async () => {
      const { service } = buildService(buildRepo({ findById: jest.fn().mockResolvedValue(null) }));

      await expect(service.getById(OWNER, 'missing')).rejects.toBeInstanceOf(NotFoundError);
    });

    it('throws NotFoundError (not Forbidden) when a non-owner requests it', async () => {
      const { service } = buildService();

      await expect(service.getById(OTHER, 'sub-1')).rejects.toBeInstanceOf(NotFoundError);
    });
  });

  describe('update', () => {
    it('updates a PENDING submission for its owner', async () => {
      const { service, repo } = buildService();

      await service.update(OWNER, 'sub-1', { category: 'Phone' });

      expect(repo.update).toHaveBeenCalledWith('sub-1', { category: 'Phone' });
    });

    it('forbids the owner from editing once assigned', async () => {
      const { service, repo } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(assignedRecord) }),
      );

      await expect(service.update(OWNER, 'sub-2', { category: 'Phone' })).rejects.toBeInstanceOf(
        ForbiddenError,
      );
      expect(repo.update).not.toHaveBeenCalled();
    });

    it('allows an admin to edit an assigned submission', async () => {
      const { service, repo } = buildService(
        buildRepo({
          findById: jest.fn().mockResolvedValue(assignedRecord),
          update: jest.fn().mockResolvedValue(assignedRecord),
        }),
      );

      await service.update(ADMIN, 'sub-2', { category: 'Phone' });

      expect(repo.update).toHaveBeenCalledWith('sub-2', { category: 'Phone' });
    });

    it('throws NotFoundError when a non-owner updates', async () => {
      const { service } = buildService();

      await expect(service.update(OTHER, 'sub-1', { category: 'Phone' })).rejects.toBeInstanceOf(
        NotFoundError,
      );
    });
  });

  describe('delete', () => {
    it('deletes a PENDING submission for its owner', async () => {
      const { service, repo } = buildService();

      await service.delete(OWNER, 'sub-1');

      expect(repo.delete).toHaveBeenCalledWith('sub-1');
    });

    it('forbids the owner from deleting once assigned', async () => {
      const { service, repo } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(assignedRecord) }),
      );

      await expect(service.delete(OWNER, 'sub-2')).rejects.toBeInstanceOf(ForbiddenError);
      expect(repo.delete).not.toHaveBeenCalled();
    });

    it('allows an admin to delete an assigned submission', async () => {
      const { service, repo } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(assignedRecord) }),
      );

      await service.delete(ADMIN, 'sub-2');

      expect(repo.delete).toHaveBeenCalledWith('sub-2');
    });

    it('throws NotFoundError when the submission is missing', async () => {
      const { service } = buildService(buildRepo({ findById: jest.fn().mockResolvedValue(null) }));

      await expect(service.delete(OWNER, 'missing')).rejects.toBeInstanceOf(NotFoundError);
    });
  });
});
