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
import { useDeleteSubmission } from '@/features/consumer/hooks/use-submissions';

interface DeleteSubmissionDialogProps {
  submission: Submission;
  /** Optional custom trigger; defaults to a destructive "Delete" button. */
  trigger?: React.ReactNode;
  /** Called after a successful delete (e.g. navigate away from a detail page). */
  onDeleted?: () => void;
}

/**
 * Confirmation dialog for deleting a submission. Callers must render this only
 * for a PENDING submission (the backend rejects deletes afterwards). Owns the
 * delete mutation; on success it toasts, closes, and invokes `onDeleted`.
 */
export function DeleteSubmissionDialog({
  submission,
  trigger,
  onDeleted,
}: DeleteSubmissionDialogProps) {
  const [open, setOpen] = useState(false);
  const { mutateAsync, isPending } = useDeleteSubmission();
  const TrashIcon = icons.trash;

  const handleDelete = async () => {
    try {
      await mutateAsync(submission.id);
      toast.success('Submission deleted.');
      setOpen(false);
      onDeleted?.();
    } catch (error) {
      toast.error(toApiError(error).message);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button variant="destructive">
            <TrashIcon aria-hidden="true" />
            Delete
          </Button>
        )}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete submission?</DialogTitle>
          <DialogDescription>
            This will permanently remove the “{submission.category}” submission. This action cannot
            be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={isPending}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={handleDelete} disabled={isPending}>
            {isPending && <icons.spinner className="animate-spin" aria-hidden="true" />}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
