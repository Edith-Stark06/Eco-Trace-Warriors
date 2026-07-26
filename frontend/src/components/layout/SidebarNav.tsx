import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { icons } from '@/lib/icons';
import { navItemsForRole } from '@/lib/navigation';
import { useAuth } from '@/hooks/use-auth';

interface SidebarNavProps {
  /** Called after a link is activated (used to close the mobile drawer). */
  onNavigate?: () => void;
}

/**
 * Role-filtered navigation link list, shared by the desktop sidebar and the
 * mobile drawer so the two never drift. Only links permitted for the current
 * user's role are rendered — unauthorized destinations are never exposed.
 */
export function SidebarNav({ onNavigate }: SidebarNavProps) {
  const { user } = useAuth();
  const items = navItemsForRole(user?.role);

  return (
    <nav aria-label="Primary" className="flex flex-col gap-1">
      {items.map((item) => {
        const Icon = icons[item.icon];
        return (
          <NavLink
            key={item.path}
            to={item.path}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
                isActive
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
              )
            }
          >
            <Icon className="size-4 shrink-0" aria-hidden="true" />
            <span>{item.label}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}
