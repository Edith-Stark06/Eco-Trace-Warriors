import * as React from 'react';
import { cn } from '@/lib/utils';

interface SectionProps extends React.HTMLAttributes<HTMLElement> {
  /** Optional section heading rendered above the content. */
  title?: string;
  /** Optional supporting line beneath the section title. */
  description?: string;
  /** Optional actions aligned to the right of the section heading. */
  actions?: React.ReactNode;
}

/**
 * Vertical content grouping within a dashboard page. Provides consistent
 * spacing and an optional titled header so pages compose from uniform blocks.
 */
export function Section({
  title,
  description,
  actions,
  className,
  children,
  ...props
}: SectionProps) {
  return (
    <section className={cn('flex flex-col gap-4', className)} {...props}>
      {(title || actions) && (
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-col gap-1">
            {title && <h2 className="text-lg font-semibold tracking-tight">{title}</h2>}
            {description && <p className="text-sm text-muted-foreground">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
