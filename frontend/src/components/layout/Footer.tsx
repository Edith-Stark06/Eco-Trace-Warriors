import { env } from '@/lib/env';

/** Footer placeholder. */
export function Footer() {
  return (
    <footer className="border-t bg-background px-4 py-3 text-center text-xs text-muted-foreground">
      {env.appName} · IEEE YESIST 2026
    </footer>
  );
}
