import { env } from '@/lib/env';

/**
 * Application footer for the authenticated shell.
 *
 * Shows the app name, the current year, and a version placeholder
 * (`VITE_APP_VERSION`). No business information.
 */
export function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer className="border-t bg-background px-4 py-3 text-xs text-muted-foreground">
      <div className="flex flex-col items-center justify-between gap-1 sm:flex-row">
        <span>
          © {year} {env.appName} · IEEE YESIST 2026
        </span>
        <span>v{env.appVersion}</span>
      </div>
    </footer>
  );
}
