/**
 * Hyperledger Fabric client provider — Phase 7 (Blockchain).
 *
 * The backend is the sole Fabric gateway (docs/engineering/03_ARCHITECTURE.md, ADR-002).
 * This interface defines the seam services will depend on; the implementation
 * (connection profile, identities, outbox/retry) arrives in Phase 7 per
 * docs/engineering/09_BLOCKCHAIN.md.
 */
export interface FabricClient {
  /** Submits a lifecycle transaction and resolves with the transaction ID. */
  submitTransaction(functionName: string, ...args: string[]): Promise<string>;
  /** Evaluates a read-only chaincode query. */
  evaluateTransaction(functionName: string, ...args: string[]): Promise<string>;
}

/** Placeholder until Phase 7: fails loudly if used before the Fabric layer exists. */
export function createFabricClient(): FabricClient {
  return {
    submitTransaction: () =>
      Promise.reject(new Error('Fabric client is not available until Phase 7 (Blockchain).')),
    evaluateTransaction: () =>
      Promise.reject(new Error('Fabric client is not available until Phase 7 (Blockchain).')),
  };
}
