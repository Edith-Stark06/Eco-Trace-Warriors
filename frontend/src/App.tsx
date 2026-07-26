import { Toaster } from 'sonner';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { QueryProvider } from '@/providers/QueryProvider';
import { ThemeProvider } from '@/providers/ThemeProvider';
import { AuthProvider } from '@/providers/AuthProvider';
import { AppRouter } from '@/routes/AppRouter';

/**
 * Application root: composes global providers and the router.
 *
 * Order matters — ErrorBoundary wraps everything so provider/render errors
 * surface a recoverable fallback; ThemeProvider is outermost among providers
 * so theming applies before content paints.
 */
export function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <QueryProvider>
          <AuthProvider>
            <AppRouter />
            <Toaster richColors closeButton position="top-right" />
          </AuthProvider>
        </QueryProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}
