import * as React from 'react';
import { cn } from '@/lib/utils';
import { icons, type IconName } from '@/lib/icons';

interface EmptyStateProps {
  title: string;
  description?: string;
  /** Optional illustrative icon from the central registry. */
  icon?: IconName;
  /** Optional call-to-action (typically a Button). */
  action?: React.ReactNode;
  className?: string;
}

/**
 * Reusable empty-state placeholder for "no data yet" situations across the
 * application. Centered icon, title, description, and an optional action.
 */
export function EmptyState({ title, description, icon, action, className }: EmptyStateProps) {
  const Icon = icon ? icons[icon] : null;

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed px-6 py-12 text-center',
        className,
      )}
    >
      {Icon && (
        <span className="rounded-full bg-muted p-3 text-muted-foreground" aria-hidden="true">
          <Icon className="size-6" />
        </span>
      )}
      <div className="flex flex-col gap-1">
        <h3 className="text-base font-semibold">{title}</h3>
        {description && (
          <p className="mx-auto max-w-sm text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
