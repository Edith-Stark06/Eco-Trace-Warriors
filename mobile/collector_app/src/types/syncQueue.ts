export type SyncQueueStatus = 'pending' | 'syncing' | 'failed';

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
}
