/**
 * Consumer submission form validation.
 *
 * Mirrors the backend `createSubmissionSchema`
 * (backend/src/modules/submission/submission.schemas.ts) so the client rejects
 * exactly what the server would — no request is sent that the backend will
 * refuse. Client validation is UX only; the server re-validates and is the
 * authority.
 *
 * The form models numeric fields as strings (native inputs yield strings) and
 * coerces on submit, so an empty field shows a "required" message rather than a
 * confusing "expected number" error. `imageUrls` is a dynamic list of URL
 * strings — the backend accepts URLs, never file uploads.
 */
import { z } from 'zod';

/** A required numeric text field with a friendly empty-state message. */
function numericField(label: string) {
  return z
    .string()
    .trim()
    .min(1, `${label} is required`)
    .refine((value) => Number.isFinite(Number(value)), `${label} must be a number`);
}

export const submissionFormSchema = z.object({
  category: z
    .string()
    .trim()
    .min(2, 'Category is required')
    .max(100, 'Category must be at most 100 characters'),
  description: z
    .string()
    .trim()
    .max(2000, 'Description must be at most 2000 characters')
    .optional(),
  estimatedWeight: numericField('Estimated weight').refine(
    (value) => Number(value) > 0,
    'Estimated weight must be a positive number',
  ),
  address: z
    .string()
    .trim()
    .min(3, 'Address is required')
    .max(500, 'Address must be at most 500 characters'),
  latitude: numericField('Latitude').refine((value) => {
    const n = Number(value);
    return n >= -90 && n <= 90;
  }, 'Latitude must be between -90 and 90'),
  longitude: numericField('Longitude').refine((value) => {
    const n = Number(value);
    return n >= -180 && n <= 180;
  }, 'Longitude must be between -180 and 180'),
  imageUrls: z
    .array(
      z.object({
        value: z.string().trim().url('Each image URL must be a valid URL'),
      }),
    )
    .max(20, 'At most 20 image URLs are allowed'),
});

export type SubmissionFormValues = z.infer<typeof submissionFormSchema>;
