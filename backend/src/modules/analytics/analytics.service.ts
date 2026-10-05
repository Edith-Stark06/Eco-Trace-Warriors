import type { Logger } from '@shared/logging';
import type { AnalyticsRepository } from './analytics.repository';

/**
 * DTO shapes mirror frontend/src/types/analytics.ts exactly (that file was
 * written ahead of this backend module against the documented endpoint
 * descriptions in docs/engineering/05_API.md — see its header comment). This
 * service is the real implementation now shipping against that contract.
 */

export interface NationalOverview {
  readonly totalSubmissions: number;
  readonly pendingSubmissions: number;
  readonly inProgressSubmissions: number;
  readonly collectedSubmissions: number;
  readonly recycledSubmissions: number;
  readonly totalUsers: number;
  readonly totalCollectors: number;
  readonly totalRecyclers: number;
  readonly totalEstimatedWeight: number;
  readonly totalRecoveredWeight: number;
  readonly totalRewardsIssued: number;
  readonly weightUnit: 'kg';
  readonly generatedAt: string;
}

export interface RegionalStat {
  readonly region: string;
  readonly state: string | null;
  readonly totalSubmissions: number;
  readonly totalWeight: number;
  readonly recycledWeight: number;
  readonly activeCollectors: number;
  readonly activeRecyclers: number;
  readonly latitude: number | null;
  readonly longitude: number | null;
}

export interface RegionalBreakdown {
  readonly regions: RegionalStat[];
  readonly weightUnit: 'kg';
  readonly generatedAt: string;
}

export interface EnvironmentalImpact {
  readonly co2Saved: number;
  readonly energySaved: number;
  readonly landfillDiverted: number;
  readonly co2Unit: 'kg';
  readonly energyUnit: 'kWh';
  readonly landfillUnit: 'kg';
  readonly treesEquivalent: number | null;
  readonly generatedAt: string;
}

/** One predicted future day. */
export interface ForecastPoint {
  readonly period: string;
  readonly predictedWeight: number;
  /** Not modeled — see `ForecastEvaluation`/module docstring; always null. */
  readonly predictedSubmissions: number | null;
  /** No calibrated prediction interval is computed; always null (never fabricated). */
  readonly confidence: number | null;
}

/** One real historical day, for ACTUAL-vs-FORECAST display context. */
export interface ForecastHistoryPoint {
  readonly period: string;
  readonly actualWeight: number;
}

/** Real chronological-holdout regression metrics (never fabricated). */
export interface ForecastEvaluation {
  readonly rmse: number;
  readonly mae: number;
  readonly mape: number | null;
  readonly trainSamples: number;
  readonly valSamples: number;
}

export type ForecastResultStatus =
  'OK' | 'INSUFFICIENT_HISTORICAL_DATA' | 'MODEL_BACKEND_UNAVAILABLE' | 'SERVICE_UNAVAILABLE';

/**
 * AI demand forecast. `status`/`reason`/`historyDays`/`minHistoryDaysRequired`
 * /`evaluation`/`history` are additive fields beyond the original provisional
 * type (see frontend/src/types/analytics.ts) — every pre-existing field keeps
 * its shape, so this is backward compatible with the original contract.
 */
export interface DemandForecast {
  readonly horizon: string;
  readonly model: string | null;
  readonly points: ForecastPoint[];
  readonly weightUnit: 'kg';
  readonly generatedAt: string;
  readonly status: ForecastResultStatus;
  readonly reason: string | null;
  readonly historyDays: number;
  readonly minHistoryDaysRequired: number;
  readonly history: ForecastHistoryPoint[];
  readonly evaluation: ForecastEvaluation | null;
}

export interface AnalyticsServiceDeps {
  readonly analytics: AnalyticsRepository;
  readonly logger: Logger;
  /** Base URL of the Python intelligence/device_ai service (mirrors
   *  blockchain.service.ts's existing proxy-call pattern). */
  readonly deviceAiServiceUrl: string;
  /** Request timeout in milliseconds for the proxied forecast call. */
  readonly deviceAiTimeoutMs: number;
  /** Test seam: injectable fetch implementation. Defaults to global `fetch`. */
  readonly fetchImpl?: typeof fetch;
}

export interface AnalyticsService {
  getOverview(): Promise<NationalOverview>;
  getRegionalBreakdown(): Promise<RegionalBreakdown>;
  getEnvironmentalImpact(): Promise<EnvironmentalImpact>;
  /** AI demand forecast (GET /analytics/forecast). Never throws for a
   *  reachability failure — degrades to `status: 'SERVICE_UNAVAILABLE'`,
   *  matching this backend's "AI calls are advisory" degradation philosophy
   *  (infrastructure/ai/ai.client.ts, blockchain.service.ts). */
  getForecast(horizon: number): Promise<DemandForecast>;
}

/** Shape of device_ai's POST /forecast/ewaste response body (snake_case). */
interface ForecastEwasteResponse {
  readonly success: boolean;
  readonly status: 'TRAINED' | 'INSUFFICIENT_HISTORICAL_DATA' | 'MODEL_BACKEND_UNAVAILABLE';
  readonly points: ReadonlyArray<{ readonly date: string; readonly predicted_weight_kg: number }>;
  readonly history: ReadonlyArray<{ readonly date: string; readonly actual_weight_kg: number }>;
  readonly evaluation: {
    readonly rmse: number;
    readonly mae: number;
    readonly mape: number | null;
    readonly train_samples: number;
    readonly val_samples: number;
  } | null;
  readonly model: { readonly name: string; readonly version: string } | null;
  readonly history_days: number;
  readonly min_history_days_required: number;
  readonly lookback: number;
  readonly horizon: number;
  readonly reason: string | null;
}

function nowIso(): string {
  return new Date().toISOString();
}

/** Creates the analytics service. Framework-agnostic and fully unit-testable. */
export function createAnalyticsService(deps: AnalyticsServiceDeps): AnalyticsService {
  return {
    async getOverview(): Promise<NationalOverview> {
      const [statusCounts, weightTotals, userCounts, totalRewardsIssued] = await Promise.all([
        deps.analytics.getSubmissionStatusCounts(),
        deps.analytics.getWeightTotals(),
        deps.analytics.getUserCounts(),
        deps.analytics.getTotalRewardPoints(),
      ]);

      deps.logger.info(
        { totalSubmissions: statusCounts.total },
        'Government analytics overview requested',
      );

      return {
        totalSubmissions: statusCounts.total,
        pendingSubmissions: statusCounts.pending,
        inProgressSubmissions: statusCounts.inProgress,
        collectedSubmissions: statusCounts.collected,
        recycledSubmissions: statusCounts.recycled,
        totalUsers: userCounts.total,
        totalCollectors: userCounts.collectors,
        totalRecyclers: userCounts.recyclers,
        totalEstimatedWeight: weightTotals.estimatedWeight,
        totalRecoveredWeight: weightTotals.recoveredWeight,
        totalRewardsIssued,
        weightUnit: 'kg',
        generatedAt: nowIso(),
      };
    },

    async getRegionalBreakdown(): Promise<RegionalBreakdown> {
      const rows = await deps.analytics.getRegionalBreakdown();

      deps.logger.info({ regionCount: rows.length }, 'Government regional breakdown requested');

      return {
        regions: rows.map((row) => ({
          region: row.region,
          // No separate state field exists on the User model today (only a
          // single free-text `region`) — reported as null rather than
          // guessed/parsed from free text, per the "no fabricated values"
          // rule. Same for lat/long: no per-region coordinate exists yet.
          state: null,
          totalSubmissions: row.totalSubmissions,
          totalWeight: row.totalWeight,
          recycledWeight: row.recycledWeight,
          activeCollectors: row.activeCollectors,
          activeRecyclers: row.activeRecyclers,
          latitude: null,
          longitude: null,
        })),
        weightUnit: 'kg',
        generatedAt: nowIso(),
      };
    },

    async getEnvironmentalImpact(): Promise<EnvironmentalImpact> {
      const totals = await deps.analytics.getEnvironmentalImpactTotals();

      deps.logger.info({ co2Saved: totals.co2Saved }, 'Government environmental impact requested');

      return {
        co2Saved: totals.co2Saved,
        energySaved: totals.energySaved,
        landfillDiverted: totals.landfillDiverted,
        co2Unit: 'kg',
        energyUnit: 'kWh',
        landfillUnit: 'kg',
        // No validated kg-of-CO2 -> trees conversion factor exists in this
        // codebase; reporting a headline "trees saved" number would be a
        // fabricated value, so this stays null until a real methodology is
        // documented (see docs/engineering/05_API.md).
        treesEquivalent: null,
        generatedAt: nowIso(),
      };
    },

    async getForecast(horizon: number): Promise<DemandForecast> {
      const series = await deps.analytics.getDailyRecycledWeightSeries();
      const observations = series.map((row) => ({ date: row.date, weight_kg: row.weightKg }));
      const fetchFn = deps.fetchImpl ?? fetch;
      const url = `${deps.deviceAiServiceUrl.replace(/\/+$/, '')}/forecast/ewaste`;

      let body: ForecastEwasteResponse;
      try {
        const response = await fetchFn(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ observations, horizon }),
          signal: AbortSignal.timeout(deps.deviceAiTimeoutMs),
        });
        if (!response.ok) {
          deps.logger.warn(
            { url, status: response.status },
            'Forecast proxy received a non-OK response',
          );
          return unavailableForecast(
            horizon,
            `Device AI service responded with HTTP ${response.status}.`,
          );
        }
        body = (await response.json()) as ForecastEwasteResponse;
      } catch (error) {
        deps.logger.warn({ url, err: error }, 'Forecast proxy request failed');
        return unavailableForecast(
          horizon,
          'Could not reach the device intelligence forecasting service.',
        );
      }

      deps.logger.info(
        { status: body.status, historyDays: body.history_days },
        'Government forecast requested',
      );

      return {
        horizon: String(body.horizon),
        model: body.model ? `${body.model.name}:${body.model.version}` : null,
        points: body.points.map((p) => ({
          period: p.date,
          predictedWeight: p.predicted_weight_kg,
          predictedSubmissions: null,
          confidence: null,
        })),
        weightUnit: 'kg',
        generatedAt: nowIso(),
        status: body.status === 'TRAINED' ? 'OK' : body.status,
        reason: body.reason,
        historyDays: body.history_days,
        minHistoryDaysRequired: body.min_history_days_required,
        history: body.history.map((h) => ({ period: h.date, actualWeight: h.actual_weight_kg })),
        evaluation: body.evaluation
          ? {
              rmse: body.evaluation.rmse,
              mae: body.evaluation.mae,
              mape: body.evaluation.mape,
              trainSamples: body.evaluation.train_samples,
              valSamples: body.evaluation.val_samples,
            }
          : null,
      };
    },
  };
}

function unavailableForecast(horizon: number, reason: string): DemandForecast {
  return {
    horizon: String(horizon),
    model: null,
    points: [],
    weightUnit: 'kg',
    generatedAt: nowIso(),
    status: 'SERVICE_UNAVAILABLE',
    reason,
    historyDays: 0,
    minHistoryDaysRequired: 0,
    history: [],
    evaluation: null,
  };
}
