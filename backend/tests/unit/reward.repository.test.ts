import type { PrismaClient } from '@prisma/client';
import { RewardReason } from '@prisma/client';
import { createRewardRepository } from '@modules/rewards';
import type { RewardRepository } from '@modules/rewards';

/**
 * Unit tests for the Prisma-backed RewardRepository. Prisma is mocked so these
 * run without a database. They lock the select projections, argument shapes,
 * and the composition of executeRewardTransaction (including rollback when any
 * step inside the transaction throws).
 */

interface MockTx {
  rewardTransaction: { create: jest.Mock };
  user: { update: jest.Mock };
  submission: { update: jest.Mock };
}

interface MockPrisma {
  rewardTransaction: { create: jest.Mock; findUnique: jest.Mock; findMany: jest.Mock };
  user: { findUniqueOrThrow: jest.Mock; update: jest.Mock };
  submission: { update: jest.Mock };
  $transaction: jest.Mock;
  __tx: MockTx;
}

function mockPrisma(): MockPrisma {
  const tx: MockTx = {
    rewardTransaction: { create: jest.fn() },
    user: { update: jest.fn() },
    submission: { update: jest.fn() },
  };

  return {
    rewardTransaction: {
      create: jest.fn(),
      findUnique: jest.fn(),
      findMany: jest.fn(),
    },
    user: {
      findUniqueOrThrow: jest.fn(),
      update: jest.fn(),
    },
    submission: {
      update: jest.fn(),
    },
    // Mirrors prisma.$transaction(fn): runs the callback with the tx client and
    // propagates any rejection (which, in real Prisma, triggers a rollback).
    $transaction: jest.fn((fn: (client: MockTx) => Promise<unknown>) => fn(tx)),
    __tx: tx,
  };
}

function buildRepo(prisma: MockPrisma): RewardRepository {
  return createRewardRepository({ prisma: prisma as unknown as PrismaClient });
}

describe('RewardRepository.createRewardTransaction', () => {
  it('calls prisma.rewardTransaction.create with the correct data and select', async () => {
    const prisma = mockPrisma();
    const repo = buildRepo(prisma);
    const record = {
      id: 'reward-1',
      userId: 'user-1',
      submissionId: 'sub-1',
      points: 110,
      reason: RewardReason.RECYCLING,
      createdAt: new Date(),
    };
    prisma.rewardTransaction.create.mockResolvedValue(record);

    const result = await repo.createRewardTransaction({
      userId: 'user-1',
      submissionId: 'sub-1',
      points: 110,
      reason: RewardReason.RECYCLING,
    });

    expect(prisma.rewardTransaction.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: {
          userId: 'user-1',
          submissionId: 'sub-1',
          points: 110,
          reason: RewardReason.RECYCLING,
        },
      }),
    );
    expect(result).toEqual(record);
  });
});

describe('RewardRepository.findRewardBySubmissionId', () => {
  it('returns the reward transaction when found', async () => {
    const prisma = mockPrisma();
    const repo = buildRepo(prisma);
    const record = {
      id: 'reward-1',
      userId: 'user-1',
      submissionId: 'sub-1',
      points: 110,
      reason: RewardReason.RECYCLING,
      createdAt: new Date(),
    };
    prisma.rewardTransaction.findUnique.mockResolvedValue(record);

    const result = await repo.findRewardBySubmissionId('sub-1');

    expect(prisma.rewardTransaction.findUnique).toHaveBeenCalledWith(
      expect.objectContaining({ where: { submissionId: 'sub-1' } }),
    );
    expect(result).toEqual(record);
  });

  it('returns null when no reward exists for the submission', async () => {
    const prisma = mockPrisma();
    const repo = buildRepo(prisma);
    prisma.rewardTransaction.findUnique.mockResolvedValue(null);

    const result = await repo.findRewardBySubmissionId('missing');

    expect(result).toBeNull();
  });
});

describe('RewardRepository.findRewardHistoryByUserId', () => {
  it('returns the reward history ordered by createdAt desc', async () => {
    const prisma = mockPrisma();
    const repo = buildRepo(prisma);
    const history = [
      {
        id: 'reward-2',
        userId: 'user-1',
        submissionId: 'sub-2',
        points: 60,
        reason: RewardReason.RECYCLING,
        createdAt: new Date('2026-07-24T00:00:00.000Z'),
        submission: {
          id: 'sub-2',
          category: 'Mobile',
          status: 'RECYCLED',
          estimatedWeight: 1,
          createdAt: new Date(),
        },
      },
    ];
    prisma.rewardTransaction.findMany.mockResolvedValue(history);

    const result = await repo.findRewardHistoryByUserId('user-1');

    expect(prisma.rewardTransaction.findMany).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { userId: 'user-1' },
        orderBy: { createdAt: 'desc' },
      }),
    );
    expect(result).toEqual(history);
  });

  it('returns an empty array when the user has no history', async () => {
    const prisma = mockPrisma();
    const repo = buildRepo(prisma);
    prisma.rewardTransaction.findMany.mockResolvedValue([]);

    const result = await repo.findRewardHistoryByUserId('user-1');

    expect(result).toEqual([]);
  });
});

describe('RewardRepository.getUserGreenCoins', () => {
  it('returns the greenCoins projection for the user', async () => {
    const prisma = mockPrisma();
    const repo = buildRepo(prisma);
    prisma.user.findUniqueOrThrow.mockResolvedValue({ id: 'user-1', greenCoins: 250 });

    const result = await repo.getUserGreenCoins('user-1');

    expect(prisma.user.findUniqueOrThrow).toHaveBeenCalledWith(
      expect.objectContaining({ where: { id: 'user-1' } }),
    );
    expect(result).toEqual({ id: 'user-1', greenCoins: 250 });
  });
});

describe('RewardRepository.incrementUserGreenCoins', () => {
  it('increments the user greenCoins by the given points', async () => {
    const prisma = mockPrisma();
    const repo = buildRepo(prisma);
    prisma.user.update.mockResolvedValue({ id: 'user-1', greenCoins: 360 });

    const result = await repo.incrementUserGreenCoins('user-1', 110);

    expect(prisma.user.update).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: 'user-1' },
        data: { greenCoins: { increment: 110 } },
      }),
    );
    expect(result.greenCoins).toBe(360);
  });
});

describe('RewardRepository.markSubmissionRewardIssued', () => {
  it('marks the submission rewarded and stores the sustainability metrics', async () => {
    const prisma = mockPrisma();
    const repo = buildRepo(prisma);
    prisma.submission.update.mockResolvedValue({
      id: 'sub-1',
      rewardIssued: true,
      co2Saved: 50,
      energySaved: 30,
      landfillDiverted: 2,
    });

    const result = await repo.markSubmissionRewardIssued('sub-1', {
      co2Saved: 50,
      energySaved: 30,
      landfillDiverted: 2,
    });

    expect(prisma.submission.update).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: 'sub-1' },
        data: expect.objectContaining({ rewardIssued: true, co2Saved: 50 }),
      }),
    );
    expect(result.rewardIssued).toBe(true);
  });

  it('coerces omitted metrics to null', async () => {
    const prisma = mockPrisma();
    const repo = buildRepo(prisma);
    prisma.submission.update.mockResolvedValue({
      id: 'sub-1',
      rewardIssued: true,
      co2Saved: null,
      energySaved: null,
      landfillDiverted: null,
    });

    await repo.markSubmissionRewardIssued('sub-1', {});

    expect(prisma.submission.update).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          co2Saved: null,
          energySaved: null,
          landfillDiverted: null,
        }),
      }),
    );
  });
});

describe('RewardRepository.executeRewardTransaction', () => {
  it('runs all three writes inside a single $transaction call', async () => {
    const prisma = mockPrisma();
    const repo = buildRepo(prisma);
    const { __tx: tx } = prisma;

    tx.rewardTransaction.create.mockResolvedValue({
      id: 'reward-1',
      userId: 'user-1',
      submissionId: 'sub-1',
      points: 110,
      reason: RewardReason.RECYCLING,
      createdAt: new Date(),
    });
    tx.user.update.mockResolvedValue({ id: 'user-1', greenCoins: 110 });
    tx.submission.update.mockResolvedValue({
      id: 'sub-1',
      rewardIssued: true,
      co2Saved: 50,
      energySaved: 30,
      landfillDiverted: 2,
    });

    const result = await repo.executeRewardTransaction(
      'user-1',
      'sub-1',
      110,
      RewardReason.RECYCLING,
      { co2Saved: 50, energySaved: 30, landfillDiverted: 2 },
    );

    expect(prisma.$transaction).toHaveBeenCalledTimes(1);
    expect(tx.rewardTransaction.create).toHaveBeenCalledWith(
      expect.objectContaining({ data: expect.objectContaining({ userId: 'user-1', points: 110 }) }),
    );
    expect(tx.user.update).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: 'user-1' },
        data: { greenCoins: { increment: 110 } },
      }),
    );
    expect(tx.submission.update).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: 'sub-1' },
        data: expect.objectContaining({ rewardIssued: true, co2Saved: 50 }),
      }),
    );
    expect(result.reward.points).toBe(110);
    expect(result.user.greenCoins).toBe(110);
    expect(result.submission.rewardIssued).toBe(true);
  });

  it('propagates a rejection from inside the transaction (simulates rollback)', async () => {
    const prisma = mockPrisma();
    const repo = buildRepo(prisma);
    const { __tx: tx } = prisma;

    tx.rewardTransaction.create.mockResolvedValue({
      id: 'reward-1',
      userId: 'user-1',
      submissionId: 'sub-1',
      points: 110,
      reason: RewardReason.RECYCLING,
      createdAt: new Date(),
    });
    // user.update fails — simulates a DB constraint violation mid-transaction
    tx.user.update.mockRejectedValue(new Error('Unique constraint failed'));

    await expect(
      repo.executeRewardTransaction('user-1', 'sub-1', 110, RewardReason.RECYCLING, {}),
    ).rejects.toThrow('Unique constraint failed');

    // submission.update must never have been called after the failure
    expect(tx.submission.update).not.toHaveBeenCalled();
  });

  it('stores null for optional sustainability metrics when they are omitted', async () => {
    const prisma = mockPrisma();
    const repo = buildRepo(prisma);
    const { __tx: tx } = prisma;

    tx.rewardTransaction.create.mockResolvedValue({
      id: 'reward-1',
      userId: 'user-1',
      submissionId: 'sub-1',
      points: 25,
      reason: RewardReason.RECYCLING,
      createdAt: new Date(),
    });
    tx.user.update.mockResolvedValue({ id: 'user-1', greenCoins: 25 });
    tx.submission.update.mockResolvedValue({
      id: 'sub-1',
      rewardIssued: true,
      co2Saved: null,
      energySaved: null,
      landfillDiverted: null,
    });

    await repo.executeRewardTransaction('user-1', 'sub-1', 25, RewardReason.RECYCLING, {});

    expect(tx.submission.update).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          co2Saved: null,
          energySaved: null,
          landfillDiverted: null,
        }),
      }),
    );
  });
});
