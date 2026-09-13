/**
 * In-app notification data hooks (Consumer-only, P10.3).
 *
 * TanStack Query wrappers around the notification API, following the exact
 * conventions already used by every other feature (see
 * use-recycler-assignments.ts). No polling — the list refetches only when
 * the query becomes stale, on mount, or after a mutation invalidates it.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { notificationApi } from '@/api/notification.api';
import { queryKeys } from '@/lib/query-keys';

/** The authenticated consumer's own notifications, newest first. */
export function useNotifications() {
  return useQuery({
    queryKey: queryKeys.notifications.list(),
    queryFn: () => notificationApi.getNotifications(),
  });
}

/** Marks one notification read, then refreshes the list so the unread badge updates. */
export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => notificationApi.markRead(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all });
    },
  });
}
