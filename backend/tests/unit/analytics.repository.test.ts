import { aggregateDailyRecycledWeight } from '@modules/analytics';
import type { RecycledWeightRow } from '@modules/analytics';

describe('aggregateDailyRecycledWeight', () => {
  it('sums two submissions recycled on the same day into one observation', () => {
    const rows: RecycledWeightRow[] = [
      { recycledAt: new Date('2026-08-01T09:00:00.000Z'), recoveredWeight: 2.5 },
      { recycledAt: new Date('2026-08-01T15:30:00.000Z'), recoveredWeight: 1.5 },
    ];

    const series = aggregateDailyRecycledWeight(rows);

    expect(series).toEqual([{ date: '2026-08-01', weightKg: 4 }]);
  });

  it('produces one entry per distinct calendar date, sorted chronologically', () => {
    const rows: RecycledWeightRow[] = [
      { recycledAt: new Date('2026-08-03T00:00:00.000Z'), recoveredWeight: 3 },
      { recycledAt: new Date('2026-08-01T00:00:00.000Z'), recoveredWeight: 1 },
      { recycledAt: new Date('2026-08-02T00:00:00.000Z'), recoveredWeight: 2 },
    ];

    const series = aggregateDailyRecycledWeight(rows);

    expect(series).toEqual([
      { date: '2026-08-01', weightKg: 1 },
      { date: '2026-08-02', weightKg: 2 },
      { date: '2026-08-03', weightKg: 3 },
    ]);
  });

  it('returns an empty series for no rows (never fabricates a placeholder)', () => {
    expect(aggregateDailyRecycledWeight([])).toEqual([]);
  });

  it('truncates to the UTC calendar date, independent of time-of-day', () => {
    const rows: RecycledWeightRow[] = [
      { recycledAt: new Date('2026-08-01T23:59:59.000Z'), recoveredWeight: 1 },
      { recycledAt: new Date('2026-08-01T00:00:01.000Z'), recoveredWeight: 1 },
    ];

    const series = aggregateDailyRecycledWeight(rows);

    expect(series).toEqual([{ date: '2026-08-01', weightKg: 2 }]);
  });
});
