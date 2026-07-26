import { RoleDashboardPlaceholder } from '@/features/shared/RoleDashboardPlaceholder';

/**
 * Consumer dashboard (placeholder). Business features are out of scope for the
 * shared-framework sprint — this renders the standard placeholder body inside
 * the application shell. Default export for React.lazy code-splitting.
 */
export default function ConsumerDashboardPage() {
  return <RoleDashboardPlaceholder title="Consumer" icon="consumer" />;
}
