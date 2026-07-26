import * as React from 'react';
import { cn } from '@/lib/utils';
import { icons, type IconName } from '@/lib/icons';

interface StatusScreenProps {
  /** Large status code or short marker (e.g. "404", "403", "500"). */
  code?: string;
  icon?: IconName;
  title: string;
  description?: string;
  /** Optional actions (typically navigation buttons). */
  action?: React.ReactNode;
  /** Fill the viewport height (standalone pages) vs. inline within content. */
  fullScreen?: boolean;
  className?: string;
}

/**
 * Shared presentation for full-page status/error screens (access denied, not
 * found, server error). Keeps the three error components visually consistent
 * and free of duplicated markup. Business-logic-free.
 */
export function StatusScreen({
  code,
  icon,
  title,
  description,
  action,
  fullScreen,
  className,
}: StatusScreenProps) {
  const Icon = icon ? icons[icon] : null;

  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-center justify-center gap-4 p-6 text-center',
        fullScreen ? 'min-h-screen' : 'py-16',
        className,
      )}
    >
      {code && <p className="text-5xl font-bold text-primary">{code}</p>}
      {Icon && !code && (
        <span className="rounded-full bg-muted p-3 text-muted-foreground" aria-hidden="true">
          <Icon className="size-7" />
        </span>
      )}
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">{title}</h1>
        {description && (
          <p className="mx-auto max-w-md text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {action && <div className="mt-1 flex flex-wrap justify-center gap-3">{action}</div>}
    </div>
  );
}
