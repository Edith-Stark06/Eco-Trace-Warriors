import { useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { SidebarNav } from '@/components/layout/SidebarNav';
import { LogoutButton } from '@/components/layout/LogoutButton';
import { icons } from '@/lib/icons';
import { env } from '@/lib/env';

/**
 * Mobile navigation drawer. The trigger (a hamburger button) is shown only
 * below the `md` breakpoint, where the fixed sidebar is hidden. Selecting a
 * link — or signing out — closes the drawer. Built on the accessible Radix
 * dialog underlying our Sheet primitive (focus trap, ESC, scrim).
 */
export function MobileSidebar() {
  const [open, setOpen] = useState(false);
  const MenuIcon = icons.menu;
  const BrandIcon = icons.brand;
  const close = () => setOpen(false);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open navigation menu">
          <MenuIcon aria-hidden="true" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="flex w-64 flex-col p-0">
        <SheetHeader className="p-4">
          <SheetTitle className="flex items-center gap-2">
            <BrandIcon className="size-5 text-primary" aria-hidden="true" />
            <span>{env.appName}</span>
          </SheetTitle>
        </SheetHeader>
        <Separator />
        <div className="flex-1 overflow-y-auto p-3">
          <SidebarNav onNavigate={close} />
        </div>
        <Separator />
        <div className="p-3">
          <LogoutButton className="w-full justify-start" onAfterLogout={close} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
