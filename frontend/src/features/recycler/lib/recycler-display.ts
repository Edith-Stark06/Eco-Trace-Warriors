/**
 * Recycler assignment presentation & workflow helpers.
 *
 * Pure functions that map an assignment's status to the recycler's single legal
 * workflow action and compute the dashboard status summary. Kept free of React
 * so they are trivially unit-testable and reused across the dashboard, table,
 * and detail views. The status→action map mirrors the backend transition rules
 * (COLLECTED→start, RECYCLING→complete) so the UI never offers an action the
 * server would reject.
 */
import type { MaterialRecovery, Submission, SubmissionStatus } from '@/types';

/** The workflow transitions a recycler can trigger directly. */
export type RecyclerAction = 'start' | 'complete';

/**
 * The single legal action for a given status, or null when the recycler can
 * only read the record (RECYCLED, or a status off the recycler path). Mirrors
 * the backend: COLLECTED→start, RECYCLING→complete.
 */
export function recyclerActionForStatus(status: SubmissionStatus): RecyclerAction | null {
  switch (status) {
    case 'COLLECTED':
      return 'start';
    case 'RECYCLING':
      return 'complete';
    default:
      return null;
  }
}

/** True when the assignment is read-only for the recycler (RECYCLED onward). */
export function isReadOnlyForRecycler(status: SubmissionStatus): boolean {
  return recyclerActionForStatus(status) === null;
}

/** Copy for the start-recycling confirmation dialog. */
export const START_RECYCLING_COPY = {
  label: 'Start Recycling',
  confirmTitle: 'Start recycling?',
  confirmDescription: 'Start the recycling process?',
  successMessage: 'Recycling started.',
} as const;

/** Label for the complete-recycling action. */
export const COMPLETE_RECYCLING_LABEL = 'Complete Recycling';

/** Label shown for an assignment that has been fully recycled (read-only). */
export const RECYCLED_LABEL = 'Completed';

/** Aggregate counts shown in the recycler dashboard status summary. */
export interface RecyclerStatusSummary {
  collected: number;
  recycling: number;
  completedToday: number;
  recoveredWeight: number;
}

/**
 * Compute the status summary from the assignment list. The active queue
 * returned by the backend contains only COLLECTED / RECYCLING, so
 * `completedToday` and `recoveredWeight` are derived defensively from any
 * RECYCLED item whose completion timestamp falls on the given day (normally
 * zero, because RECYCLED submissions leave the active queue).
 */
export function computeRecyclerSummary(
  assignments: readonly Submission[],
  now: Date = new Date(),
): RecyclerStatusSummary {
  const summary: RecyclerStatusSummary = {
    collected: 0,
    recycling: 0,
    completedToday: 0,
    recoveredWeight: 0,
  };

  for (const assignment of assignments) {
    switch (assignment.status) {
      case 'COLLECTED':
        summary.collected += 1;
        break;
      case 'RECYCLING':
        summary.recycling += 1;
        break;
      case 'RECYCLED':
        if (isSameDay(assignment.recycledAt, now)) {
          summary.completedToday += 1;
          summary.recoveredWeight += assignment.recoveredWeight ?? 0;
        }
        break;
      default:
        break;
    }
  }

  return summary;
}

/** True when the given ISO timestamp falls on the same calendar day as `now`. */
function isSameDay(iso: string | null, now: Date): boolean {
  if (!iso) return false;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return false;
  return (
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  );
}

/**
 * "Today's recycling" — assignments the recycler is actively processing now
 * (RECYCLING), which are the jobs awaiting completion.
 */
export function activeRecycling(assignments: readonly Submission[]): Submission[] {
  return assignments.filter((assignment) => assignment.status === 'RECYCLING');
}

/**
 * Render the backend `materialRecovery` JSON value (an unknown blob on the
 * submission record) as an ordered list of name/weight rows for display. Returns
 * an empty array when the value is absent or not a well-formed record of
 * numbers, so callers can simply check `.length`.
 */
export function materialRecoveryEntries(
  value: Submission['materialRecovery'],
): { name: string; weight: number }[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
  return Object.entries(value as MaterialRecovery)
    .filter(([, weight]) => typeof weight === 'number' && Number.isFinite(weight))
    .map(([name, weight]) => ({ name, weight }));
}
