import { SidebarNav } from '@/components/layout/SidebarNav';
import { LogoutButton } from '@/components/layout/LogoutButton';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';

/**
 * Desktop sidebar — a fixed navigation rail shown from the `md` breakpoint up.
 * On smaller screens it is hidden and the navbar's drawer takes over
 * (see MobileSidebar). Links are role-filtered by SidebarNav.
 */
export function Sidebar() {
  return (
    <aside className="hidden w-60 shrink-0 border-r bg-background md:flex md:flex-col">
      <ScrollArea className="flex-1">
        <div className="p-3">
          <SidebarNav />
        </div>
      </ScrollArea>
      <Separator />
      <div className="p-3">
        <LogoutButton className="w-full justify-start" />
      </div>
    </aside>
  );
}
