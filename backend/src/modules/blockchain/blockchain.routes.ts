import { Router } from 'express';
import type { BlockchainController } from './blockchain.controller';

/**
 * Mounts the blockchain module routes. Public, like `/health`/`/ready` —
 * this reports infrastructure connectivity, not user data, and read-only
 * status checks are not a resource worth gating behind auth.
 */
export function createBlockchainRouter(controller: BlockchainController): Router {
  const router = Router();
  router.get('/system/blockchain/health', (req, res, next) => {
    controller.getHealth(req, res).catch(next);
  });
  return router;
}
