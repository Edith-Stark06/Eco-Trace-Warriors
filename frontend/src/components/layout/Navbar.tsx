import { Link } from 'react-router-dom';
import { MobileSidebar } from '@/components/layout/MobileSidebar';
import { Breadcrumbs } from '@/components/layout/Breadcrumbs';
import { NotificationButton } from '@/components/layout/NotificationButton';
import { UserMenu } from '@/components/layout/UserMenu';
import { ThemeToggle } from '@/components/common/ThemeToggle';
import { icons } from '@/lib/icons';
import { env } from '@/lib/env';
import { ROUTES } from '@/lib/routes';

/**
 * Top navigation bar of the application shell.
 *
 * Left: mobile drawer toggle, brand logo, and auto-generated breadcrumbs.
 * Right: notifications placeholder, theme toggle, and the user menu. Carries no
 * business information — purely navigation and session controls.
 */
export function Navbar() {
  const BrandIcon = icons.brand;

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background px-3 sm:px-4">
      <MobileSidebar />

      <Link
        to={ROUTES.dashboard}
        className="flex items-center gap-2 font-semibold focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        <BrandIcon className="size-5 text-primary" aria-hidden="true" />
        <span className="hidden sm:inline">{env.appName}</span>
      </Link>

      <div className="mx-1 hidden h-6 w-px bg-border sm:block" aria-hidden="true" />

      <div className="min-w-0 flex-1">
        <Breadcrumbs />
      </div>

      <div className="flex items-center gap-1 sm:gap-2">
        <NotificationButton />
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
}
