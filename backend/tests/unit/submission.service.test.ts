/* eslint-disable @typescript-eslint/unbound-method -- jest.fn() mocks carry no `this`; referencing them in expect() is safe */
import { UserRole } from '@prisma/client';
import { createSubmissionService, validateTransition } from '@modules/submission';
import type {
  CollectorRecord,
  SubmissionActor,
  SubmissionRecord,
  SubmissionRepository,
  SubmissionServiceDeps,
} from '@modules/submission';
import { ConflictError, ForbiddenError, NotFoundError } from '@shared/errors';
import { createLogger } from '@shared/logging';
import type { RewardService } from '@modules/rewards';

const OWNER: SubmissionActor = { userId: 'user-1', role: UserRole.CONSUMER };
const OTHER: SubmissionActor = { userId: 'user-2', role: UserRole.CONSUMER };
const ADMIN: SubmissionActor = { userId: 'admin-1', role: UserRole.ADMIN };
const GOVERNMENT: SubmissionActor = { userId: 'gov-1', role: UserRole.GOVERNMENT };
const COLLECTOR: SubmissionActor = { userId: 'collector-1', role: UserRole.COLLECTOR };
const OTHER_COLLECTOR: SubmissionActor = { userId: 'collector-2', role: UserRole.COLLECTOR };
const RECYCLER: SubmissionActor = { userId: 'recycler-1', role: UserRole.RECYCLER };
const OTHER_RECYCLER: SubmissionActor = { userId: 'recycler-2', role: UserRole.RECYCLER };

const activeCollectorRecord: CollectorRecord = {
  id: 'collector-1',
  role: UserRole.COLLECTOR,
  isActive: true,
};

const activeRecyclerRecord: CollectorRecord = {
  id: 'recycler-1',
  role: UserRole.RECYCLER,
  isActive: true,
};

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
  processingStartedAt: null,
  recycledAt: null,
  recyclerNotes: null,
  recoveredWeight: null,
  materialRecovery: null,
  createdAt: new Date('2026-07-20T00:00:00.000Z'),
  updatedAt: new Date('2026-07-20T00:00:00.000Z'),
};

const assignedRecord: SubmissionRecord = {
  ...pendingRecord,
  id: 'sub-2',
  status: 'ASSIGNED',
  assignedCollectorId: 'collector-1',
};

const acceptedRecord: SubmissionRecord = {
  ...pendingRecord,
  id: 'sub-3',
  status: 'ACCEPTED',
  assignedCollectorId: 'collector-1',
};

const inProgressRecord: SubmissionRecord = {
  ...pendingRecord,
  id: 'sub-4',
  status: 'IN_PROGRESS',
  assignedCollectorId: 'collector-1',
};

const collectedRecord: SubmissionRecord = {
  ...pendingRecord,
  id: 'sub-5',
  status: 'COLLECTED',
  assignedCollectorId: 'collector-1',
  assignedRecyclerId: 'recycler-1',
};

const recyclingRecord: SubmissionRecord = {
  ...pendingRecord,
  id: 'sub-6',
  status: 'RECYCLING',
  assignedCollectorId: 'collector-1',
  assignedRecyclerId: 'recycler-1',
  processingStartedAt: new Date('2026-07-22T09:00:00.000Z'),
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
    assignCollector: jest.fn().mockResolvedValue(assignedRecord),
    updateStatus: jest.fn().mockResolvedValue(acceptedRecord),
    updatePickupSchedule: jest.fn().mockResolvedValue(inProgressRecord),
    findByCollector: jest.fn().mockResolvedValue([assignedRecord]),
    findCollectorAssignments: jest.fn().mockResolvedValue([assignedRecord]),
    findCollectorById: jest.fn().mockResolvedValue(activeCollectorRecord),
    assignRecycler: jest.fn().mockResolvedValue(collectedRecord),
    findRecyclerAssignments: jest.fn().mockResolvedValue([collectedRecord]),
    findRecyclerById: jest.fn().mockResolvedValue(activeRecyclerRecord),
    updateRecyclerProcessing: jest.fn().mockResolvedValue(recyclingRecord),
    updateRecyclerCompletion: jest
      .fn()
      .mockResolvedValue({ ...recyclingRecord, status: 'RECYCLED' }),
    ...overrides,
  } as jest.Mocked<SubmissionRepository>;
}

function buildRewardService(overrides?: Partial<RewardService>): RewardService {
  return {
    issueReward: jest.fn().mockResolvedValue({
      rewardTransaction: {
        id: 'reward-1',
        submissionId: 'sub-6',
        points: 100,
        reason: 'RECYCLING',
        createdAt: new Date().toISOString(),
      },
      greenCoinsAwarded: 100,
      updatedBalance: 100,
      sustainability: {
        co2Saved: 25,
        energySaved: 15,
        landfillDiverted: 1,
        co2Unit: 'kg',
        energyUnit: 'kWh',
        landfillUnit: 'kg',
      },
    }),
    getRewardHistory: jest.fn().mockResolvedValue([]),
    getBalance: jest.fn().mockResolvedValue({
      greenCoins: 250,
      totalRewards: 250,
      totalCO2Saved: 25,
      totalEnergySaved: 15,
      totalLandfillDiverted: 2.5,
    }),
    calculateRewardPoints: jest.fn().mockReturnValue(100),
    calculateEnvironmentalImpact: jest.fn().mockReturnValue({
      co2Saved: 25,
      energySaved: 15,
      landfillDiverted: 2.5,
      co2Unit: 'kg',
      energyUnit: 'kWh',
      landfillUnit: 'kg',
    }),
    ...overrides,
  };
}

function buildService(
  repo: jest.Mocked<SubmissionRepository> = buildRepo(),
  rewards?: Partial<RewardService>,
): {
  service: ReturnType<typeof createSubmissionService>;
  repo: jest.Mocked<SubmissionRepository>;
} {
  const deps: SubmissionServiceDeps = {
    submissions: repo,
    logger: createLogger({ logLevel: 'fatal', nodeEnv: 'test' }),
    rewards: buildRewardService(rewards),
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

      expect(repo.findByUser).toHaveBeenCalledWith('user-1', undefined);
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

    it('returns every submission for a government actor (audit visibility, P8.5)', async () => {
      const { service, repo } = buildService();

      const result = await service.list(GOVERNMENT);

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

    it('returns the submission for a government actor regardless of owner (audit visibility, P8.5)', async () => {
      const { service } = buildService();

      const result = await service.getById(GOVERNMENT, 'sub-1');

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

describe('validateTransition', () => {
  it('permits each legal step of the collector workflow', () => {
    expect(() => validateTransition('PENDING', 'ASSIGNED')).not.toThrow();
    expect(() => validateTransition('ASSIGNED', 'ACCEPTED')).not.toThrow();
    expect(() => validateTransition('ACCEPTED', 'IN_PROGRESS')).not.toThrow();
    expect(() => validateTransition('IN_PROGRESS', 'COLLECTED')).not.toThrow();
  });

  it('permits each legal step of the recycler workflow', () => {
    expect(() => validateTransition('COLLECTED', 'RECYCLING')).not.toThrow();
    expect(() => validateTransition('RECYCLING', 'RECYCLED')).not.toThrow();
  });

  it('rejects skipping a step', () => {
    expect(() => validateTransition('PENDING', 'ACCEPTED')).toThrow(ConflictError);
    expect(() => validateTransition('ASSIGNED', 'IN_PROGRESS')).toThrow(ConflictError);
    expect(() => validateTransition('PENDING', 'COLLECTED')).toThrow(ConflictError);
    expect(() => validateTransition('COLLECTED', 'RECYCLED')).toThrow(ConflictError);
  });

  it('rejects moving backwards', () => {
    expect(() => validateTransition('ACCEPTED', 'ASSIGNED')).toThrow(ConflictError);
    expect(() => validateTransition('COLLECTED', 'IN_PROGRESS')).toThrow(ConflictError);
    expect(() => validateTransition('RECYCLING', 'COLLECTED')).toThrow(ConflictError);
  });

  it('rejects any transition out of a terminal status', () => {
    expect(() => validateTransition('RECYCLED', 'RECYCLING')).toThrow(ConflictError);
    expect(() => validateTransition('REJECTED', 'ASSIGNED')).toThrow(ConflictError);
  });
});

describe('createSubmissionService — collector workflow', () => {
  describe('assignCollector', () => {
    it('assigns a collector to a PENDING submission for an admin', async () => {
      const { service, repo } = buildService();

      const result = await service.assignCollector(ADMIN, 'sub-1', 'collector-1');

      expect(repo.findCollectorById).toHaveBeenCalledWith('collector-1');
      expect(repo.assignCollector).toHaveBeenCalledWith('sub-1', 'collector-1');
      expect(result.status).toBe('ASSIGNED');
    });

    it('assigns a collector for a government actor', async () => {
      const { service, repo } = buildService();

      await service.assignCollector(GOVERNMENT, 'sub-1', 'collector-1');

      expect(repo.assignCollector).toHaveBeenCalledWith('sub-1', 'collector-1');
    });

    it('forbids a collector from assigning (cannot self-assign)', async () => {
      const { service, repo } = buildService();

      await expect(
        service.assignCollector(COLLECTOR, 'sub-1', 'collector-1'),
      ).rejects.toBeInstanceOf(ForbiddenError);
      expect(repo.assignCollector).not.toHaveBeenCalled();
    });

    it('forbids a consumer from assigning', async () => {
      const { service } = buildService();

      await expect(service.assignCollector(OWNER, 'sub-1', 'collector-1')).rejects.toBeInstanceOf(
        ForbiddenError,
      );
    });

    it('throws NotFoundError when the submission does not exist', async () => {
      const { service } = buildService(buildRepo({ findById: jest.fn().mockResolvedValue(null) }));

      await expect(service.assignCollector(ADMIN, 'missing', 'collector-1')).rejects.toBeInstanceOf(
        NotFoundError,
      );
    });

    it('throws NotFoundError when the collector id is unknown', async () => {
      const { service, repo } = buildService(
        buildRepo({ findCollectorById: jest.fn().mockResolvedValue(null) }),
      );

      await expect(service.assignCollector(ADMIN, 'sub-1', 'ghost')).rejects.toBeInstanceOf(
        NotFoundError,
      );
      expect(repo.assignCollector).not.toHaveBeenCalled();
    });

    it('throws NotFoundError when the target user is not a collector', async () => {
      const { service } = buildService(
        buildRepo({
          findCollectorById: jest
            .fn()
            .mockResolvedValue({ id: 'user-9', role: UserRole.RECYCLER, isActive: true }),
        }),
      );

      await expect(service.assignCollector(ADMIN, 'sub-1', 'user-9')).rejects.toBeInstanceOf(
        NotFoundError,
      );
    });

    it('rejects an inactive collector', async () => {
      const { service } = buildService(
        buildRepo({
          findCollectorById: jest
            .fn()
            .mockResolvedValue({ id: 'collector-1', role: UserRole.COLLECTOR, isActive: false }),
        }),
      );

      await expect(service.assignCollector(ADMIN, 'sub-1', 'collector-1')).rejects.toBeInstanceOf(
        NotFoundError,
      );
    });

    it('lets an admin override and re-assign an already ASSIGNED submission', async () => {
      const { service, repo } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(assignedRecord) }),
      );

      await service.assignCollector(ADMIN, 'sub-2', 'collector-1');

      expect(repo.assignCollector).toHaveBeenCalledWith('sub-2', 'collector-1');
    });

    it('forbids a government actor from re-assigning outside PENDING (no override)', async () => {
      const { service, repo } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(assignedRecord) }),
      );

      await expect(
        service.assignCollector(GOVERNMENT, 'sub-2', 'collector-1'),
      ).rejects.toBeInstanceOf(ConflictError);
      expect(repo.assignCollector).not.toHaveBeenCalled();
    });
  });

  describe('acceptAssignment', () => {
    it('moves ASSIGNED → ACCEPTED for the assigned collector', async () => {
      const { service, repo } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(assignedRecord) }),
      );

      const result = await service.acceptAssignment(COLLECTOR, 'sub-2');

      expect(repo.updateStatus).toHaveBeenCalledWith('sub-2', 'ACCEPTED');
      expect(result.status).toBe('ACCEPTED');
    });

    it('throws NotFoundError for a collector who is not the assignee', async () => {
      const { service, repo } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(assignedRecord) }),
      );

      await expect(service.acceptAssignment(OTHER_COLLECTOR, 'sub-2')).rejects.toBeInstanceOf(
        NotFoundError,
      );
      expect(repo.updateStatus).not.toHaveBeenCalled();
    });

    it('throws ConflictError when the submission is not ASSIGNED', async () => {
      const { service, repo } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(acceptedRecord) }),
      );

      await expect(service.acceptAssignment(COLLECTOR, 'sub-3')).rejects.toBeInstanceOf(
        ConflictError,
      );
      expect(repo.updateStatus).not.toHaveBeenCalled();
    });
  });

  describe('startPickup', () => {
    it('moves ACCEPTED → IN_PROGRESS and stamps the pickup time', async () => {
      const clock = new Date('2026-07-22T09:00:00.000Z');
      const repo = buildRepo({ findById: jest.fn().mockResolvedValue(acceptedRecord) });
      const service = createSubmissionService({
        submissions: repo,
        logger: createLogger({ logLevel: 'fatal', nodeEnv: 'test' }),
        rewards: buildRewardService(),
        now: () => clock,
      });

      await service.startPickup(COLLECTOR, 'sub-3');

      expect(repo.updateStatus).toHaveBeenCalledWith('sub-3', 'IN_PROGRESS');
      expect(repo.updatePickupSchedule).toHaveBeenCalledWith('sub-3', clock);
    });

    it('throws ConflictError when the submission is not ACCEPTED', async () => {
      const { service } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(assignedRecord) }),
      );

      await expect(service.startPickup(COLLECTOR, 'sub-2')).rejects.toBeInstanceOf(ConflictError);
    });

    it('throws NotFoundError for a non-assignee collector', async () => {
      const { service } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(acceptedRecord) }),
      );

      await expect(service.startPickup(OTHER_COLLECTOR, 'sub-3')).rejects.toBeInstanceOf(
        NotFoundError,
      );
    });
  });

  describe('completePickup', () => {
    it('moves IN_PROGRESS → COLLECTED for the assigned collector', async () => {
      const collected: SubmissionRecord = { ...inProgressRecord, status: 'COLLECTED' };
      const { service, repo } = buildService(
        buildRepo({
          findById: jest.fn().mockResolvedValue(inProgressRecord),
          updateStatus: jest.fn().mockResolvedValue(collected),
        }),
      );

      const result = await service.completePickup(COLLECTOR, 'sub-4');

      expect(repo.updateStatus).toHaveBeenCalledWith('sub-4', 'COLLECTED');
      expect(result.status).toBe('COLLECTED');
    });

    it('throws ConflictError when the submission is not IN_PROGRESS', async () => {
      const { service } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(acceptedRecord) }),
      );

      await expect(service.completePickup(COLLECTOR, 'sub-3')).rejects.toBeInstanceOf(
        ConflictError,
      );
    });
  });

  describe('getCollectorDashboard', () => {
    it('returns the active assignments for the authenticated collector', async () => {
      const { service, repo } = buildService();

      const result = await service.getCollectorDashboard(COLLECTOR);

      expect(repo.findCollectorAssignments).toHaveBeenCalledWith('collector-1', undefined);
      expect(result).toHaveLength(1);
    });
  });
});

describe('createSubmissionService — recycler workflow', () => {
  describe('assignRecycler', () => {
    it('assigns a recycler to a COLLECTED submission for an admin', async () => {
      const { service, repo } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(collectedRecord) }),
      );

      const result = await service.assignRecycler(ADMIN, 'sub-5', 'recycler-1');

      expect(repo.findRecyclerById).toHaveBeenCalledWith('recycler-1');
      expect(repo.assignRecycler).toHaveBeenCalledWith('sub-5', 'recycler-1');
      expect(result.assignedRecyclerId).toBe('recycler-1');
    });

    it('assigns a recycler for a government actor on a COLLECTED submission', async () => {
      const { service, repo } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(collectedRecord) }),
      );

      await service.assignRecycler(GOVERNMENT, 'sub-5', 'recycler-1');

      expect(repo.assignRecycler).toHaveBeenCalledWith('sub-5', 'recycler-1');
    });

    it('forbids a recycler from assigning (cannot self-assign)', async () => {
      const { service, repo } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(collectedRecord) }),
      );

      await expect(service.assignRecycler(RECYCLER, 'sub-5', 'recycler-1')).rejects.toBeInstanceOf(
        ForbiddenError,
      );
      expect(repo.assignRecycler).not.toHaveBeenCalled();
    });

    it('forbids a consumer from assigning a recycler', async () => {
      const { service } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(collectedRecord) }),
      );

      await expect(service.assignRecycler(OWNER, 'sub-5', 'recycler-1')).rejects.toBeInstanceOf(
        ForbiddenError,
      );
    });

    it('throws NotFoundError when the submission does not exist', async () => {
      const { service } = buildService(buildRepo({ findById: jest.fn().mockResolvedValue(null) }));

      await expect(service.assignRecycler(ADMIN, 'missing', 'recycler-1')).rejects.toBeInstanceOf(
        NotFoundError,
      );
    });

    it('throws NotFoundError when the recycler id is unknown', async () => {
      const { service, repo } = buildService(
        buildRepo({
          findById: jest.fn().mockResolvedValue(collectedRecord),
          findRecyclerById: jest.fn().mockResolvedValue(null),
        }),
      );

      await expect(service.assignRecycler(ADMIN, 'sub-5', 'ghost')).rejects.toBeInstanceOf(
        NotFoundError,
      );
      expect(repo.assignRecycler).not.toHaveBeenCalled();
    });

    it('throws NotFoundError when the target user is not a recycler', async () => {
      const { service } = buildService(
        buildRepo({
          findById: jest.fn().mockResolvedValue(collectedRecord),
          findRecyclerById: jest
            .fn()
            .mockResolvedValue({ id: 'user-9', role: UserRole.COLLECTOR, isActive: true }),
        }),
      );

      await expect(service.assignRecycler(ADMIN, 'sub-5', 'user-9')).rejects.toBeInstanceOf(
        NotFoundError,
      );
    });

    it('rejects an inactive recycler', async () => {
      const { service } = buildService(
        buildRepo({
          findById: jest.fn().mockResolvedValue(collectedRecord),
          findRecyclerById: jest
            .fn()
            .mockResolvedValue({ id: 'recycler-1', role: UserRole.RECYCLER, isActive: false }),
        }),
      );

      await expect(service.assignRecycler(ADMIN, 'sub-5', 'recycler-1')).rejects.toBeInstanceOf(
        NotFoundError,
      );
    });

    it('forbids a government actor from assigning before COLLECTED', async () => {
      const { service, repo } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(assignedRecord) }),
      );

      await expect(
        service.assignRecycler(GOVERNMENT, 'sub-2', 'recycler-1'),
      ).rejects.toBeInstanceOf(ConflictError);
      expect(repo.assignRecycler).not.toHaveBeenCalled();
    });

    it('lets an admin override and assign a recycler before COLLECTED', async () => {
      const { service, repo } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(assignedRecord) }),
      );

      await service.assignRecycler(ADMIN, 'sub-2', 'recycler-1');

      expect(repo.assignRecycler).toHaveBeenCalledWith('sub-2', 'recycler-1');
    });
  });

  describe('startRecycling', () => {
    it('moves COLLECTED → RECYCLING and stamps the processing time', async () => {
      const clock = new Date('2026-07-22T09:00:00.000Z');
      const repo = buildRepo({ findById: jest.fn().mockResolvedValue(collectedRecord) });
      const service = createSubmissionService({
        submissions: repo,
        logger: createLogger({ logLevel: 'fatal', nodeEnv: 'test' }),
        rewards: buildRewardService(),
        now: () => clock,
      });

      const result = await service.startRecycling(RECYCLER, 'sub-5');

      expect(repo.updateRecyclerProcessing).toHaveBeenCalledWith('sub-5', clock);
      expect(result.status).toBe('RECYCLING');
    });

    it('throws NotFoundError for a recycler who is not the assignee', async () => {
      const { service, repo } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(collectedRecord) }),
      );

      await expect(service.startRecycling(OTHER_RECYCLER, 'sub-5')).rejects.toBeInstanceOf(
        NotFoundError,
      );
      expect(repo.updateRecyclerProcessing).not.toHaveBeenCalled();
    });

    it('throws ConflictError when the submission is not COLLECTED', async () => {
      const { service, repo } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(recyclingRecord) }),
      );

      await expect(service.startRecycling(RECYCLER, 'sub-6')).rejects.toBeInstanceOf(ConflictError);
      expect(repo.updateRecyclerProcessing).not.toHaveBeenCalled();
    });
  });

  describe('completeRecycling', () => {
    const completeInput = {
      recoveredWeight: 12.5,
      recyclerNotes: 'Separated lithium batteries.',
      materialRecovery: { plastic: 3.2, metal: 6.1, glass: 3.2 },
    };

    it('moves RECYCLING → RECYCLED and records the recovery outcome', async () => {
      const clock = new Date('2026-07-23T09:00:00.000Z');
      const repo = buildRepo({ findById: jest.fn().mockResolvedValue(recyclingRecord) });
      const service = createSubmissionService({
        submissions: repo,
        logger: createLogger({ logLevel: 'fatal', nodeEnv: 'test' }),
        rewards: buildRewardService(),
        now: () => clock,
      });

      const result = await service.completeRecycling(RECYCLER, 'sub-6', completeInput);

      expect(repo.updateRecyclerCompletion).toHaveBeenCalledWith('sub-6', clock, {
        recoveredWeight: 12.5,
        recyclerNotes: 'Separated lithium batteries.',
        materialRecovery: { plastic: 3.2, metal: 6.1, glass: 3.2 },
      });
      expect(result.submission.status).toBe('RECYCLED');
      expect(result.reward.greenCoinsAwarded).toBeGreaterThan(0);
    });

    it('accepts a completion without notes or material breakdown', async () => {
      const repo = buildRepo({ findById: jest.fn().mockResolvedValue(recyclingRecord) });
      const { service } = buildService(repo);

      await service.completeRecycling(RECYCLER, 'sub-6', { recoveredWeight: 5 });

      expect(repo.updateRecyclerCompletion).toHaveBeenCalledWith(
        'sub-6',
        expect.any(Date),
        expect.objectContaining({ recoveredWeight: 5 }),
      );
    });

    it('throws NotFoundError for a recycler who is not the assignee', async () => {
      const { service } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(recyclingRecord) }),
      );

      await expect(
        service.completeRecycling(OTHER_RECYCLER, 'sub-6', completeInput),
      ).rejects.toBeInstanceOf(NotFoundError);
    });

    it('throws ConflictError when the submission is not RECYCLING', async () => {
      const { service, repo } = buildService(
        buildRepo({ findById: jest.fn().mockResolvedValue(collectedRecord) }),
      );

      await expect(
        service.completeRecycling(RECYCLER, 'sub-5', completeInput),
      ).rejects.toBeInstanceOf(ConflictError);
      expect(repo.updateRecyclerCompletion).not.toHaveBeenCalled();
    });
  });

  describe('getRecyclerDashboard', () => {
    it('returns the active assignments for the authenticated recycler', async () => {
      const { service, repo } = buildService();

      const result = await service.getRecyclerDashboard(RECYCLER);

      expect(repo.findRecyclerAssignments).toHaveBeenCalledWith('recycler-1', undefined);
      expect(result).toHaveLength(1);
    });
  });
});
