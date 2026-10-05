/**
 * Mirrors `BlockchainHealth` (`backend/src/modules/blockchain/blockchain.types.ts`,
 * P6.5) — a read-only proxy of the Python `intelligence/device_ai` service's
 * Fabric Gateway health check (P6.1/P6.2).
 */
export interface BlockchainHealth {
  /** One of: disabled | configuration_error | unavailable | connected | proxy_unreachable. */
  status: string;
  fabricEnabled: boolean | null;
  channel: string | null;
  chaincode: string | null;
  mspId: string | null;
  peerEndpoint: string | null;
  message: string;
  checkedAt: string;
  latencyMs: number | null;
}
