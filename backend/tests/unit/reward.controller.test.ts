/* eslint-disable @typescript-eslint/unbound-method -- jest.fn() mocks carry no `this`; referencing them in expect() is safe */
import type { Request, Response } from 'express';
import { RewardReason } from '@prisma/client';
import { createRewardController } from '@modules/rewards';
import type { RewardService } from '@modules/rewards';

const rewardSummary = {
  rewardTransaction: {
    id: 'reward-1',
    submissionId: 'sub-1',
    points: 110,
    reason: RewardReason.RECYCLING,
    createdAt: '2026-07-24T00:00:00.000Z',
  },
  greenCoinsAwarded: 110,
  updatedBalance: 110,
  sustainability: {
    co2Saved: 50,
    energySaved: 30,
    landfillDiverted: 2,
    co2Unit: 'kg' as const,
    energyUnit: 'kWh' as const,
    landfillUnit: 'kg' as const,
  },
};

function buildService(overrides: Partial<RewardService> = {}): jest.Mocked<RewardService> {
  return {
    issueReward: jest.fn().mockResolvedValue(rewardSummary),
    getRewardHistory: jest.fn().mockResolvedValue([]),
    getBalance: jest.fn().mockResolvedValue({
      greenCoins: 110,
      totalRewards: 110,
      totalCO2Saved: 50,
      totalEnergySaved: 30,
      totalLandfillDiverted: 2,
    }),
    calculateRewardPoints: jest.fn().mockReturnValue(110),
    calculateEnvironmentalImpact: jest.fn(),
    ...overrides,
  } as jest.Mocked<RewardService>;
}

function buildRes(): jest.Mocked<Response> {
  const res = {} as jest.Mocked<Response>;
  res.status = jest.fn().mockReturnValue(res);
  res.json = jest.fn().mockReturnValue(res);
  return res;
}

function buildReq(overrides: Partial<Request> = {}): Request {
  return {
    params: {},
    body: {},
    user: { userId: 'user-1', email: 'user-1@example.com', role: 'CONSUMER' },
    ...overrides,
  } as unknown as Request;
}

describe('RewardController.issueReward', () => {
  it('returns 201 with the reward summary', async () => {
    const service = buildService();
    const controller = createRewardController(service);
    const req = buildReq({ params: { submissionId: 'sub-1' } });
    const res = buildRes();

    await controller.issueReward(req, res);

    expect(service.issueReward).toHaveBeenCalledWith('sub-1');
    expect(res.status).toHaveBeenCalledWith(201);
    expect(res.json).toHaveBeenCalledWith({ success: true, data: rewardSummary });
  });
});

describe('RewardController.getRewardHistory', () => {
  it('returns 200 with the reward history for the authenticated user', async () => {
    const service = buildService();
    const controller = createRewardController(service);
    const req = buildReq();
    const res = buildRes();

    await controller.getRewardHistory(req, res);

    expect(service.getRewardHistory).toHaveBeenCalledWith('user-1');
    expect(res.status).toHaveBeenCalledWith(200);
    expect(res.json).toHaveBeenCalledWith({ success: true, data: [] });
  });
});

describe('RewardController.getBalance', () => {
  it('returns 200 with the balance for the authenticated user', async () => {
    const service = buildService();
    const controller = createRewardController(service);
    const req = buildReq();
    const res = buildRes();

    await controller.getBalance(req, res);

    expect(service.getBalance).toHaveBeenCalledWith('user-1');
    expect(res.status).toHaveBeenCalledWith(200);
    expect(res.json).toHaveBeenCalledWith({
      success: true,
      data: expect.objectContaining({ greenCoins: 110 }),
    });
  });
});
