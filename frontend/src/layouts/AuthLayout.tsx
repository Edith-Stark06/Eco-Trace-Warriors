import { Outlet } from 'react-router-dom';
import { Leaf } from 'lucide-react';
import { env } from '@/lib/env';

/**
 * Simple centered layout for unauthenticated pages (e.g. login).
 * No business UI — just a branded, centered container.
 */
export function AuthLayout() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-muted/30 px-4">
      <div className="mb-6 flex items-center gap-2 text-lg font-semibold">
        <Leaf className="size-6 text-primary" aria-hidden="true" />
        <span>{env.appName}</span>
      </div>
      <div className="w-full max-w-sm rounded-xl border bg-card p-6 shadow-sm">
        <Outlet />
      </div>
    </div>
  );
}
