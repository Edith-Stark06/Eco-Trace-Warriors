import { AssignUserDialog } from '@/features/admin/components/AssignUserDialog';
import { useAssignRecycler, useRecyclers } from '@/features/admin/hooks/use-admin';
import type { Submission } from '@/types';

interface AssignRecyclerDialogProps {
  submission: Submission;
}

/**
 * Assign a recycler to a COLLECTED submission (PATCH /submissions/:id/assign-recycler).
 * Candidates come from GET /users?role=RECYCLER. Thin wrapper over the shared
 * AssignUserDialog — all UI and error handling live there.
 */
export function AssignRecyclerDialog({ submission }: AssignRecyclerDialogProps) {
  const { data, isPending: isLoadingCandidates, isError } = useRecyclers();
  const { mutateAsync, isPending } = useAssignRecycler();

  return (
    <AssignUserDialog
      submission={submission}
      candidates={data ?? []}
      isLoadingCandidates={isLoadingCandidates}
      isCandidatesError={isError}
      isPending={isPending}
      onAssign={(recyclerId) => mutateAsync({ submissionId: submission.id, recyclerId })}
      copy={{
        triggerLabel: 'Assign Recycler',
        title: 'Assign recycler',
        description: 'Select an active recycler',
        selectLabel: 'Recycler',
        selectPlaceholder: 'Select a recycler',
        emptyMessage: 'No active recyclers are available.',
        confirmLabel: 'Assign',
        successMessage: 'Recycler assigned.',
      }}
    />
  );
}
