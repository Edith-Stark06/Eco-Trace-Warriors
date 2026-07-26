import { RoleDashboardPlaceholder } from '@/features/shared/RoleDashboardPlaceholder';

/**
 * Admin dashboard (placeholder). Business features are out of scope for the
 * shared-framework sprint — this renders the standard placeholder body inside
 * the application shell. Default export for React.lazy code-splitting.
 */
export default function AdminDashboardPage() {
  return <RoleDashboardPlaceholder title="Admin" icon="admin" />;
}
