import { useNavigate } from 'react-router-dom';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { icons } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { consumerSubmissionPath } from '@/lib/routes';
import { useAuth } from '@/hooks/use-auth';
import { formatDateTime } from '@/features/consumer/lib/submission-display';
import {
  useMarkNotificationRead,
  useNotifications,
} from '@/features/notifications/hooks/use-notifications';
import { notificationIcon, unreadBadgeLabel } from '@/features/notifications/lib/notification-display';
import type { AppNotification } from '@/types';

/**
 * In-app notification bell (P10.3) — persistent, authenticated, Consumer-only.
 * Real lifecycle-triggered notifications only: no push, no email, no SMS, no
 * WebSocket. Backend endpoints are Consumer-authorized only
 * (backend/src/modules/notification/notification.routes.ts), so this
 * component only fetches for a signed-in Consumer; every other role keeps
 * the honest static placeholder — there is nothing real to show them here.
 */
export function NotificationButton() {
  const { user } = useAuth();
  const isConsumer = user?.role === 'CONSUMER';

  if (!isConsumer) {
    return <PlaceholderBell />;
  }

  return <ConsumerNotificationBell />;
}

/** Unchanged placeholder for non-Consumer roles — no real notification feed exists for them. */
function PlaceholderBell() {
  const BellIcon = icons.bell;
  return (
    <Button variant="ghost" size="icon" aria-label="Notifications" disabled>
      <BellIcon aria-hidden="true" />
    </Button>
  );
}

function ConsumerNotificationBell() {
  const navigate = useNavigate();
  const { data, isPending, isError, refetch } = useNotifications();
  const { mutate: markRead } = useMarkNotificationRead();
  const BellIcon = icons.bell;

  const unreadCount = data?.filter((n) => !n.isRead).length ?? 0;

  const handleSelect = (notification: AppNotification) => {
    if (!notification.isRead) {
      markRead(notification.id);
    }
    navigate(consumerSubmissionPath(notification.submissionId));
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={
            unreadCount > 0 ? `Notifications (${unreadCount} unread)` : 'Notifications'
          }
        >
          <BellIcon aria-hidden="true" />
          {unreadCount > 0 && (
            <Badge
              variant="destructive"
              className="absolute -right-1 -top-1 h-4 min-w-4 justify-center rounded-full px-1 text-[10px] leading-none"
            >
              {unreadBadgeLabel(unreadCount)}
            </Badge>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel>Notifications</DropdownMenuLabel>
        <DropdownMenuSeparator />

        {isPending ? (
          <div className="flex flex-col gap-2 p-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : isError ? (
          <div className="p-2">
            <Alert variant="destructive">
              <icons.alert className="size-4" />
              <AlertDescription className="flex items-center justify-between gap-2">
                <span>Couldn&apos;t load notifications.</span>
                <Button variant="outline" size="sm" onClick={() => void refetch()}>
                  Retry
                </Button>
              </AlertDescription>
            </Alert>
          </div>
        ) : data.length === 0 ? (
          <p className="px-2 py-6 text-center text-sm text-muted-foreground">
            No notifications yet
          </p>
        ) : (
          <div className="max-h-96 overflow-y-auto">
            {data.map((notification) => {
              const Icon = icons[notificationIcon(notification.type)];
              return (
                <DropdownMenuItem
                  key={notification.id}
                  className="flex items-start gap-2 whitespace-normal py-2"
                  onSelect={() => handleSelect(notification)}
                >
                  <Icon
                    className={cn('mt-0.5 size-4 shrink-0', !notification.isRead && 'text-primary')}
                    aria-hidden="true"
                  />
                  <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <p
                      className={cn(
                        'text-sm leading-snug',
                        !notification.isRead && 'font-medium text-foreground',
                        notification.isRead && 'text-muted-foreground',
                      )}
                    >
                      {notification.message}
                    </p>
                    <span className="text-xs text-muted-foreground">
                      {formatDateTime(notification.createdAt)}
                    </span>
                  </div>
                  {!notification.isRead && (
                    <span
                      className="mt-1.5 size-2 shrink-0 rounded-full bg-primary"
                      aria-label="Unread"
                    />
                  )}
                </DropdownMenuItem>
              );
            })}
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
