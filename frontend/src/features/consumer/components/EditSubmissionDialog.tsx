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
import type { CreateSubmissionPayload, Submission } from '@/types';
import { useUpdateSubmission } from '@/features/consumer/hooks/use-submissions';
import { SubmissionForm } from '@/features/consumer/components/SubmissionForm';
import type { SubmissionFormValues } from '@/features/consumer/lib/submission-form.schema';

interface EditSubmissionDialogProps {
  submission: Submission;
  /** Optional custom trigger; defaults to an "Edit" outline button. */
  trigger?: React.ReactNode;
}

/** Map a submission to the string-based form values used by the form. */
function toFormValues(submission: Submission): SubmissionFormValues {
  return {
    category: submission.category,
    description: submission.description ?? '',
    estimatedWeight: String(submission.estimatedWeight),
    address: submission.address,
    latitude: String(submission.latitude),
    longitude: String(submission.longitude),
    imageUrls: submission.imageUrls.map((value) => ({ value })),
  };
}

/**
 * Dialog that hosts the edit-submission form. Callers must render this only for
 * a PENDING submission (the backend rejects edits afterwards); the dialog owns
 * the update mutation and closes/toasts on success, letting invalidation
 * refresh the detail and list views.
 */
export function EditSubmissionDialog({ submission, trigger }: EditSubmissionDialogProps) {
  const [open, setOpen] = useState(false);
  const { mutateAsync, isPending } = useUpdateSubmission();
  const EditIcon = icons.edit;

  const handleSubmit = async (payload: CreateSubmissionPayload) => {
    try {
      await mutateAsync({ id: submission.id, payload });
      toast.success('Submission updated.');
      setOpen(false);
    } catch (error) {
      toast.error(toApiError(error).message);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button variant="outline">
            <EditIcon aria-hidden="true" />
            Edit
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit submission</DialogTitle>
          <DialogDescription>Update the details of this pending submission.</DialogDescription>
        </DialogHeader>
        <SubmissionForm
          defaultValues={toFormValues(submission)}
          onSubmit={handleSubmit}
          isSubmitting={isPending}
          submitLabel="Save changes"
          onCancel={() => setOpen(false)}
        />
      </DialogContent>
    </Dialog>
  );
}
