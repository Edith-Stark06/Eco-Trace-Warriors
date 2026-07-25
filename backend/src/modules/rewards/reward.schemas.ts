import { z } from 'zod';

export const rewardSubmissionIdSchema = z.object({
  submissionId: z.string().uuid('A valid submission id is required'),
});

export type RewardSubmissionIdParams = z.infer<typeof rewardSubmissionIdSchema>;
