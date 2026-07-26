/**
 * Submission data hooks.
 *
 * TanStack Query wrappers around the submission API. Queries share the central
 * key factory so mutations can invalidate them precisely; mutations never
 * refetch manually — they invalidate and let Query refetch what is observed.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { submissionApi } from '@/api/submission.api';
import { queryKeys } from '@/lib/query-keys';
import type {
  CreateSubmissionPayload,
  PaginationParams,
  Submission,
  UpdateSubmissionPayload,
} from '@/types';

/** List the caller's submissions. */
export function useSubmissions(params?: PaginationParams) {
  return useQuery({
    queryKey: queryKeys.submissions.list(params),
    queryFn: () => submissionApi.list(params),
  });
}

/** Fetch a single submission by id. Disabled until an id is available. */
export function useSubmission(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.submissions.detail(id ?? ''),
    queryFn: () => submissionApi.getById(id as string),
    enabled: Boolean(id),
  });
}

/** Create a submission, then refresh submission lists and reward balance. */
export function useCreateSubmission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateSubmissionPayload) => submissionApi.create(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.submissions.all });
    },
  });
}

/** Update a submission, then refresh its detail and any submission lists. */
export function useUpdateSubmission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: UpdateSubmissionPayload }) =>
      submissionApi.update(id, payload),
    onSuccess: (updated: Submission) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.submissions.all });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.submissions.detail(updated.id),
      });
    },
  });
}

/** Delete a submission, then refresh submission lists. */
export function useDeleteSubmission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => submissionApi.remove(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.submissions.all });
    },
  });
}
