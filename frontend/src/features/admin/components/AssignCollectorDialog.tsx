import { AssignUserDialog } from '@/features/admin/components/AssignUserDialog';
import { useAssignCollector, useCollectors } from '@/features/admin/hooks/use-admin';
import type { Submission } from '@/types';

interface AssignCollectorDialogProps {
  submission: Submission;
}

/**
 * Assign a collector to a PENDING submission (PATCH /submissions/:id/assign).
 * Candidates come from GET /users?role=COLLECTOR. Thin wrapper over the shared
 * AssignUserDialog — all UI and error handling live there.
 */
export function AssignCollectorDialog({ submission }: AssignCollectorDialogProps) {
  const { data, isPending: isLoadingCandidates, isError } = useCollectors();
  const { mutateAsync, isPending } = useAssignCollector();

  return (
    <AssignUserDialog
      submission={submission}
      candidates={data ?? []}
      isLoadingCandidates={isLoadingCandidates}
      isCandidatesError={isError}
      isPending={isPending}
      onAssign={(collectorId) => mutateAsync({ submissionId: submission.id, collectorId })}
      copy={{
        triggerLabel: 'Assign Collector',
        title: 'Assign collector',
        description: 'Select an active collector',
        selectLabel: 'Collector',
        selectPlaceholder: 'Select a collector',
        emptyMessage: 'No active collectors are available.',
        confirmLabel: 'Assign',
        successMessage: 'Collector assigned.',
      }}
    />
  );
}
