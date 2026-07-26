import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Button } from '@/components/ui/button';
import { icons } from '@/lib/icons';

/**
 * Notifications entry point (placeholder). The bell and its "no notifications"
 * tooltip are wired up now so the navbar layout is final; the real
 * notification feed arrives in a later sprint. No business data here.
 */
export function NotificationButton() {
  const BellIcon = icons.bell;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon" aria-label="Notifications">
            <BellIcon aria-hidden="true" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>No new notifications</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
