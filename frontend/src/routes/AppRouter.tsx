import { lazy } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { MainLayout } from '@/layouts/MainLayout';
import { AuthLayout } from '@/layouts/AuthLayout';
import { ProtectedRoute } from '@/routes/ProtectedRoute';
import { RoleGuard } from '@/routes/RoleGuard';
import { ROUTES } from '@/lib/routes';

import { LoginPage } from '@/pages/LoginPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { NotFoundPage } from '@/pages/NotFoundPage';

/**
 * Content pages are code-split with React.lazy so each role's dashboard (and
 * settings) ships in its own chunk, loaded on demand. The MainLayout wraps its
 * <Outlet /> in a Suspense boundary that shows the shared PageLoader while a
 * chunk downloads. Login and the dashboard redirect stay eager: they are the
 * entry points and carry no meaningful bundle weight.
 */
const ConsumerDashboardPage = lazy(() => import('@/features/consumer/ConsumerDashboardPage'));
const CollectorDashboardPage = lazy(() => import('@/features/collector/CollectorDashboardPage'));
const RecyclerDashboardPage = lazy(() => import('@/features/recycler/RecyclerDashboardPage'));
const GovernmentDashboardPage = lazy(() => import('@/features/government/GovernmentDashboardPage'));
const AdminDashboardPage = lazy(() => import('@/features/admin/AdminDashboardPage'));
const SettingsPage = lazy(() => import('@/pages/SettingsPage'));

/**
 * Central route table.
 *
 * Public routes use AuthLayout; authenticated routes are wrapped by
 * ProtectedRoute + MainLayout. Role-specific dashboards are additionally
 * fenced by RoleGuard (UX-only; real authorization is server-side). Settings is
 * shared by all authenticated roles.
 */
export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Root → dashboard redirect */}
        <Route path={ROUTES.root} element={<Navigate to={ROUTES.dashboard} replace />} />

        {/* Public */}
        <Route element={<AuthLayout />}>
          <Route path={ROUTES.login} element={<LoginPage />} />
        </Route>

        {/* Authenticated */}
        <Route element={<ProtectedRoute />}>
          <Route element={<MainLayout />}>
            <Route path={ROUTES.dashboard} element={<DashboardPage />} />
            <Route path={ROUTES.settings} element={<SettingsPage />} />

            <Route element={<RoleGuard allow={['CONSUMER']} />}>
              <Route path={ROUTES.consumer} element={<ConsumerDashboardPage />} />
            </Route>

            <Route element={<RoleGuard allow={['COLLECTOR']} />}>
              <Route path={ROUTES.collector} element={<CollectorDashboardPage />} />
            </Route>

            <Route element={<RoleGuard allow={['RECYCLER']} />}>
              <Route path={ROUTES.recycler} element={<RecyclerDashboardPage />} />
            </Route>

            <Route element={<RoleGuard allow={['GOVERNMENT', 'ADMIN']} />}>
              <Route path={ROUTES.government} element={<GovernmentDashboardPage />} />
            </Route>

            <Route element={<RoleGuard allow={['ADMIN']} />}>
              <Route path={ROUTES.admin} element={<AdminDashboardPage />} />
            </Route>
          </Route>
        </Route>

        {/* Catch-all */}
        <Route path={ROUTES.notFound} element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  );
}
