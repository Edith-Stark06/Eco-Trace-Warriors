import { useState } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { icons } from '@/lib/icons';
import { toApiError } from '@/api/client';
import type { CompleteRecyclingResult, Submission } from '@/types';
import { useCompleteRecycling } from '@/features/recycler/hooks/use-recycler-assignments';
import {
  completeRecyclingFormSchema,
  EMPTY_COMPLETE_RECYCLING_VALUES,
  toCompleteRecyclingPayload,
  type CompleteRecyclingFormValues,
} from '@/features/recycler/lib/complete-recycling.schema';

interface CompleteRecyclingDialogProps {
  submission: Submission;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Receives the backend `{ submission, reward }` result on success. */
  onCompleted: (result: CompleteRecyclingResult) => void;
}

/**
 * Records the recovery outcome for a RECYCLING submission and finalizes it.
 *
 * Validates with the shared Zod schema that mirrors the backend contract, so no
 * request is sent the server would reject. `materials` is a dynamic add/remove
 * list folded into the `materialRecovery` record; recovered weight is required
 * and positive; notes are optional. On success it closes and hands the
 * backend-issued reward to the parent (which shows the reward dialog) — the
 * reward is never computed here.
 */
export function CompleteRecyclingDialog({
  submission,
  open,
  onOpenChange,
  onCompleted,
}: CompleteRecyclingDialogProps) {
  const { mutateAsync, isPending } = useCompleteRecycling();
  // Bump on each open to give React Hook Form a fresh, reset instance.
  const [formKey, setFormKey] = useState(0);

  const handleOpenChange = (next: boolean) => {
    if (next) setFormKey((key) => key + 1);
    onOpenChange(next);
  };

  const handleCompleted = (result: CompleteRecyclingResult) => {
    onOpenChange(false);
    onCompleted(result);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Complete recycling</DialogTitle>
          <DialogDescription>
            Record the recovery outcome for {submission.category}. Rewards are calculated by the
            system once submitted.
          </DialogDescription>
        </DialogHeader>
        <CompleteRecyclingForm
          key={formKey}
          isSubmitting={isPending}
          onCancel={() => onOpenChange(false)}
          onSubmit={async (values) => {
            try {
              const result = await mutateAsync({
                id: submission.id,
                body: toCompleteRecyclingPayload(values),
              });
              toast.success('Recycling completed.');
              handleCompleted(result);
            } catch (error) {
              toast.error(toApiError(error).message);
            }
          }}
        />
      </DialogContent>
    </Dialog>
  );
}

interface CompleteRecyclingFormProps {
  isSubmitting: boolean;
  onSubmit: (values: CompleteRecyclingFormValues) => Promise<void> | void;
  onCancel: () => void;
}

/** The form body, split out so it fully resets when remounted by key. */
function CompleteRecyclingForm({ isSubmitting, onSubmit, onCancel }: CompleteRecyclingFormProps) {
  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<CompleteRecyclingFormValues>({
    resolver: zodResolver(completeRecyclingFormSchema),
    defaultValues: EMPTY_COMPLETE_RECYCLING_VALUES,
  });

  const { fields, append, remove } = useFieldArray({ control, name: 'materials' });

  const PlusIcon = icons.plus;
  const TrashIcon = icons.trash;

  const submit = handleSubmit((values) => onSubmit(values));

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <Label htmlFor="recoveredWeight">Recovered weight (kg)</Label>
        <Input
          id="recoveredWeight"
          type="number"
          inputMode="decimal"
          step="0.1"
          min="0"
          placeholder="e.g. 7.3"
          aria-invalid={errors.recoveredWeight ? true : undefined}
          aria-describedby={errors.recoveredWeight ? 'recoveredWeight-error' : undefined}
          disabled={isSubmitting}
          {...register('recoveredWeight')}
        />
        {errors.recoveredWeight && (
          <p id="recoveredWeight-error" className="text-sm text-destructive">
            {errors.recoveredWeight.message}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="recyclerNotes">Recycler notes (optional)</Label>
        <Textarea
          id="recyclerNotes"
          rows={3}
          placeholder="Process notes, condition, observations, etc."
          aria-invalid={errors.recyclerNotes ? true : undefined}
          aria-describedby={errors.recyclerNotes ? 'recyclerNotes-error' : undefined}
          disabled={isSubmitting}
          {...register('recyclerNotes')}
        />
        {errors.recyclerNotes && (
          <p id="recyclerNotes-error" className="text-sm text-destructive">
            {errors.recyclerNotes.message}
          </p>
        )}
      </div>

      <fieldset className="flex flex-col gap-3" disabled={isSubmitting}>
        <div className="flex items-center justify-between gap-2">
          <legend className="text-sm font-medium leading-none">Material recovery (optional)</legend>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => append({ name: '', weight: '' })}
          >
            <PlusIcon aria-hidden="true" />
            Add material
          </Button>
        </div>

        {fields.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No materials added. Add rows to record recovered materials (e.g. Copper 2.4, Plastic
            3.7).
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {fields.map((field, index) => {
              const nameError = errors.materials?.[index]?.name;
              const weightError = errors.materials?.[index]?.weight;
              return (
                <li key={field.id} className="flex flex-col gap-1">
                  <div className="flex items-start gap-2">
                    <div className="flex-1">
                      <Label htmlFor={`materials.${index}.name`} className="sr-only">
                        Material name {index + 1}
                      </Label>
                      <Input
                        id={`materials.${index}.name`}
                        placeholder="Material (e.g. Copper)"
                        aria-invalid={nameError ? true : undefined}
                        aria-describedby={nameError ? `materials-${index}-name-error` : undefined}
                        {...register(`materials.${index}.name` as const)}
                      />
                    </div>
                    <div className="w-28 shrink-0">
                      <Label htmlFor={`materials.${index}.weight`} className="sr-only">
                        Recovered weight for material {index + 1} (kg)
                      </Label>
                      <Input
                        id={`materials.${index}.weight`}
                        type="number"
                        inputMode="decimal"
                        step="0.1"
                        min="0"
                        placeholder="kg"
                        aria-invalid={weightError ? true : undefined}
                        aria-describedby={
                          weightError ? `materials-${index}-weight-error` : undefined
                        }
                        {...register(`materials.${index}.weight` as const)}
                      />
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => remove(index)}
                      aria-label={`Remove material ${index + 1}`}
                    >
                      <TrashIcon aria-hidden="true" />
                    </Button>
                  </div>
                  {nameError && (
                    <p id={`materials-${index}-name-error`} className="text-sm text-destructive">
                      {nameError.message}
                    </p>
                  )}
                  {weightError && (
                    <p id={`materials-${index}-weight-error`} className="text-sm text-destructive">
                      {weightError.message}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </fieldset>

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting && <icons.spinner className="animate-spin" aria-hidden="true" />}
          Complete Recycling
        </Button>
      </div>
    </form>
  );
}
