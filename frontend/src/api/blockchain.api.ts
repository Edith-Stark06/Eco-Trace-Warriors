/**
 * Blockchain API module.
 *
 * Typed wrapper around the read-only blockchain health endpoint
 * (`backend/src/modules/blockchain/`, P6.5), which itself proxies to the
 * Python `intelligence/device_ai` service's Fabric Gateway health check
 * (P6.1/P6.2). Public — no auth required, mirrors `/health`/`/ready`.
 *
 * Implemented backend surface (verified from backend/src/modules/blockchain):
 *   GET /system/blockchain/health
 */
import { apiClient } from '@/api/axios';
import { unwrap } from '@/api/client';
import type { ApiSuccess, BlockchainHealth } from '@/types';

export const blockchainApi = {
  /** GET /system/blockchain/health — always resolves (backend degrades to
   *  `status: "proxy_unreachable"` rather than a 5xx when the upstream
   *  Fabric Gateway service can't be reached — see the report for P6.5). */
  getHealth: (): Promise<BlockchainHealth> =>
    unwrap<BlockchainHealth>(
      apiClient.get<ApiSuccess<BlockchainHealth>>('/system/blockchain/health'),
    ),
};
