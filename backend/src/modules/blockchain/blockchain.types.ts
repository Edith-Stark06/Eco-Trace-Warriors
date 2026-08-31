import type { SuccessResponse } from '../../types';

/**
 * Blockchain connectivity status as reported by the Python
 * `intelligence/device_ai` service's `GET /system/blockchain/health`
 * (P6.2 — `intelligence/device_ai/api/blockchain_routes.py`).
 *
 * This backend does not itself hold a Fabric connection — the working
 * Fabric Gateway client lives in that Python service (P6.1/P6.2). This
 * module is a thin, read-only proxy so a caller of *this* API (the mobile
 * apps, the admin dashboard) does not need to know that service exists or
 * where it runs. It is intentionally read-only: it forwards a health
 * check, never a transaction (see `BlockchainService.getHealth`).
 */
export interface BlockchainHealth {
  /** One of: disabled | configuration_error | unavailable | connected | proxy_unreachable. */
  readonly status: string;
  readonly fabricEnabled: boolean | null;
  readonly channel: string | null;
  readonly chaincode: string | null;
  readonly mspId: string | null;
  readonly peerEndpoint: string | null;
  readonly message: string;
  readonly checkedAt: string;
  readonly latencyMs: number | null;
}

export type BlockchainHealthResponse = SuccessResponse<BlockchainHealth>;
