import { useForm, useFieldArray } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { icons } from '@/lib/icons';
import type { CreateSubmissionPayload } from '@/types';
import {
  submissionFormSchema,
  type SubmissionFormValues,
} from '@/features/consumer/lib/submission-form.schema';

interface SubmissionFormProps {
  /** Prefilled values for edit mode; omit for a blank create form. */
  defaultValues?: Partial<SubmissionFormValues>;
  /** Receives the coerced, backend-ready payload on valid submit. */
  onSubmit: (payload: CreateSubmissionPayload) => Promise<void> | void;
  /** Whether a submit request is in flight (disables inputs). */
  isSubmitting?: boolean;
  /** Label for the primary button (e.g. "Create submission"). */
  submitLabel: string;
  /** Optional cancel handler; renders a secondary button when provided. */
  onCancel?: () => void;
}

const EMPTY_VALUES: SubmissionFormValues = {
  category: '',
  description: '',
  estimatedWeight: '',
  address: '',
  latitude: '',
  longitude: '',
  imageUrls: [],
};

/**
 * Reusable submission form (create + edit).
 *
 * Validates with the shared Zod schema that mirrors the backend contract, so no
 * request is sent that the server would reject. Numeric fields are typed as
 * text and coerced on submit; `imageUrls` is a dynamic add/remove list of URL
 * strings (the backend accepts URLs, not file uploads). Errors are shown inline
 * and wired with aria-invalid / aria-describedby for assistive tech.
 */
export function SubmissionForm({
  defaultValues,
  onSubmit,
  isSubmitting = false,
  submitLabel,
  onCancel,
}: SubmissionFormProps) {
  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<SubmissionFormValues>({
    resolver: zodResolver(submissionFormSchema),
    defaultValues: { ...EMPTY_VALUES, ...defaultValues },
  });

  const { fields, append, remove } = useFieldArray({
    control,
    name: 'imageUrls',
  });

  const PlusIcon = icons.plus;
  const TrashIcon = icons.trash;

  const submit = handleSubmit((values) => {
    const payload: CreateSubmissionPayload = {
      category: values.category.trim(),
      estimatedWeight: Number(values.estimatedWeight),
      address: values.address.trim(),
      latitude: Number(values.latitude),
      longitude: Number(values.longitude),
      imageUrls: values.imageUrls.map((item) => item.value.trim()),
    };
    const description = values.description?.trim();
    if (description) payload.description = description;
    return onSubmit(payload);
  });

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <Label htmlFor="category">Category</Label>
        <Input
          id="category"
          placeholder="e.g. Laptop, Mobile, Monitor"
          aria-invalid={errors.category ? true : undefined}
          aria-describedby={errors.category ? 'category-error' : undefined}
          disabled={isSubmitting}
          {...register('category')}
        />
        {errors.category && (
          <p id="category-error" className="text-sm text-destructive">
            {errors.category.message}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="description">Description (optional)</Label>
        <Textarea
          id="description"
          rows={3}
          placeholder="Condition, brand, accessories, etc."
          aria-invalid={errors.description ? true : undefined}
          aria-describedby={errors.description ? 'description-error' : undefined}
          disabled={isSubmitting}
          {...register('description')}
        />
        {errors.description && (
          <p id="description-error" className="text-sm text-destructive">
            {errors.description.message}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="estimatedWeight">Estimated weight (kg)</Label>
        <Input
          id="estimatedWeight"
          type="number"
          inputMode="decimal"
          step="0.1"
          min="0"
          placeholder="e.g. 2.5"
          aria-invalid={errors.estimatedWeight ? true : undefined}
          aria-describedby={errors.estimatedWeight ? 'estimatedWeight-error' : undefined}
          disabled={isSubmitting}
          {...register('estimatedWeight')}
        />
        {errors.estimatedWeight && (
          <p id="estimatedWeight-error" className="text-sm text-destructive">
            {errors.estimatedWeight.message}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="address">Pickup address</Label>
        <Textarea
          id="address"
          rows={2}
          placeholder="Street, city, state, PIN"
          aria-invalid={errors.address ? true : undefined}
          aria-describedby={errors.address ? 'address-error' : undefined}
          disabled={isSubmitting}
          {...register('address')}
        />
        {errors.address && (
          <p id="address-error" className="text-sm text-destructive">
            {errors.address.message}
          </p>
        )}
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <Label htmlFor="latitude">Latitude</Label>
          <Input
            id="latitude"
            type="number"
            inputMode="decimal"
            step="any"
            placeholder="e.g. 12.9716"
            aria-invalid={errors.latitude ? true : undefined}
            aria-describedby={errors.latitude ? 'latitude-error' : undefined}
            disabled={isSubmitting}
            {...register('latitude')}
          />
          {errors.latitude && (
            <p id="latitude-error" className="text-sm text-destructive">
              {errors.latitude.message}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="longitude">Longitude</Label>
          <Input
            id="longitude"
            type="number"
            inputMode="decimal"
            step="any"
            placeholder="e.g. 77.5946"
            aria-invalid={errors.longitude ? true : undefined}
            aria-describedby={errors.longitude ? 'longitude-error' : undefined}
            disabled={isSubmitting}
            {...register('longitude')}
          />
          {errors.longitude && (
            <p id="longitude-error" className="text-sm text-destructive">
              {errors.longitude.message}
            </p>
          )}
        </div>
      </div>

      <fieldset className="flex flex-col gap-3" disabled={isSubmitting}>
        <div className="flex items-center justify-between gap-2">
          <legend className="text-sm font-medium leading-none">Image URLs (optional)</legend>
          <Button type="button" variant="outline" size="sm" onClick={() => append({ value: '' })}>
            <PlusIcon aria-hidden="true" />
            Add image URL
          </Button>
        </div>

        {fields.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No image URLs added. Paste links to photos of the device (uploads are not supported).
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {fields.map((field, index) => {
              const fieldError = errors.imageUrls?.[index]?.value;
              return (
                <li key={field.id} className="flex flex-col gap-1">
                  <div className="flex items-start gap-2">
                    <div className="flex-1">
                      <Label htmlFor={`imageUrls.${index}.value`} className="sr-only">
                        Image URL {index + 1}
                      </Label>
                      <Input
                        id={`imageUrls.${index}.value`}
                        type="url"
                        placeholder="https://example.com/device.jpg"
                        aria-invalid={fieldError ? true : undefined}
                        aria-describedby={fieldError ? `imageUrls-${index}-error` : undefined}
                        {...register(`imageUrls.${index}.value` as const)}
                      />
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => remove(index)}
                      aria-label={`Remove image URL ${index + 1}`}
                    >
                      <TrashIcon aria-hidden="true" />
                    </Button>
                  </div>
                  {fieldError && (
                    <p id={`imageUrls-${index}-error`} className="text-sm text-destructive">
                      {fieldError.message}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </fieldset>

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting && <icons.spinner className="animate-spin" aria-hidden="true" />}
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
