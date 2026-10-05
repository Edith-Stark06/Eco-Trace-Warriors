import * as React from 'react';
import { cn } from '@/lib/utils';

/**
 * Page heading (`<h1>`) for a dashboard view. One per page.
 */
export function PageTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h1 className={cn('text-2xl font-semibold tracking-tight', className)} {...props} />;
}

/**
 * Supporting description shown beneath a PageTitle.
 */
export function PageDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn('text-sm text-muted-foreground', className)} {...props} />;
}

interface DashboardHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string;
  description?: string;
  /** Optional actions (buttons, filters) aligned to the right on wider screens. */
  actions?: React.ReactNode;
}

/**
 * Standard page header for dashboard views: a title, optional description, and
 * an optional actions slot. Stacks on mobile and spreads on `sm+`.
 */
export function DashboardHeader({
  title,
  description,
  actions,
  className,
  ...props
}: DashboardHeaderProps) {
  return (
    <div
      className={cn(
        'flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between',
        className,
      )}
      {...props}
    >
      <div className="flex flex-col gap-1">
        <PageTitle>{title}</PageTitle>
        {description && <PageDescription>{description}</PageDescription>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}
