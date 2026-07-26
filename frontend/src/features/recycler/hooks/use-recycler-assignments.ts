/**
 * Recycler data hooks.
 *
 * TanStack Query wrappers around the recycler API. The assignment queue query
 * shares the central key factory so every workflow mutation can invalidate it
 * precisely; mutations never refetch manually — they invalidate the recycler
 * queries and let Query refetch what is observed.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { recyclerApi } from '@/api/recycler.api';
import { queryKeys } from '@/lib/query-keys';
import type { CompleteRecyclingPayload, PaginationParams } from '@/types';

/** The authenticated recycler's active assignment queue. */
export function useRecyclerAssignments(params?: PaginationParams) {
  return useQuery({
    queryKey: queryKeys.recycler.assignments(params),
    queryFn: () => recyclerApi.getAssignments(params),
  });
}

/**
 * Shared invalidation for every workflow transition. A successful start /
 * complete changes the assignment's status, which can remove it from the active
 * queue — so we invalidate all recycler queries and let Query refetch the
 * observed ones.
 */
function useInvalidateRecyclerAssignments() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.recycler.all });
}

/** Start recycling (COLLECTED → RECYCLING), then refresh the queue. */
export function useStartRecycling() {
  const invalidate = useInvalidateRecyclerAssignments();
  return useMutation({
    mutationFn: (id: string) => recyclerApi.startRecycling(id),
    onSuccess: () => {
      void invalidate();
    },
  });
}

/** Arguments for completing a recycling job. */
export interface CompleteRecyclingArgs {
  id: string;
  body: CompleteRecyclingPayload;
}

/**
 * Complete recycling (RECYCLING → RECYCLED), then refresh the queue. Resolves to
 * the backend `{ submission, reward }` payload so the caller can show the
 * reward success dialog with authoritative values.
 */
export function useCompleteRecycling() {
  const invalidate = useInvalidateRecyclerAssignments();
  return useMutation({
    mutationFn: ({ id, body }: CompleteRecyclingArgs) => recyclerApi.completeRecycling(id, body),
    onSuccess: () => {
      void invalidate();
    },
  });
}
