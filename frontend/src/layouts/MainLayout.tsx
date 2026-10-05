import { Suspense } from 'react';
import { Outlet } from 'react-router-dom';
import { Navbar } from '@/components/layout/Navbar';
import { Sidebar } from '@/components/layout/Sidebar';
import { Footer } from '@/components/layout/Footer';
import { PageLoader } from '@/components/dashboard/PageLoader';

/**
 * Reusable application shell for every authenticated role.
 *
 * Layout hierarchy:
 *   Navbar (sticky, full width)
 *   ├─ Sidebar (fixed rail on md+, drawer on mobile via the navbar toggle)
 *   └─ Main content (scrolls independently) + Footer
 *
 * Nested routes render into <Outlet />, wrapped in Suspense so lazy-loaded
 * pages show the shared PageLoader without collapsing the shell.
 */
export function MainLayout() {
  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <Navbar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <div className="flex flex-1 flex-col overflow-y-auto">
          <main className="flex-1 px-4 py-6 sm:px-6">
            <Suspense fallback={<PageLoader />}>
              <Outlet />
            </Suspense>
          </main>
          <Footer />
        </div>
      </div>
    </div>
  );
}
