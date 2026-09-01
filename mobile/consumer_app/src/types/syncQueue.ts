import type { CreateSubmissionInput } from './submission';

export type SyncQueueStatus = 'pending' | 'syncing' | 'failed';

/** A waste report captured while offline (or that failed to sync), queued for retry. */
export interface SyncQueueItem {
  id: string;
  input: CreateSubmissionInput;
  status: SyncQueueStatus;
  attempts: number;
  lastError: string | null;
  createdAt: string;
}
