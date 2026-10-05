/**
 * Government analytics domain types.
 *
 * These mirror the analytics endpoints declared in docs/engineering/05_API.md
 * and implemented in backend/src/modules/analytics/:
 *
 *   GET /analytics/overview              National statistics
 *   GET /analytics/regions               Regional breakdown / heatmap data
 *   GET /analytics/forecast              Real LSTM e-waste weight forecast (P10.1)
 *   GET /analytics/environmental-impact  Impact metrics
 *
 * `RegionalStat.state`/`latitude`/`longitude` and
 * `EnvironmentalImpact.treesEquivalent` are always `null` from the real
 * backend — there is no per-region state/coordinate data or a validated
 * trees-equivalent conversion factor to report (see 05_API.md's Analytics
 * notes). No value in this file is fabricated data — these are type
 * declarations only.
 */

/**
 * GET /analytics/overview — national, cross-region statistics for the
 * observer dashboard. All weights are in kilograms; `weightUnit` carries the
 * unit so the UI never hardcodes it. `generatedAt` is an ISO string.
 */
export interface NationalOverview {
  totalSubmissions: number;
  pendingSubmissions: number;
  inProgressSubmissions: number;
  collectedSubmissions: number;
  recycledSubmissions: number;
  totalUsers: number;
  totalCollectors: number;
  totalRecyclers: number;
  totalEstimatedWeight: number;
  totalRecoveredWeight: number;
  totalRewardsIssued: number;
  weightUnit: 'kg';
  generatedAt: string;
}

/**
 * A single region's aggregated statistics, one row of the regional breakdown /
 * heatmap. Latitude/longitude are optional and only present for map rendering;
 * this dashboard renders the breakdown as a table (no map/chart library is
 * bundled).
 */
export interface RegionalStat {
  region: string;
  state: string | null;
  totalSubmissions: number;
  totalWeight: number;
  recycledWeight: number;
  activeCollectors: number;
  activeRecyclers: number;
  latitude: number | null;
  longitude: number | null;
}

/** GET /analytics/regions — per-region breakdown for the observer dashboard. */
export interface RegionalBreakdown {
  regions: RegionalStat[];
  weightUnit: 'kg';
  generatedAt: string;
}

/**
 * A single forecast bucket. `period` is an opaque backend-provided label (e.g.
 * an ISO date or "2026-08"). `predictedSubmissions` is always `null` — the
 * LSTM forecasts daily recycled weight only (docs/engineering/05_API.md), a
 * submission-count model was not built, and this is reported honestly as
 * unavailable rather than guessed. `confidence` is always `null` — the model
 * does not compute a calibrated prediction interval, so none is displayed.
 */
export interface ForecastPoint {
  period: string;
  predictedSubmissions: number | null;
  predictedWeight: number;
  confidence: number | null;
}

/** One real historical day, for ACTUAL-vs-FORECAST display context. */
export interface ForecastHistoryPoint {
  period: string;
  actualWeight: number;
}

/** Real chronological-holdout regression metrics — never fabricated. */
export interface ForecastEvaluation {
  rmse: number;
  mae: number;
  mape: number | null;
  trainSamples: number;
  valSamples: number;
}

/** Machine-readable forecast outcome — see 05_API.md's Analytics notes. */
export type ForecastResultStatus =
  | 'OK'
  | 'INSUFFICIENT_HISTORICAL_DATA'
  | 'MODEL_BACKEND_UNAVAILABLE'
  | 'SERVICE_UNAVAILABLE';

/**
 * GET /analytics/forecast — real LSTM e-waste weight demand forecast (P10.1),
 * trained on Submission.recycledAt/recoveredWeight history. `model` identifies
 * the trained model version when one was used. `status`/`reason` are always
 * present and truthful: when there isn't enough real history yet or the
 * forecasting backend is unavailable, `points`/`history`/`evaluation` are
 * empty/null rather than populated with an invented value — see `status` to
 * distinguish that from a genuine "OK" forecast.
 */
export interface DemandForecast {
  horizon: string;
  model: string | null;
  points: ForecastPoint[];
  weightUnit: 'kg';
  generatedAt: string;
  status: ForecastResultStatus;
  reason: string | null;
  historyDays: number;
  minHistoryDaysRequired: number;
  history: ForecastHistoryPoint[];
  evaluation: ForecastEvaluation | null;
}

/**
 * GET /analytics/environmental-impact — national impact metrics. Mirrors the
 * backend `SustainabilityResult` shape (co2/energy/landfill with explicit
 * units) so figures render identically to per-reward sustainability values.
 * `treesEquivalent` is an optional derived headline metric when provided.
 */
export interface EnvironmentalImpact {
  co2Saved: number;
  energySaved: number;
  landfillDiverted: number;
  co2Unit: 'kg';
  energyUnit: 'kWh';
  landfillUnit: 'kg';
  treesEquivalent: number | null;
  generatedAt: string;
}
