import { RoleDashboardPlaceholder } from '@/features/shared/RoleDashboardPlaceholder';

/**
 * Recycler dashboard (placeholder). Business features are out of scope for the
 * shared-framework sprint — this renders the standard placeholder body inside
 * the application shell. Default export for React.lazy code-splitting.
 */
export default function RecyclerDashboardPage() {
  return <RoleDashboardPlaceholder title="Recycler" icon="recycler" />;
}
