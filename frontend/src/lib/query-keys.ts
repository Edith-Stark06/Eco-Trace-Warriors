/**
 * Query key factory for TanStack Query.
 *
 * Using a single factory keeps cache keys consistent and makes targeted
 * invalidation straightforward. Extend per feature in future sprints.
 */
export const queryKeys = {
  auth: {
    me: ['auth', 'me'] as const,
  },
  submissions: {
    all: ['submissions'] as const,
    list: (params?: Record<string, unknown>) => ['submissions', 'list', params ?? {}] as const,
    detail: (id: string) => ['submissions', 'detail', id] as const,
  },
  rewards: {
    balance: ['rewards', 'balance'] as const,
    transactions: ['rewards', 'transactions'] as const,
  },
  user: {
    profile: ['user', 'profile'] as const,
  },
} as const;
