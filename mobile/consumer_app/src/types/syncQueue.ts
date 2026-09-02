import type { CreateSubmissionInput } from './submission';

/**
 * `pending`: queued, waiting for its next retry window.
 * `syncing`: a sync attempt is in flight right now.
 * `conflict`: the server rejected it with 409 — retrying automatically
 *   would just conflict again, so this is a terminal state the user must
 *   acknowledge, distinct from a generic `failed` item.
 * `failed`: exceeded the maximum retry attempts on a non-network,
 *   non-conflict error (e.g. persistent validation failure).
 * There is no explicit "synced" status — a successfully synced item is
 * simply removed from the queue.
 */
export type SyncQueueStatus = 'pending' | 'syncing' | 'conflict' | 'failed';

/** A waste report captured while offline (or that failed to sync), queued for retry. */
export interface SyncQueueItem {
  id: string;
  input: CreateSubmissionInput;
  status: SyncQueueStatus;
  attempts: number;
  lastError: string | null;
  createdAt: string;
  /**
   * ISO-8601 timestamp before which this item should not be retried
   * (exponential backoff after each failed attempt). `null` means it is
   * eligible for the very next sync pass.
   */
  nextRetryAt: string | null;
}
