import { Leaf } from 'lucide-react';
import { ThemeToggle } from '@/components/common/ThemeToggle';
import { env } from '@/lib/env';

/** Top navigation bar placeholder. Navigation items arrive in later sprints. */
export function Navbar() {
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b bg-background px-4">
      <div className="flex items-center gap-2 font-semibold">
        <Leaf className="size-5 text-primary" aria-hidden="true" />
        <span>{env.appName}</span>
      </div>
      <div className="flex items-center gap-2">
        <ThemeToggle />
        {/* Placeholder: user menu / notifications land in a later sprint. */}
      </div>
    </header>
  );
}
