/**
 * Query key factory for TanStack Query.
 *
 * Using a single factory keeps cache keys consistent and makes targeted
 * invalidation straightforward. Extend per feature in future sprints.
 */
import type { PaginationParams } from '@/types';

/** Loose parameter bag accepted by list-style query keys (e.g. pagination). */
export type QueryKeyParams = Record<string, unknown> | PaginationParams | undefined;

export const queryKeys = {
  auth: {
    me: ['auth', 'me'] as const,
  },
  submissions: {
    all: ['submissions'] as const,
    list: (params?: QueryKeyParams) => ['submissions', 'list', params ?? {}] as const,
    detail: (id: string) => ['submissions', 'detail', id] as const,
  },
  rewards: {
    all: ['rewards'] as const,
    balance: ['rewards', 'balance'] as const,
    history: (params?: QueryKeyParams) => ['rewards', 'history', params ?? {}] as const,
  },
  collector: {
    all: ['collector'] as const,
    assignments: (params?: QueryKeyParams) => ['collector', 'assignments', params ?? {}] as const,
  },
  recycler: {
    all: ['recycler'] as const,
    assignments: (params?: QueryKeyParams) => ['recycler', 'assignments', params ?? {}] as const,
  },
  government: {
    all: ['government'] as const,
    overview: ['government', 'overview'] as const,
    regions: ['government', 'regions'] as const,
    environmentalImpact: ['government', 'environmental-impact'] as const,
    forecast: ['government', 'forecast'] as const,
  },
  admin: {
    all: ['admin'] as const,
    submissions: (params?: QueryKeyParams) => ['admin', 'submissions', params ?? {}] as const,
  },
  user: {
    profile: ['user', 'profile'] as const,
  },
} as const;
