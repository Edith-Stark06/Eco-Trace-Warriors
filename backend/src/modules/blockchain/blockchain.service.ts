import type { Logger } from '@shared/logging';
import type { BlockchainHealth } from './blockchain.types';

/** Dependencies injected into the blockchain service. */
export interface BlockchainServiceDeps {
  /** Base URL of the Python `intelligence/device_ai` service (P6.1/P6.2's
   *  working Fabric Gateway integration lives there — see
   *  `intelligence/device_ai/api/blockchain_routes.py`). */
  readonly deviceAiServiceUrl: string;
  /** Request timeout in milliseconds for the proxied health check. */
  readonly timeoutMs: number;
  readonly logger: Logger;
  /** Test seam: injectable fetch implementation. Defaults to global `fetch`
   *  (Node 18+ built-in — no new HTTP client dependency needed). */
  readonly fetchImpl?: typeof fetch;
}

export interface BlockchainService {
  /**
   * Proxies the Python AI service's `GET /system/blockchain/health`.
   * Read-only: never submits a chaincode transaction, never touches the
   * database. Degrades gracefully — a network failure or timeout reaching
   * the AI service becomes `status: "proxy_unreachable"` in the response,
   * never a thrown error, matching this backend's existing "AI calls are
   * advisory" degradation philosophy (`infrastructure/ai/ai.client.ts`).
   */
  getHealth(): Promise<BlockchainHealth>;
}

const UNREACHABLE_MESSAGE = 'Could not reach the device intelligence / Fabric Gateway service.';

export function createBlockchainService(deps: BlockchainServiceDeps): BlockchainService {
  const fetchFn = deps.fetchImpl ?? fetch;

  return {
    async getHealth(): Promise<BlockchainHealth> {
      const url = `${deps.deviceAiServiceUrl.replace(/\/+$/, '')}/system/blockchain/health`;

      try {
        const response = await fetchFn(url, {
          method: 'GET',
          signal: AbortSignal.timeout(deps.timeoutMs),
        });

        if (!response.ok) {
          deps.logger.warn(
            { url, status: response.status },
            'Blockchain health proxy received a non-OK response',
          );
          return unreachable(`Device AI service responded with HTTP ${response.status}.`);
        }

        const body = (await response.json()) as {
          health?: {
            status?: string;
            fabric_enabled?: boolean;
            channel?: string;
            chaincode?: string;
            msp_id?: string;
            peer_endpoint?: string;
            message?: string;
            checked_at?: string;
            latency_ms?: number | null;
          };
        };

        const health = body.health;
        if (!health) {
          deps.logger.warn({ url }, 'Blockchain health proxy received an unexpected payload shape');
          return unreachable('Device AI service returned an unexpected response shape.');
        }

        return {
          status: health.status ?? 'unavailable',
          fabricEnabled: health.fabric_enabled ?? null,
          channel: health.channel ?? null,
          chaincode: health.chaincode ?? null,
          mspId: health.msp_id ?? null,
          peerEndpoint: health.peer_endpoint ?? null,
          message: health.message ?? '',
          checkedAt: health.checked_at ?? new Date().toISOString(),
          latencyMs: health.latency_ms ?? null,
        };
      } catch (error) {
        deps.logger.warn({ url, err: error }, 'Blockchain health proxy request failed');
        return unreachable(UNREACHABLE_MESSAGE);
      }
    },
  };
}

function unreachable(message: string): BlockchainHealth {
  return {
    status: 'proxy_unreachable',
    fabricEnabled: null,
    channel: null,
    chaincode: null,
    mspId: null,
    peerEndpoint: null,
    message,
    checkedAt: new Date().toISOString(),
    latencyMs: null,
  };
}
