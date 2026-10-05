/**
 * Consumer submission presentation helpers.
 *
 * Pure functions that map submission domain data to display strings and badge
 * styles, plus the client-side gate for which actions the backend will accept.
 * Kept free of React so they are trivially unit-testable and reused across the
 * dashboard, list, and detail views.
 */
import type { BadgeProps } from '@/components/ui/badge';
import type { Submission, SubmissionStatus } from '@/types';

/** Human-readable label for a lifecycle status (e.g. IN_PROGRESS → "In progress"). */
export function statusLabel(status: string): string {
  return status
    .toLowerCase()
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * Badge variant for a status. PENDING/ASSIGNED read as neutral, terminal
 * success states (RECYCLED, COMPLETED) as primary, REJECTED as destructive,
 * and in-flight states as secondary.
 */
export function statusBadgeVariant(status: string): NonNullable<BadgeProps['variant']> {
  switch (status) {
    case 'RECYCLED':
    case 'COMPLETED':
      return 'default';
    case 'REJECTED':
      return 'destructive';
    case 'PENDING':
      return 'outline';
    default:
      return 'secondary';
  }
}

/**
 * A submission is editable/deletable by its owner only while PENDING — once a
 * collector is assigned the backend rejects modification. The client mirrors
 * this so the user is never offered an action the server will refuse.
 */
export function isSubmissionMutable(status: SubmissionStatus): boolean {
  return status === 'PENDING';
}

/** Message shown when a submission can no longer be modified. */
export const IMMUTABLE_SUBMISSION_MESSAGE = 'This submission can no longer be modified.';

/** Format a weight in kilograms for display (e.g. 2.5 → "2.5 kg"). */
export function formatWeight(kg: number): string {
  return `${kg.toLocaleString(undefined, { maximumFractionDigits: 2 })} kg`;
}

/** Format an ISO timestamp as a short, locale-aware date. */
export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

/** Format an ISO timestamp as a short date and time. */
export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Truncate an address to a single-line summary for dense table rows. */
export function shortAddress(address: string, max = 40): string {
  return address.length > max ? `${address.slice(0, max - 1).trimEnd()}…` : address;
}

/** Sort submissions newest-first by creation date (non-mutating). */
export function sortByNewest(submissions: readonly Submission[]): Submission[] {
  return [...submissions].sort(
    (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
  );
}
