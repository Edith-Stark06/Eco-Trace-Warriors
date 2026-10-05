/**
 * Forecast horizon options for the Government dashboard's selector.
 *
 * The backend accepts any integer 1–90 (`MAX_FORECAST_HORIZON`,
 * `backend/src/modules/analytics/analytics.schemas.ts`); these five values
 * are simply a curated, commonly-useful subset presented to the user — every
 * one of them is a value the real API genuinely supports, not an
 * arbitrarily-invented option.
 */
export const FORECAST_HORIZON_OPTIONS = [7, 14, 30, 60, 90] as const;

export const DEFAULT_FORECAST_HORIZON = 30;
