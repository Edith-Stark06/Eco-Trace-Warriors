/**
 * Collector assignment presentation & workflow helpers.
 *
 * Pure functions that map an assignment's status to the single legal workflow
 * action and compute the dashboard status summary. Kept free of React so they
 * are trivially unit-testable and reused across the dashboard, table, and
 * detail views. The status→action map mirrors the backend transition rules so
 * the UI never offers an action the server would reject.
 */
import type { Submission, SubmissionStatus } from '@/types';

/** The workflow transitions a collector can trigger. */
export type CollectorAction = 'accept' | 'start' | 'complete';

/** A resolved workflow action with its user-facing copy. */
export interface CollectorActionSpec {
  readonly action: CollectorAction;
  /** Label for the trigger button (e.g. "Accept Assignment"). */
  readonly label: string;
  /** Confirmation dialog title. */
  readonly confirmTitle: string;
  /** Confirmation dialog body. */
  readonly confirmDescription: string;
  /** Success toast shown after the mutation resolves. */
  readonly successMessage: string;
}

/**
 * The single legal action for a given status, or null when the collector can
 * only wait (COLLECTED → awaiting recycler) or the status is off the collector
 * path. Mirrors the backend: ASSIGNED→accept, ACCEPTED→start, IN_PROGRESS→complete.
 */
export function actionForStatus(status: SubmissionStatus): CollectorActionSpec | null {
  switch (status) {
    case 'ASSIGNED':
      return {
        action: 'accept',
        label: 'Accept Assignment',
        confirmTitle: 'Accept assignment?',
        confirmDescription: 'Accept this pickup assignment?',
        successMessage: 'Assignment accepted.',
      };
    case 'ACCEPTED':
      return {
        action: 'start',
        label: 'Start Pickup',
        confirmTitle: 'Start pickup?',
        confirmDescription: 'Start traveling to pickup location?',
        successMessage: 'Pickup started.',
      };
    case 'IN_PROGRESS':
      return {
        action: 'complete',
        label: 'Complete Pickup',
        confirmTitle: 'Complete pickup?',
        confirmDescription: 'Mark this pickup as completed?',
        successMessage: 'Pickup completed.',
      };
    default:
      return null;
  }
}

/**
 * Message shown for an assignment that has no actionable transition for the
 * collector — a COLLECTED pickup now waits for the recycler.
 */
export const AWAITING_RECYCLER_MESSAGE = 'Waiting for recycler.';

/** True when the assignment is read-only for the collector (COLLECTED onward). */
export function isReadOnlyForCollector(status: SubmissionStatus): boolean {
  return actionForStatus(status) === null;
}

/** Aggregate counts shown in the collector dashboard status summary. */
export interface StatusSummary {
  assigned: number;
  accepted: number;
  inProgress: number;
  collectedToday: number;
}

/**
 * Compute the status summary from the assignment list. The active queue
 * returned by the backend contains only ASSIGNED / ACCEPTED / IN_PROGRESS, so
 * `collectedToday` is derived defensively: any COLLECTED item whose completion
 * timestamp falls on the given day is counted (it will normally be zero because
 * COLLECTED submissions leave the active queue).
 */
export function computeStatusSummary(
  assignments: readonly Submission[],
  now: Date = new Date(),
): StatusSummary {
  const summary: StatusSummary = { assigned: 0, accepted: 0, inProgress: 0, collectedToday: 0 };

  for (const assignment of assignments) {
    switch (assignment.status) {
      case 'ASSIGNED':
        summary.assigned += 1;
        break;
      case 'ACCEPTED':
        summary.accepted += 1;
        break;
      case 'IN_PROGRESS':
        summary.inProgress += 1;
        break;
      case 'COLLECTED':
        if (isSameDay(assignment.completedAt, now)) {
          summary.collectedToday += 1;
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
 * "Today's work" — assignments the collector is actively handling now
 * (ACCEPTED or IN_PROGRESS), newest first.
 */
export function todaysWork(assignments: readonly Submission[]): Submission[] {
  return assignments.filter(
    (assignment) => assignment.status === 'ACCEPTED' || assignment.status === 'IN_PROGRESS',
  );
}
