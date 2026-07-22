import { z } from 'zod';

/**
 * Request schemas for the submission module. Applied by the validate middleware
 * before controllers run — see docs/engineering/05_API.md (Validation Rules).
 */

const category = z.string().trim().min(2, 'Category is required').max(100);
const description = z.string().trim().max(2000).optional();
const estimatedWeight = z.number().positive('Estimated weight must be a positive number');
const address = z.string().trim().min(3, 'Address is required').max(500);
const latitude = z
  .number()
  .min(-90, 'Latitude must be between -90 and 90')
  .max(90, 'Latitude must be between -90 and 90');
const longitude = z
  .number()
  .min(-180, 'Longitude must be between -180 and 180')
  .max(180, 'Longitude must be between -180 and 180');
const imageUrls = z.array(z.string().url('Each image URL must be a valid URL')).max(20).optional();

export const createSubmissionSchema = z.object({
  category,
  description,
  estimatedWeight,
  address,
  latitude,
  longitude,
  imageUrls,
});

/** Every field is optional on update; at least one must be present. */
export const updateSubmissionSchema = z
  .object({
    category,
    description,
    estimatedWeight,
    address,
    latitude,
    longitude,
    imageUrls,
  })
  .partial()
  .refine((body) => Object.keys(body).length > 0, {
    message: 'At least one field must be provided',
  });

export const submissionIdSchema = z.object({
  id: z.string().uuid('A valid submission id is required'),
});

/**
 * Body for PATCH /submissions/:id/assign. The status-transition endpoints
 * (accept/start/complete) carry no body — they validate only the :id param.
 */
export const assignCollectorSchema = z.object({
  collectorId: z.string().uuid('A valid collector id is required'),
});

export type CreateSubmissionInput = z.infer<typeof createSubmissionSchema>;
export type UpdateSubmissionInput = z.infer<typeof updateSubmissionSchema>;
export type SubmissionIdParams = z.infer<typeof submissionIdSchema>;
export type AssignCollectorInput = z.infer<typeof assignCollectorSchema>;
