/**
 * Government analytics domain types.
 *
 * These mirror the four analytics endpoints declared in
 * docs/engineering/05_API.md:
 *
 *   GET /analytics/overview              National statistics
 *   GET /analytics/regions               Regional breakdown / heatmap data
 *   GET /analytics/forecast              AI demand forecast (proxied from AI service)
 *   GET /analytics/environmental-impact  Impact metrics
 *
 * IMPORTANT — provisional contract:
 * The backend Analytics module is not yet implemented (the module directory is
 * an empty stub and no `/analytics` router is mounted), and the documentation
 * provides only the one-line endpoint descriptions above — no field-level DTOs.
 *
 * The interfaces below are therefore INFERRED from those descriptions and from
 * the existing, authoritative backend contracts they will naturally aggregate:
 *   - RewardBalance / RewardSustainability (backend rewards module)
 *   - SubmissionStatus lifecycle (backend submission module)
 *
 * They exist so the Government module is fully typed and becomes functional the
 * moment the backend Analytics module ships. When that module is implemented,
 * reconcile these shapes against its real response DTOs and adjust as needed.
 * No value in this file is fabricated data — these are type declarations only.
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
 * an ISO date or "2026-08"); `confidence` is a 0–1 model confidence when the AI
 * service supplies one.
 */
export interface ForecastPoint {
  period: string;
  predictedSubmissions: number;
  predictedWeight: number;
  confidence: number | null;
}

/**
 * GET /analytics/forecast — AI demand forecast proxied from the AI service.
 * `model` identifies the forecasting model when reported.
 */
export interface DemandForecast {
  horizon: string;
  model: string | null;
  points: ForecastPoint[];
  weightUnit: 'kg';
  generatedAt: string;
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
