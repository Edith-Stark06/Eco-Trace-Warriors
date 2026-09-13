import { createAnalyticsService } from '@modules/analytics';
import type {
  AnalyticsRepository,
  AnalyticsServiceDeps,
  DailyWeightObservation,
  EnvironmentalImpactTotals,
  RegionalAggregateRow,
  SubmissionStatusCounts,
  UserCounts,
  WeightTotals,
} from '@modules/analytics';
import { createLogger } from '@shared/logging';

const logger = createLogger({ logLevel: 'fatal', nodeEnv: 'test' });

/** Default deps for createAnalyticsService; override per-test as needed. */
function serviceDeps(
  overrides: { analytics?: AnalyticsRepository; fetchImpl?: typeof fetch } = {},
): AnalyticsServiceDeps {
  return {
    analytics: overrides.analytics ?? fakeRepository(),
    logger,
    deviceAiServiceUrl: 'http://device-ai.test:8100',
    deviceAiTimeoutMs: 5000,
    fetchImpl: overrides.fetchImpl,
  };
}

function fakeRepository(overrides: Partial<AnalyticsRepository> = {}): AnalyticsRepository {
  const statusCounts: SubmissionStatusCounts = {
    total: 10,
    pending: 2,
    inProgress: 3,
    collected: 1,
    recycled: 4,
  };
  const weightTotals: WeightTotals = { estimatedWeight: 25, recoveredWeight: 18 };
  const userCounts: UserCounts = { total: 12, collectors: 3, recyclers: 2 };
  const impactTotals: EnvironmentalImpactTotals = {
    co2Saved: 62.5,
    energySaved: 37.5,
    landfillDiverted: 2.5,
  };
  const regions: RegionalAggregateRow[] = [
    {
      region: 'Bengaluru',
      totalSubmissions: 4,
      totalWeight: 10,
      recycledWeight: 6,
      activeCollectors: 2,
      activeRecyclers: 1,
    },
  ];
  const dailySeries: DailyWeightObservation[] = [
    { date: '2026-08-01', weightKg: 5 },
    { date: '2026-08-02', weightKg: 7 },
  ];

  return {
    getSubmissionStatusCounts: jest.fn().mockResolvedValue(statusCounts),
    getWeightTotals: jest.fn().mockResolvedValue(weightTotals),
    getUserCounts: jest.fn().mockResolvedValue(userCounts),
    getTotalRewardPoints: jest.fn().mockResolvedValue(340),
    getEnvironmentalImpactTotals: jest.fn().mockResolvedValue(impactTotals),
    getRegionalBreakdown: jest.fn().mockResolvedValue(regions),
    getDailyRecycledWeightSeries: jest.fn().mockResolvedValue(dailySeries),
    ...overrides,
  };
}

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

describe('AnalyticsService', () => {
  it('assembles the national overview from real repository aggregates', async () => {
    const service = createAnalyticsService(serviceDeps());
    const overview = await service.getOverview();

    expect(overview).toMatchObject({
      totalSubmissions: 10,
      pendingSubmissions: 2,
      inProgressSubmissions: 3,
      collectedSubmissions: 1,
      recycledSubmissions: 4,
      totalUsers: 12,
      totalCollectors: 3,
      totalRecyclers: 2,
      totalEstimatedWeight: 25,
      totalRecoveredWeight: 18,
      totalRewardsIssued: 340,
      weightUnit: 'kg',
    });
    expect(typeof overview.generatedAt).toBe('string');
  });

  it('never fabricates state/lat/long for the regional breakdown', async () => {
    const service = createAnalyticsService(serviceDeps());
    const breakdown = await service.getRegionalBreakdown();

    expect(breakdown.regions).toHaveLength(1);
    expect(breakdown.regions[0]).toMatchObject({
      region: 'Bengaluru',
      state: null,
      totalSubmissions: 4,
      totalWeight: 10,
      recycledWeight: 6,
      activeCollectors: 2,
      activeRecyclers: 1,
      latitude: null,
      longitude: null,
    });
  });

  it('reports treesEquivalent as null rather than an invented conversion', async () => {
    const service = createAnalyticsService(serviceDeps());
    const impact = await service.getEnvironmentalImpact();

    expect(impact).toMatchObject({
      co2Saved: 62.5,
      energySaved: 37.5,
      landfillDiverted: 2.5,
      co2Unit: 'kg',
      energyUnit: 'kWh',
      landfillUnit: 'kg',
      treesEquivalent: null,
    });
  });

  it('maps a TRAINED forecast from device_ai into the DemandForecast contract', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(
      jsonResponse(200, {
        success: true,
        status: 'TRAINED',
        points: [{ date: '2026-08-03', predicted_weight_kg: 6.2 }],
        history: [{ date: '2026-08-02', actual_weight_kg: 7 }],
        evaluation: { rmse: 1.2, mae: 0.9, mape: 15.5, train_samples: 20, val_samples: 6 },
        model: { name: 'ewaste-forecast-lstm', version: '20260901120000' },
        history_days: 45,
        min_history_days_required: 30,
        lookback: 14,
        horizon: 1,
        reason: null,
      }),
    );
    const service = createAnalyticsService(serviceDeps({ fetchImpl }));

    const forecast = await service.getForecast(1);

    expect(forecast.status).toBe('OK');
    expect(forecast.model).toBe('ewaste-forecast-lstm:20260901120000');
    expect(forecast.points).toEqual([
      { period: '2026-08-03', predictedWeight: 6.2, predictedSubmissions: null, confidence: null },
    ]);
    expect(forecast.evaluation).toEqual({
      rmse: 1.2,
      mae: 0.9,
      mape: 15.5,
      trainSamples: 20,
      valSamples: 6,
    });
    expect(forecast.history).toEqual([{ period: '2026-08-02', actualWeight: 7 }]);
  });

  it('never fabricates a prediction when device_ai reports insufficient data', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(
      jsonResponse(200, {
        success: true,
        status: 'INSUFFICIENT_HISTORICAL_DATA',
        points: [],
        history: [],
        evaluation: null,
        model: null,
        history_days: 5,
        min_history_days_required: 30,
        lookback: 14,
        horizon: 30,
        reason: 'Only 5 day(s) of historical data are available.',
      }),
    );
    const service = createAnalyticsService(serviceDeps({ fetchImpl }));

    const forecast = await service.getForecast(30);

    expect(forecast.status).toBe('INSUFFICIENT_HISTORICAL_DATA');
    expect(forecast.points).toEqual([]);
    expect(forecast.model).toBeNull();
    expect(forecast.reason).toContain('Only 5 day(s)');
  });

  it('degrades to SERVICE_UNAVAILABLE without throwing when device_ai is unreachable', async () => {
    const fetchImpl = jest.fn().mockRejectedValue(new Error('ECONNREFUSED'));
    const service = createAnalyticsService(serviceDeps({ fetchImpl }));

    const forecast = await service.getForecast(30);

    expect(forecast.status).toBe('SERVICE_UNAVAILABLE');
    expect(forecast.points).toEqual([]);
    expect(forecast.model).toBeNull();
    expect(forecast.reason).toMatch(/could not reach/i);
  });

  it('degrades to SERVICE_UNAVAILABLE on a non-OK response from device_ai', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(jsonResponse(500, { detail: 'boom' }));
    const service = createAnalyticsService(serviceDeps({ fetchImpl }));

    const forecast = await service.getForecast(30);

    expect(forecast.status).toBe('SERVICE_UNAVAILABLE');
    expect(forecast.reason).toContain('HTTP 500');
  });

  it('sends the real aggregated daily series and requested horizon to device_ai', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(
      jsonResponse(200, {
        success: true,
        status: 'INSUFFICIENT_HISTORICAL_DATA',
        points: [],
        history: [],
        evaluation: null,
        model: null,
        history_days: 2,
        min_history_days_required: 30,
        lookback: 14,
        horizon: 45,
        reason: 'not enough data',
      }),
    );
    const service = createAnalyticsService(serviceDeps({ fetchImpl }));

    await service.getForecast(45);

    expect(fetchImpl).toHaveBeenCalledWith(
      'http://device-ai.test:8100/forecast/ewaste',
      expect.objectContaining({ method: 'POST' }),
    );
    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    const sentBody = JSON.parse(init.body as string) as {
      observations: unknown[];
      horizon: number;
    };
    expect(sentBody.horizon).toBe(45);
    expect(sentBody.observations).toEqual([
      { date: '2026-08-01', weight_kg: 5 },
      { date: '2026-08-02', weight_kg: 7 },
    ]);
  });
});
