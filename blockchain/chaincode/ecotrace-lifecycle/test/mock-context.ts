/**
 * Mock Fabric Context and Stub for Chaincode Unit Testing
 *
 * Provides a testable in-memory implementation of the Fabric Contract API
 * surfaces used by the chaincode, without requiring a live Fabric network.
 *
 * The mock is typed against the installed `fabric-contract-api` / `fabric-shim-api`
 * declarations so the contract itself type-checks when exercised through it.
 * Surfaces that the contract never touches (private data, transient map, etc.)
 * are stubbed minimally.
 */

import { Context } from 'fabric-contract-api';
import type { ChaincodeStub, ClientIdentity } from 'fabric-shim-api';

/**
 * Mock ClientIdentity for testing authorization.
 */
export class MockClientIdentity implements ClientIdentity {
  private mspId: string;
  private id: string;
  private attributes: Map<string, string>;

  constructor(mspId: string = 'EcoTraceOrg', id: string = 'admin', attributes: Map<string, string> = new Map()) {
    this.mspId = mspId;
    this.id = id;
    this.attributes = attributes;
  }

  getMSPID(): string {
    return this.mspId;
  }

  getID(): string {
    return this.id;
  }

  getIDBytes(): Uint8Array {
    return Buffer.from(this.id);
  }

  getAttributeValue(attrName: string): string | null {
    return this.attributes.get(attrName) || null;
  }

  assertAttributeValue(attrName: string, attrValue: string): boolean {
    return this.attributes.get(attrName) === attrValue;
  }

  getX509Certificate(): string {
    return 'mock-certificate';
  }
}

/**
 * Mock Transaction Timestamp (seconds as a Long-like {low, high}).
 */
export interface MockTimestamp {
  seconds: { low: number; high: number };
  nanos: number;
}

/**
 * Mock State Entry.
 */
interface MockStateEntry {
  key: string;
  value: Buffer;
}

/**
 * Mock State Iterator (minimal next/close).
 */
export class MockStateIterator {
  private entries: MockStateEntry[];
  private index: number = 0;
  private closed: boolean = false;

  constructor(entries: MockStateEntry[]) {
    this.entries = entries;
  }

  async next(): Promise<{ done: boolean; value?: MockStateEntry }> {
    if (this.closed) {
      throw new Error('Iterator is closed');
    }
    if (this.index >= this.entries.length) {
      return { done: true };
    }
    return { done: false, value: this.entries[this.index++] };
  }

  async close(): Promise<void> {
    this.closed = true;
  }
}

/**
 * Mock Stub for Chaincode Testing.
 *
 * Implements the ChaincodeStub surface the contract relies on: state CRUD,
 * range queries, events, tx id/timestamp, and client identity. Not declared
 * `implements ChaincodeStub` — the contract only ever sees it through the
 * `Context.stub` typing (a ChaincodeStub), and the runtime shape matches.
 */
export class MockStub {
  private state: Map<string, Buffer> = new Map();
  private events: Map<string, Buffer> = new Map();
  private txId: string;
  private timestamp: MockTimestamp;
  private clientIdentity: MockClientIdentity;

  constructor(
    txId: string = 'mock-tx-0001',
    timestamp?: MockTimestamp,
    mspId: string = 'EcoTraceOrg',
    userId: string = 'admin'
  ) {
    this.txId = txId;
    this.timestamp = timestamp || {
      seconds: { low: 1_700_000_000, high: 0 },
      nanos: 0,
    };
    this.clientIdentity = new MockClientIdentity(mspId, userId);
  }

  // State operations
  async getState(key: string): Promise<Buffer> {
    const value = this.state.get(key);
    return value || Buffer.alloc(0);
  }

  async putState(key: string, value: Buffer): Promise<void> {
    this.state.set(key, value);
  }

  async deleteState(key: string): Promise<void> {
    this.state.delete(key);
  }

  async getStateByRange(startKey: string, endKey: string): Promise<MockStateIterator> {
    const entries: MockStateEntry[] = [];
    for (const [key, value] of this.state.entries()) {
      if (key >= startKey && key < endKey) {
        entries.push({ key, value });
      }
    }
    return new MockStateIterator(entries);
  }

  // Events
  setEvent(name: string, payload: Buffer): void {
    this.events.set(name, payload);
  }

  // Getters
  getTxID(): string {
    return this.txId;
  }

  getTxTimestamp(): MockTimestamp {
    return this.timestamp;
  }

  getClientIdentity(): MockClientIdentity {
    return this.clientIdentity;
  }

  // Test helpers
  getStateMap(): Map<string, Buffer> {
    return this.state;
  }

  getEvents(): Map<string, Buffer> {
    return this.events;
  }

  clear(): void {
    this.state.clear();
    this.events.clear();
  }

  setTimestamp(seconds: number): void {
    this.timestamp = { seconds: { low: seconds, high: 0 }, nanos: 0 };
  }

  setClientIdentity(mspId: string, userId: string): void {
    this.clientIdentity = new MockClientIdentity(mspId, userId);
  }
}

/**
 * Mock Context for Chaincode Testing.
 *
 * Satisfies `Context` structurally (public `stub`, `clientIdentity`, `logging`)
 * so the contract's `ctx.stub` / `ctx.clientIdentity` access works and type-checks.
 */
export class MockContext implements Context {
  stub: ChaincodeStub;
  clientIdentity: ClientIdentity;
  logging = {
    setLevel: (): void => {},
    getLogger: (): object => ({}),
  } as unknown as Context['logging'];

  private mockStub: MockStub;

  constructor(stub?: MockStub) {
    this.mockStub = stub || new MockStub();
    // The runtime MockStub is a valid stand-in for the ChaincodeStub contract.
    this.stub = this.mockStub as unknown as ChaincodeStub;
    this.clientIdentity = this.mockStub.getClientIdentity();
  }

  getStub(): ChaincodeStub {
    return this.stub;
  }

  getClientIdentity(): ClientIdentity {
    return this.clientIdentity;
  }

  getFunction(): string {
    return '';
  }

  getParameters(): string[] {
    return [];
  }

  // Test helpers
  getMockStub(): MockStub {
    return this.mockStub;
  }

  setClientIdentity(mspId: string, userId: string): void {
    this.mockStub.setClientIdentity(mspId, userId);
    this.clientIdentity = this.mockStub.getClientIdentity();
  }
}

/**
 * Create a mock context with a fixed, deterministic transaction timestamp.
 * Deterministic timestamps make serialization/response tests reproducible.
 *
 * @param seconds Unix epoch seconds for the transaction timestamp
 * @param mspId MSP id for the submitting identity
 * @param userId Identity id for the submitting identity
 * @param txId Transaction id
 * @returns A configured MockContext
 */
export function createMockContext(
  seconds: number = 1_700_000_000,
  mspId: string = 'EcoTraceOrg',
  userId: string = 'platform-admin',
  txId: string = 'mock-tx-0001'
): MockContext {
  const stub = new MockStub(txId, { seconds: { low: seconds, high: 0 }, nanos: 0 }, mspId, userId);
  return new MockContext(stub);
}
