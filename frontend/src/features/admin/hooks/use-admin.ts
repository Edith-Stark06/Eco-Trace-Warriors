/**
 * Admin data hooks.
 *
 * TanStack Query wrappers around the admin API. The submissions query uses the
 * central key factory so the issue-reward mutation can invalidate it precisely.
 * Mutations never refetch manually — they invalidate and let Query refetch what
 * is observed.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { adminApi } from '@/api/admin.api';
import { queryKeys } from '@/lib/query-keys';
import type { PaginationParams } from '@/types';

/** All submissions across every user (admin-scoped GET /submissions). */
export function useAdminSubmissions(params?: PaginationParams) {
  return useQuery({
    queryKey: queryKeys.admin.submissions(params),
    queryFn: () => adminApi.listAllSubmissions(params),
  });
}

/** Active collectors eligible for assignment (GET /users?role=COLLECTOR). */
export function useCollectors() {
  return useQuery({
    queryKey: queryKeys.admin.collectors,
    queryFn: () => adminApi.listUsersByRole('COLLECTOR'),
  });
}

/** Active recyclers eligible for assignment (GET /users?role=RECYCLER). */
export function useRecyclers() {
  return useQuery({
    queryKey: queryKeys.admin.recyclers,
    queryFn: () => adminApi.listUsersByRole('RECYCLER'),
  });
}

/**
 * Manually issue a reward for a RECYCLED submission (POST /rewards/issue/:id).
 * On success, invalidates the admin submissions list so the table reflects any
 * status changes surfaced by the backend.
 */
export function useIssueReward() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (submissionId: string) => adminApi.issueReward(submissionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
    },
  });
}

/** Assign a collector to a PENDING submission (PATCH /submissions/:id/assign). */
export function useAssignCollector() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ submissionId, collectorId }: { submissionId: string; collectorId: string }) =>
      adminApi.assignCollector(submissionId, collectorId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
    },
  });
}

/** Assign a recycler to a COLLECTED submission (PATCH /submissions/:id/assign-recycler). */
export function useAssignRecycler() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ submissionId, recyclerId }: { submissionId: string; recyclerId: string }) =>
      adminApi.assignRecycler(submissionId, recyclerId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
    },
  });
}
