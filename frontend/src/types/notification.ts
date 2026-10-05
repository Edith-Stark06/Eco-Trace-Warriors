/**
 * Notification domain types.
 *
 * Mirror the backend contract exactly (backend/src/modules/notification/*).
 * This is a persistent, in-app, Consumer-only notification center — no push,
 * no email, no SMS, no WebSocket. Every notification is generated
 * server-side from a real submission-lifecycle event.
 */

/** Closed set of real submission-lifecycle events a consumer is notified about. */
export const NOTIFICATION_TYPES = [
  'COLLECTOR_ASSIGNED',
  'ITEM_COLLECTED',
  'RECYCLING_COMPLETED',
] as const;

export type NotificationType = (typeof NOTIFICATION_TYPES)[number];

/**
 * A notification as returned by the backend (`PublicNotification`).
 * `isRead` is derived server-side from `readAt` so the client never has to
 * re-derive it from a nullable timestamp itself.
 */
export interface AppNotification {
  id: string;
  submissionId: string;
  type: NotificationType;
  message: string;
  createdAt: string;
  readAt: string | null;
  isRead: boolean;
}
