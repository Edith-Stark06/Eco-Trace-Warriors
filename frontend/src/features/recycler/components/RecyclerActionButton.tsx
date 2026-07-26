import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { icons } from '@/lib/icons';
import { toApiError } from '@/api/client';
import type { CompleteRecyclingResult, Submission } from '@/types';
import { useStartRecycling } from '@/features/recycler/hooks/use-recycler-assignments';
import { CompleteRecyclingDialog } from '@/features/recycler/components/CompleteRecyclingDialog';
import {
  COMPLETE_RECYCLING_LABEL,
  recyclerActionForStatus,
  START_RECYCLING_COPY,
} from '@/features/recycler/lib/recycler-display';

interface RecyclerActionButtonProps {
  submission: Submission;
  /** Optional size for the trigger button. */
  size?: 'sm' | 'default';
  /** Called after a successful start transition (e.g. to navigate away). */
  onStarted?: () => void;
  /** Receives the backend `{ submission, reward }` result after completion. */
  onCompleted?: (result: CompleteRecyclingResult) => void;
}

/**
 * The single legal workflow-action control for a recycler assignment. Renders
 * nothing when the status has no action (RECYCLED / off-path), a confirmation
 * dialog for COLLECTED → start, and the recovery form dialog for RECYCLING →
 * complete. Mirrors the backend transition rules so an invalid action is never
 * offered.
 */
export function RecyclerActionButton({
  submission,
  size = 'sm',
  onStarted,
  onCompleted,
}: RecyclerActionButtonProps) {
  const action = recyclerActionForStatus(submission.status);
  if (action === 'start') {
    return <StartRecyclingButton submission={submission} size={size} onStarted={onStarted} />;
  }
  if (action === 'complete') {
    return (
      <CompleteRecyclingButton submission={submission} size={size} onCompleted={onCompleted} />
    );
  }
  return null;
}

/** COLLECTED → RECYCLING, guarded by a confirmation dialog. */
function StartRecyclingButton({
  submission,
  size,
  onStarted,
}: {
  submission: Submission;
  size: 'sm' | 'default';
  onStarted?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const { mutateAsync, isPending } = useStartRecycling();

  const handleConfirm = async () => {
    try {
      await mutateAsync(submission.id);
      toast.success(START_RECYCLING_COPY.successMessage);
      setOpen(false);
      onStarted?.();
    } catch (error) {
      toast.error(toApiError(error).message);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size={size}>{START_RECYCLING_COPY.label}</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{START_RECYCLING_COPY.confirmTitle}</DialogTitle>
          <DialogDescription>{START_RECYCLING_COPY.confirmDescription}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={isPending}>
            Cancel
          </Button>
          <Button onClick={handleConfirm} disabled={isPending}>
            {isPending && <icons.spinner className="animate-spin" aria-hidden="true" />}
            {START_RECYCLING_COPY.label}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** RECYCLING → RECYCLED via the recovery-recording dialog. */
function CompleteRecyclingButton({
  submission,
  size,
  onCompleted,
}: {
  submission: Submission;
  size: 'sm' | 'default';
  onCompleted?: (result: CompleteRecyclingResult) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button size={size} onClick={() => setOpen(true)}>
        {COMPLETE_RECYCLING_LABEL}
      </Button>
      <CompleteRecyclingDialog
        submission={submission}
        open={open}
        onOpenChange={setOpen}
        onCompleted={(result) => onCompleted?.(result)}
      />
    </>
  );
}
