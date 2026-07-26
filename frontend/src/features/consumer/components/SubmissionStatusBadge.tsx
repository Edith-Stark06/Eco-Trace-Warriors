import { Badge } from '@/components/ui/badge';
import { statusBadgeVariant, statusLabel } from '@/features/consumer/lib/submission-display';

interface SubmissionStatusBadgeProps {
  status: string;
}

/**
 * Status pill for a submission's lifecycle state. Presentation only — maps the
 * backend status to a consistent label and badge variant.
 */
export function SubmissionStatusBadge({ status }: SubmissionStatusBadgeProps) {
  return <Badge variant={statusBadgeVariant(status)}>{statusLabel(status)}</Badge>;
}
