/**
 * Notification presentation helpers.
 *
 * Pure formatting — the backend generates the real `message` text; this
 * module only maps the closed `type` enum to a display icon, and reuses the
 * existing date formatter. No new data, no fabricated labels.
 */
import type { IconName } from '@/lib/icons';
import type { NotificationType } from '@/types';

/** Icon shown per real lifecycle event type — purely visual, not new data. */
export function notificationIcon(type: NotificationType): IconName {
  switch (type) {
    case 'COLLECTOR_ASSIGNED':
      return 'collector';
    case 'ITEM_COLLECTED':
      return 'package';
    case 'RECYCLING_COMPLETED':
      return 'recycler';
    default:
      return 'bell';
  }
}

/** Unread-count badge text: exact count up to 99, "99+" beyond that. */
export function unreadBadgeLabel(count: number): string {
  return count > 99 ? '99+' : String(count);
}
