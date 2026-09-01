import { EcoTraceLifecycleContract } from './ecotrace-lifecycle';

/**
 * fabric-shim's bootstrap (contract-spi/bootstrap.js) requires package.json's
 * "main" module to expose a `contracts` array of contract classes — a plain
 * named export (as used by the unit tests and the fake gateway server) isn't
 * enough; without it, fabric-shim wraps the whole module object as if it were
 * a single contract class and fails with "contractClass is not a constructor".
 * This is the real chaincode server entrypoint (P9.2); it does not change the
 * contract itself, only how the peer/fabric-chaincode-node discovers it.
 */
export const contracts = [EcoTraceLifecycleContract];
export { EcoTraceLifecycleContract };
