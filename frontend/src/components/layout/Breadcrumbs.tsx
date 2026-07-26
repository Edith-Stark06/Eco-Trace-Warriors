import { Fragment } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { icons } from '@/lib/icons';
import { buildBreadcrumbs } from '@/lib/breadcrumbs';

/**
 * Route-derived breadcrumb trail. The path is parsed into crumbs automatically
 * (see `buildBreadcrumbs`), so pages need no per-page configuration. The final
 * crumb marks the current page (`aria-current`) and is not a link.
 */
export function Breadcrumbs() {
  const { pathname } = useLocation();
  const crumbs = buildBreadcrumbs(pathname);
  const ChevronIcon = icons.chevronRight;

  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex items-center gap-1 text-sm">
        {crumbs.map((crumb, index) => {
          const isLast = index === crumbs.length - 1;
          return (
            <Fragment key={`${crumb.label}-${index}`}>
              {index > 0 && (
                <ChevronIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              )}
              <li className="min-w-0">
                {isLast || !crumb.path ? (
                  <span aria-current="page" className="truncate font-medium text-foreground">
                    {crumb.label}
                  </span>
                ) : (
                  <Link
                    to={crumb.path}
                    className="truncate text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {crumb.label}
                  </Link>
                )}
              </li>
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
