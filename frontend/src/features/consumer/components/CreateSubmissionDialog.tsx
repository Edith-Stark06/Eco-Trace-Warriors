import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { icons } from '@/lib/icons';
import { toApiError } from '@/api/client';
import type { CreateSubmissionPayload } from '@/types';
import { useCreateSubmission } from '@/features/consumer/hooks/use-submissions';
import { SubmissionForm } from '@/features/consumer/components/SubmissionForm';

interface CreateSubmissionDialogProps {
  /** Optional custom trigger; defaults to a "New submission" button. */
  trigger?: React.ReactNode;
}

/**
 * Dialog that hosts the create-submission form. Owns open state and the create
 * mutation; on success it closes, toasts, and lets React Query invalidation
 * refresh the affected lists (no manual refetch).
 */
export function CreateSubmissionDialog({ trigger }: CreateSubmissionDialogProps) {
  const [open, setOpen] = useState(false);
  const { mutateAsync, isPending } = useCreateSubmission();
  const PlusIcon = icons.plus;

  const handleSubmit = async (payload: CreateSubmissionPayload) => {
    try {
      await mutateAsync(payload);
      toast.success('Submission created.');
      setOpen(false);
    } catch (error) {
      toast.error(toApiError(error).message);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button>
            <PlusIcon aria-hidden="true" />
            New submission
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create submission</DialogTitle>
          <DialogDescription>Register an e-waste item for pickup and recycling.</DialogDescription>
        </DialogHeader>
        <SubmissionForm
          onSubmit={handleSubmit}
          isSubmitting={isPending}
          submitLabel="Create submission"
          onCancel={() => setOpen(false)}
        />
      </DialogContent>
    </Dialog>
  );
}
