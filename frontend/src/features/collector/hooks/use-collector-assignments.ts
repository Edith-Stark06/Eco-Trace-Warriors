/**
 * Collector data hooks.
 *
 * TanStack Query wrappers around the collector API. The assignment queue query
 * shares the central key factory so every workflow mutation can invalidate it
 * precisely; mutations never refetch manually — they invalidate the collector
 * queries and let Query refetch what is observed.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { collectorApi } from '@/api/collector.api';
import { queryKeys } from '@/lib/query-keys';
import type { PaginationParams } from '@/types';

/** The authenticated collector's active assignment queue. */
export function useCollectorAssignments(params?: PaginationParams) {
  return useQuery({
    queryKey: queryKeys.collector.assignments(params),
    queryFn: () => collectorApi.getAssignments(params),
  });
}

/**
 * Shared invalidation for every workflow transition. A successful accept /
 * start / complete changes the assignment's status, which can add or remove it
 * from the active queue — so we invalidate all collector queries and let Query
 * refetch the observed ones.
 */
function useInvalidateCollectorAssignments() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.collector.all });
}

/** Accept an assignment (ASSIGNED → ACCEPTED), then refresh the queue. */
export function useAcceptAssignment() {
  const invalidate = useInvalidateCollectorAssignments();
  return useMutation({
    mutationFn: (id: string) => collectorApi.acceptAssignment(id),
    onSuccess: () => {
      void invalidate();
    },
  });
}

/** Start a pickup (ACCEPTED → IN_PROGRESS), then refresh the queue. */
export function useStartPickup() {
  const invalidate = useInvalidateCollectorAssignments();
  return useMutation({
    mutationFn: (id: string) => collectorApi.startPickup(id),
    onSuccess: () => {
      void invalidate();
    },
  });
}

/** Complete a pickup (IN_PROGRESS → COLLECTED), then refresh the queue. */
export function useCompletePickup() {
  const invalidate = useInvalidateCollectorAssignments();
  return useMutation({
    mutationFn: (id: string) => collectorApi.completePickup(id),
    onSuccess: () => {
      void invalidate();
    },
  });
}
