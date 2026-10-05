/**
 * `pending`: queued, waiting for its next retry window.
 * `syncing`: a sync attempt is in flight right now.
 * `conflict`: the server rejected it with 409 — the device was likely
 *   already finalized elsewhere (e.g. a prior attempt actually succeeded
 *   server-side but the response never reached this client). Retrying
 *   automatically would just conflict again, so this is a terminal state
 *   the user must acknowledge, distinct from a generic `failed` item.
 * `failed`: exceeded the maximum retry attempts on a non-network,
 *   non-conflict error (e.g. persistent validation failure).
 * There is no explicit "synced" status — a successfully synced item is
 * simply removed from the queue.
 */
export type SyncQueueStatus = 'pending' | 'syncing' | 'conflict' | 'failed';

/**
 * A device confirmed via the AI capture flow while offline (or that failed
 * to sync), queued for retry. Collectors are not authorized to create
 * backend Submission records (POST /submissions requires the CONSUMER
 * role — backend/src/modules/submission/submission.routes.ts); a
 * Collector's own real action is confirming/finalizing the AI-side device
 * record for the pickup they are already handling, so that is what this
 * queue holds.
 */
export interface SyncQueueItem {
  id: string;
  deviceId: string;
  deviceType: string;
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
