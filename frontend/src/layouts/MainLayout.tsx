import { Outlet } from 'react-router-dom';
import { Navbar } from '@/components/layout/Navbar';
import { Sidebar } from '@/components/layout/Sidebar';
import { Footer } from '@/components/layout/Footer';

/**
 * Application shell for authenticated areas.
 *
 * Composes the navbar, sidebar, main content region, and footer placeholders.
 * Nested routes render into <Outlet />.
 */
export function MainLayout() {
  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      <div className="flex flex-1">
        <Sidebar />
        <main className="flex flex-1 flex-col px-4 py-6">
          <Outlet />
        </main>
      </div>
      <Footer />
    </div>
  );
}
