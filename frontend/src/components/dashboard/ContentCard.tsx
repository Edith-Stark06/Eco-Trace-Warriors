import * as React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

interface ContentCardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Optional card heading. */
  title?: string;
  /** Optional supporting line beneath the title. */
  description?: string;
  /** Optional actions aligned to the right of the header. */
  actions?: React.ReactNode;
}

/**
 * Convenience wrapper over the Card primitive for the common "titled panel"
 * pattern used across dashboards. Renders a header only when a title or actions
 * are supplied, otherwise just a padded content surface.
 */
export function ContentCard({ title, description, actions, children, ...props }: ContentCardProps) {
  const hasHeader = Boolean(title || actions);

  return (
    <Card {...props}>
      {hasHeader && (
        <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
          <div className="flex flex-col gap-1">
            {title && <CardTitle>{title}</CardTitle>}
            {description && <CardDescription>{description}</CardDescription>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </CardHeader>
      )}
      <CardContent className={hasHeader ? undefined : 'pt-6'}>{children}</CardContent>
    </Card>
  );
}
