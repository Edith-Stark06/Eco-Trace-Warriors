/**
 * Blockchain monitoring data hook (P6.6).
 *
 * A short `refetchInterval` keeps the admin dashboard's connectivity card
 * live without a manual refresh — this is a lightweight status poll, not a
 * transaction, so polling is safe and matches the read-only nature of the
 * endpoint it calls (`backend/src/modules/blockchain/`, P6.5).
 */
import { useQuery } from '@tanstack/react-query';
import { blockchainApi } from '@/api/blockchain.api';
import { queryKeys } from '@/lib/query-keys';

const POLL_INTERVAL_MS = 30_000;

export function useBlockchainHealth() {
  return useQuery({
    queryKey: queryKeys.blockchain.health,
    queryFn: () => blockchainApi.getHealth(),
    refetchInterval: POLL_INTERVAL_MS,
    // A degraded/unreachable Fabric Gateway is a normal, expected status
    // value (see blockchainApi.getHealth's doc comment) — never an error
    // this query should retry aggressively.
    retry: 1,
  });
}
