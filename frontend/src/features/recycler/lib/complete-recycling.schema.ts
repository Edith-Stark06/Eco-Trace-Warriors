/**
 * Complete-recycling form validation & payload conversion.
 *
 * Mirrors the backend `completeRecyclingSchema`
 * (backend/src/modules/submission/submission.schemas.ts) so the client rejects
 * exactly what the server would — no request is sent that the backend will
 * refuse. Client validation is UX only; the server re-validates and is the
 * authority. Reward values are always computed by the backend and never here.
 *
 * Numeric inputs are modelled as strings (native inputs yield strings) and
 * coerced on submit, so an empty field shows a "required" message rather than a
 * confusing "expected number" error. `materials` is a dynamic add/remove list
 * that is folded into the `materialRecovery` record the backend expects.
 */
import { z } from 'zod';
import type { CompleteRecyclingPayload, MaterialRecovery } from '@/types';

/** A single dynamic material-recovery row. */
const materialRow = z.object({
  name: z
    .string()
    .trim()
    .min(1, 'Material name is required')
    .max(100, 'Material name must be at most 100 characters'),
  weight: z
    .string()
    .trim()
    .min(1, 'Weight is required')
    .refine((value) => Number.isFinite(Number(value)), 'Weight must be a number')
    .refine((value) => Number(value) >= 0, 'Weight must be zero or greater'),
});

export const completeRecyclingFormSchema = z
  .object({
    recoveredWeight: z
      .string()
      .trim()
      .min(1, 'Recovered weight is required')
      .refine((value) => Number.isFinite(Number(value)), 'Recovered weight must be a number')
      .refine((value) => Number(value) > 0, 'Recovered weight must be a positive number'),
    recyclerNotes: z.string().trim().max(2000, 'Notes must be at most 2000 characters').optional(),
    materials: z.array(materialRow),
  })
  .superRefine((values, ctx) => {
    // Reject duplicate material names (case-insensitive) — the backend record is
    // keyed by name, so duplicates would silently overwrite each other.
    const seen = new Map<string, number>();
    values.materials.forEach((material, index) => {
      const key = material.name.trim().toLowerCase();
      if (!key) return;
      if (seen.has(key)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Duplicate material name',
          path: ['materials', index, 'name'],
        });
      } else {
        seen.set(key, index);
      }
    });
  });

export type CompleteRecyclingFormValues = z.infer<typeof completeRecyclingFormSchema>;

/** Blank form state: a required weight and no material rows. */
export const EMPTY_COMPLETE_RECYCLING_VALUES: CompleteRecyclingFormValues = {
  recoveredWeight: '',
  recyclerNotes: '',
  materials: [],
};

/**
 * Fold validated form values into the backend request body. Numeric strings are
 * coerced to numbers; the dynamic material list becomes a `materialRecovery`
 * record ({ Copper: 2.4, Plastic: 3.7 }); empty optional fields are omitted so
 * the request carries only meaningful data.
 */
export function toCompleteRecyclingPayload(
  values: CompleteRecyclingFormValues,
): CompleteRecyclingPayload {
  const payload: CompleteRecyclingPayload = {
    recoveredWeight: Number(values.recoveredWeight),
  };

  const notes = values.recyclerNotes?.trim();
  if (notes) payload.recyclerNotes = notes;

  if (values.materials.length > 0) {
    const materialRecovery: MaterialRecovery = {};
    for (const material of values.materials) {
      materialRecovery[material.name.trim()] = Number(material.weight);
    }
    payload.materialRecovery = materialRecovery;
  }

  return payload;
}
