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
import type { Submission } from '@/types';
import {
  actionForStatus,
  type CollectorAction,
  type CollectorActionSpec,
} from '@/features/collector/lib/assignment-display';
import {
  useAcceptAssignment,
  useCompletePickup,
  useStartPickup,
} from '@/features/collector/hooks/use-collector-assignments';

interface AssignmentActionButtonProps {
  submission: Submission;
  /** Optional size for the trigger button. */
  size?: 'sm' | 'default';
  /** Called after a successful transition (e.g. to navigate away). */
  onDone?: () => void;
}

/** Selects the mutation hook for the resolved action. */
function useActionMutation(action: CollectorAction) {
  const accept = useAcceptAssignment();
  const start = useStartPickup();
  const complete = useCompletePickup();
  if (action === 'accept') return accept;
  if (action === 'start') return start;
  return complete;
}

/**
 * A single workflow-action button with a confirmation dialog. It renders only
 * when the submission's status maps to a legal collector transition (mirroring
 * the backend), so invalid actions are never shown. On confirm it runs the
 * matching mutation, toasts success/error via Sonner, and closes.
 *
 * Rendering nothing for a read-only status keeps callers simple: they can drop
 * this in unconditionally and it disappears when there is no action.
 */
export function AssignmentActionButton({
  submission,
  size = 'sm',
  onDone,
}: AssignmentActionButtonProps) {
  const spec = actionForStatus(submission.status);
  if (!spec) return null;
  return <ActionDialog submission={submission} spec={spec} size={size} onDone={onDone} />;
}

/**
 * Inner dialog, split out so the mutation hooks are only mounted when there is
 * an action to perform (hooks cannot run conditionally, so the guard lives in
 * the parent's early return).
 */
function ActionDialog({
  submission,
  spec,
  size,
  onDone,
}: {
  submission: Submission;
  spec: CollectorActionSpec;
  size: 'sm' | 'default';
  onDone?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const { mutateAsync, isPending } = useActionMutation(spec.action);

  const handleConfirm = async () => {
    try {
      await mutateAsync(submission.id);
      toast.success(spec.successMessage);
      setOpen(false);
      onDone?.();
    } catch (error) {
      toast.error(toApiError(error).message);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size={size}>{spec.label}</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{spec.confirmTitle}</DialogTitle>
          <DialogDescription>{spec.confirmDescription}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={isPending}>
            Cancel
          </Button>
          <Button onClick={handleConfirm} disabled={isPending}>
            {isPending && <icons.spinner className="animate-spin" aria-hidden="true" />}
            {spec.label}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
