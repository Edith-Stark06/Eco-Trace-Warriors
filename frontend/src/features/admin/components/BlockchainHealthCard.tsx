import { ContentCard } from '@/components/dashboard/ContentCard';
import { SkeletonCards } from '@/components/dashboard/SkeletonCards';
import { ServerError } from '@/components/common/ServerError';
import { Badge } from '@/components/ui/badge';
import { StatCard } from '@/components/dashboard/StatCard';
import { useBlockchainHealth } from '@/features/admin/hooks/use-blockchain';

/**
 * Live Fabric Gateway connectivity — polls
 * `GET /system/blockchain/health` (P6.5, itself a real proxy through to the
 * P6.1/P6.2 Fabric Gateway client; never a fabricated status). Every status
 * value below is one the backend can actually report; none are invented for
 * this UI.
 */
const STATUS_LABEL: Record<string, string> = {
  connected: 'Connected',
  disabled: 'Disabled',
  configuration_error: 'Configuration error',
  unavailable: 'Peer unreachable',
  proxy_unreachable: 'Backend proxy unreachable',
};

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  connected: 'default',
  disabled: 'secondary',
  configuration_error: 'destructive',
  unavailable: 'destructive',
  proxy_unreachable: 'destructive',
};

export function BlockchainHealthCard() {
  const { data, isPending, isError, refetch, dataUpdatedAt } = useBlockchainHealth();

  if (isPending) {
    return <SkeletonCards count={1} />;
  }

  if (isError || !data) {
    return <ServerError onRetry={() => void refetch()} />;
  }

  const label = STATUS_LABEL[data.status] ?? data.status;
  const variant = STATUS_VARIANT[data.status] ?? 'secondary';

  return (
    <ContentCard>
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">Fabric Gateway status</span>
            <Badge variant={variant}>{label}</Badge>
          </div>
          <span className="text-xs text-muted-foreground" aria-live="polite">
            Last checked {new Date(dataUpdatedAt).toLocaleTimeString()}
          </span>
        </div>

        <p className="text-sm text-muted-foreground">{data.message}</p>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Channel" value={data.channel ?? '—'} />
          <StatCard label="Chaincode" value={data.chaincode ?? '—'} />
          <StatCard label="MSP ID" value={data.mspId ?? '—'} />
          <StatCard
            label="Latency"
            value={data.latencyMs != null ? `${data.latencyMs.toFixed(1)} ms` : '—'}
          />
        </div>
      </div>
    </ContentCard>
  );
}
