/* eslint-disable @typescript-eslint/unbound-method -- jest.fn() mocks carry no `this`; referencing them in expect() is safe */
import { RewardReason } from '@prisma/client';
import { createRewardService } from '@modules/rewards';
import type {
  RewardRepository,
  RewardService,
  RewardTransactionResult,
  RewardTransactionWithSubmission,
} from '@modules/rewards';
import type { SubmissionRecord, SubmissionRepository } from '@modules/submission';
import { ConflictError, NotFoundError } from '@shared/errors';
import { createLogger } from '@shared/logging';

const logger = createLogger({ logLevel: 'fatal', nodeEnv: 'test' });

/** Builds a full RECYCLED submission record; override any field per test. */
function submission(overrides: Partial<SubmissionRecord> = {}): SubmissionRecord {
  return {
    id: 'sub-1',
    userId: 'user-1',
    category: 'Laptop',
    description: null,
    estimatedWeight: 2,
    address: '12 MG Road, Bengaluru',
    latitude: 12.9716,
    longitude: 77.5946,
    imageUrls: [],
    status: 'RECYCLED',
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
    ...overrides,
  };
}

/** A submission repository stub exposing only findById (all the service reads). */
function subRepo(record: SubmissionRecord | null): SubmissionRepository {
  return { findById: jest.fn().mockResolvedValue(record) } as unknown as SubmissionRepository;
}

/** A reward repository mock with a working executeRewardTransaction by default. */
function rewardRepo(overrides: Partial<RewardRepository> = {}): jest.Mocked<RewardRepository> {
  return {
    createRewardTransaction: jest.fn(),
    findRewardBySubmissionId: jest.fn().mockResolvedValue(null),
    findRewardHistoryByUserId: jest.fn().mockResolvedValue([]),
    getUserGreenCoins: jest.fn().mockResolvedValue({ id: 'user-1', greenCoins: 0 }),
    incrementUserGreenCoins: jest.fn(),
    markSubmissionRewardIssued: jest.fn(),
    executeRewardTransaction: jest
      .fn()
      .mockImplementation(
        (userId: string, submissionId: string, points: number): Promise<RewardTransactionResult> =>
          Promise.resolve({
            reward: {
              id: 'reward-1',
              userId,
              submissionId,
              points,
              reason: RewardReason.RECYCLING,
              createdAt: new Date('2026-07-24T00:00:00.000Z'),
            },
            user: { id: userId, greenCoins: points },
            submission: {
              id: submissionId,
              rewardIssued: true,
              co2Saved: null,
              energySaved: null,
              landfillDiverted: null,
            },
          }),
      ),
    ...overrides,
  } as jest.Mocked<RewardRepository>;
}

function buildService(
  record: SubmissionRecord | null = submission(),
  rewards: jest.Mocked<RewardRepository> = rewardRepo(),
): { service: RewardService; rewards: jest.Mocked<RewardRepository> } {
  const service = createRewardService({ rewards, submissions: subRepo(record), logger });
  return { service, rewards };
}

describe('RewardService.calculateRewardPoints', () => {
  it('returns the correct base reward for every known device category', () => {
    const { service } = buildService();
    // weight 0 isolates the base points from the weight bonus
    expect(service.calculateRewardPoints('Laptop', 0)).toBe(100);
    expect(service.calculateRewardPoints('Desktop', 0)).toBe(150);
    expect(service.calculateRewardPoints('Mobile', 0)).toBe(50);
    expect(service.calculateRewardPoints('Tablet', 0)).toBe(60);
    expect(service.calculateRewardPoints('Monitor', 0)).toBe(70);
    expect(service.calculateRewardPoints('Printer', 0)).toBe(80);
  });

  it('falls back to the default base reward for an unknown category', () => {
    const { service } = buildService();
    expect(service.calculateRewardPoints('Unknown', 0)).toBe(25);
    expect(service.calculateRewardPoints('Toaster', 0)).toBe(25);
  });

  it('is case-insensitive and trims the category', () => {
    const { service } = buildService();
    expect(service.calculateRewardPoints('  laptop  ', 0)).toBe(100);
    expect(service.calculateRewardPoints('MoBiLe', 0)).toBe(50);
  });

  describe('weight bonus (5 GreenCoins per kg, rounded)', () => {
    it.each([
      [0, 100],
      [0.5, 103], // 0.5 * 5 = 2.5 → rounds to 3 (round half up)
      [1, 105],
      [2, 110],
      [5, 125],
      [10, 150],
      [1000, 5100], // large weight: 1000 * 5 = 5000 bonus
    ])('adds the weight bonus for %d kg → %d points (Laptop base 100)', (weight, expected) => {
      const { service } = buildService();
      expect(service.calculateRewardPoints('Laptop', weight)).toBe(expected);
    });

    it('rounds the weight bonus to the nearest whole GreenCoin', () => {
      const { service } = buildService();
      // 0.1 * 5 = 0.5 → rounds to 1; 0.14 * 5 = 0.7 → rounds to 1; 0.05 * 5 = 0.25 → rounds to 0
      expect(service.calculateRewardPoints('Mobile', 0.1)).toBe(51);
      expect(service.calculateRewardPoints('Mobile', 0.14)).toBe(51);
      expect(service.calculateRewardPoints('Mobile', 0.05)).toBe(50);
    });
  });
});

describe('RewardService.calculateEnvironmentalImpact', () => {
  it('computes CO₂, energy, and landfill for a Laptop', () => {
    const { service } = buildService();
    const impact = service.calculateEnvironmentalImpact('Laptop', 2);
    expect(impact).toEqual({
      co2Saved: 50, // 2 * 25
      energySaved: 30, // 2 * 15
      landfillDiverted: 2, // 2 * 1
      co2Unit: 'kg',
      energyUnit: 'kWh',
      landfillUnit: 'kg',
    });
  });

  it('computes impact for a Mobile', () => {
    const { service } = buildService();
    const impact = service.calculateEnvironmentalImpact('Mobile', 0.5);
    expect(impact.co2Saved).toBeCloseTo(6); // 0.5 * 12
    expect(impact.energySaved).toBeCloseTo(4); // 0.5 * 8
    expect(impact.landfillDiverted).toBeCloseTo(0.5); // 0.5 * 1
  });

  it('computes impact for a Desktop', () => {
    const { service } = buildService();
    const impact = service.calculateEnvironmentalImpact('Desktop', 10);
    expect(impact.co2Saved).toBe(300); // 10 * 30
    expect(impact.energySaved).toBe(180); // 10 * 18
    expect(impact.landfillDiverted).toBe(10); // 10 * 1
  });

  it('uses conservative default factors for an unknown category', () => {
    const { service } = buildService();
    const impact = service.calculateEnvironmentalImpact('Printer', 3);
    // Printer is not in IMPACT_MAP → default { co2:10, energy:6, landfill:1 }
    expect(impact.co2Saved).toBe(30);
    expect(impact.energySaved).toBe(18);
    expect(impact.landfillDiverted).toBe(3);
  });

  it('returns zero impact for zero weight', () => {
    const { service } = buildService();
    const impact = service.calculateEnvironmentalImpact('Laptop', 0);
    expect(impact.co2Saved).toBe(0);
    expect(impact.energySaved).toBe(0);
    expect(impact.landfillDiverted).toBe(0);
  });

  it('always attaches the correct measurement units', () => {
    const { service } = buildService();
    const impact = service.calculateEnvironmentalImpact('Anything', 1);
    expect(impact.co2Unit).toBe('kg');
    expect(impact.energyUnit).toBe('kWh');
    expect(impact.landfillUnit).toBe('kg');
  });
});

describe('RewardService.issueReward', () => {
  it('issues a reward for a RECYCLED submission and returns the summary', async () => {
    const record = submission({ category: 'Laptop', estimatedWeight: 2, userId: 'user-1' });
    const { service, rewards } = buildService(record);

    const result = await service.issueReward('sub-1');

    // points = base 100 (Laptop) + round(2 * 5) = 110
    expect(rewards.executeRewardTransaction).toHaveBeenCalledWith(
      'user-1',
      'sub-1',
      110,
      RewardReason.RECYCLING,
      { co2Saved: 50, energySaved: 30, landfillDiverted: 2 },
    );
    expect(result.greenCoinsAwarded).toBe(110);
    expect(result.updatedBalance).toBe(110);
    expect(result.rewardTransaction).toEqual(
      expect.objectContaining({ id: 'reward-1', submissionId: 'sub-1', points: 110 }),
    );
    expect(result.sustainability.co2Saved).toBe(50);
  });

  it('serializes the reward transaction createdAt to an ISO string', async () => {
    const { service } = buildService();
    const result = await service.issueReward('sub-1');
    expect(result.rewardTransaction.createdAt).toBe('2026-07-24T00:00:00.000Z');
  });

  it('throws NotFoundError when the submission does not exist', async () => {
    const { service, rewards } = buildService(null);

    await expect(service.issueReward('missing')).rejects.toBeInstanceOf(NotFoundError);
    expect(rewards.executeRewardTransaction).not.toHaveBeenCalled();
  });

  it.each(['PENDING', 'ASSIGNED', 'ACCEPTED', 'IN_PROGRESS', 'COLLECTED', 'RECYCLING', 'REJECTED'])(
    'throws ConflictError when the submission status is %s (not RECYCLED)',
    async (status) => {
      const record = submission({ status: status as SubmissionRecord['status'] });
      const { service, rewards } = buildService(record);

      await expect(service.issueReward('sub-1')).rejects.toBeInstanceOf(ConflictError);
      expect(rewards.findRewardBySubmissionId).not.toHaveBeenCalled();
      expect(rewards.executeRewardTransaction).not.toHaveBeenCalled();
    },
  );

  it('throws ConflictError when a reward already exists for the submission', async () => {
    const rewards = rewardRepo({
      findRewardBySubmissionId: jest.fn().mockResolvedValue({
        id: 'reward-existing',
        userId: 'user-1',
        submissionId: 'sub-1',
        points: 110,
        reason: RewardReason.RECYCLING,
        createdAt: new Date('2026-07-23T00:00:00.000Z'),
      }),
    });
    const { service } = buildService(submission(), rewards);

    await expect(service.issueReward('sub-1')).rejects.toBeInstanceOf(ConflictError);
    expect(rewards.executeRewardTransaction).not.toHaveBeenCalled();
  });

  it('wraps a repository transaction failure in a ConflictError', async () => {
    const rewards = rewardRepo({
      executeRewardTransaction: jest.fn().mockRejectedValue(new Error('DB write failed')),
    });
    const { service } = buildService(submission(), rewards);

    await expect(service.issueReward('sub-1')).rejects.toBeInstanceOf(ConflictError);
  });
});

describe('RewardService.getRewardHistory', () => {
  it('delegates to the repository and returns the history', async () => {
    const history: RewardTransactionWithSubmission[] = [
      {
        id: 'reward-1',
        userId: 'user-1',
        submissionId: 'sub-1',
        points: 110,
        reason: RewardReason.RECYCLING,
        createdAt: new Date('2026-07-24T00:00:00.000Z'),
        submission: {
          id: 'sub-1',
          category: 'Laptop',
          status: 'RECYCLED',
          estimatedWeight: 2,
          createdAt: new Date('2026-07-20T00:00:00.000Z'),
        },
      },
    ];
    const rewards = rewardRepo({
      findRewardHistoryByUserId: jest.fn().mockResolvedValue(history),
    });
    const { service } = buildService(submission(), rewards);

    const result = await service.getRewardHistory('user-1');

    expect(rewards.findRewardHistoryByUserId).toHaveBeenCalledWith('user-1', undefined);
    expect(result).toEqual(history);
  });
});

describe('RewardService.getBalance', () => {
  it('aggregates GreenCoins and cumulative sustainability metrics from history', async () => {
    const history: RewardTransactionWithSubmission[] = [
      {
        id: 'reward-1',
        userId: 'user-1',
        submissionId: 'sub-1',
        points: 110,
        reason: RewardReason.RECYCLING,
        createdAt: new Date('2026-07-24T00:00:00.000Z'),
        submission: {
          id: 'sub-1',
          category: 'Laptop',
          status: 'RECYCLED',
          estimatedWeight: 2, // Laptop: co2 25, energy 15, landfill 1
          createdAt: new Date('2026-07-20T00:00:00.000Z'),
        },
      },
      {
        id: 'reward-2',
        userId: 'user-1',
        submissionId: 'sub-2',
        points: 60,
        reason: RewardReason.RECYCLING,
        createdAt: new Date('2026-07-23T00:00:00.000Z'),
        submission: {
          id: 'sub-2',
          category: 'Mobile',
          status: 'RECYCLED',
          estimatedWeight: 1, // Mobile: co2 12, energy 8, landfill 1
          createdAt: new Date('2026-07-19T00:00:00.000Z'),
        },
      },
    ];
    const rewards = rewardRepo({
      getUserGreenCoins: jest.fn().mockResolvedValue({ id: 'user-1', greenCoins: 170 }),
      findRewardHistoryByUserId: jest.fn().mockResolvedValue(history),
    });
    const { service } = buildService(submission(), rewards);

    const balance = await service.getBalance('user-1');

    expect(balance.greenCoins).toBe(170);
    expect(balance.totalRewards).toBe(170); // 110 + 60
    expect(balance.totalCO2Saved).toBe(62); // 2*25 + 1*12
    expect(balance.totalEnergySaved).toBe(38); // 2*15 + 1*8
    expect(balance.totalLandfillDiverted).toBe(3); // 2*1 + 1*1
  });

  it('returns zeroed metrics when the user has no reward history', async () => {
    const rewards = rewardRepo({
      getUserGreenCoins: jest.fn().mockResolvedValue({ id: 'user-1', greenCoins: 0 }),
      findRewardHistoryByUserId: jest.fn().mockResolvedValue([]),
    });
    const { service } = buildService(submission(), rewards);

    const balance = await service.getBalance('user-1');

    expect(balance).toEqual({
      greenCoins: 0,
      totalRewards: 0,
      totalCO2Saved: 0,
      totalEnergySaved: 0,
      totalLandfillDiverted: 0,
    });
  });
});
