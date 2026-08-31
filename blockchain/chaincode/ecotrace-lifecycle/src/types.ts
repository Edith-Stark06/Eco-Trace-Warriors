/**
 * EcoTrace Device Lifecycle Chaincode Types
 *
 * P6.1 — Hyperledger Fabric Chaincode for EcoTrace Device Lifecycle Management
 *
 * Domain models, enums, and interfaces for the on-chain contract.
 *
 * Terminology follows the P5 device-registration domain
 * (`intelligence/device_ai/devices/models.py`):
 *   - `RegistrationState`: DETECTED -> CONFIRMED -> REGISTERED
 *   - `DeviceEventType`: DEVICE_DETECTED / DEVICE_CONFIRMED / DEVICE_REGISTERED /
 *     DEVICE_ENRICHED / DEVICE_EXTERNALLY_ANCHORED
 *
 * The taxonomy is the authoritative 19-class device-detection taxonomy loaded
 * by `load_taxonomy()` (`intelligence/device_ai/dataset/taxonomy.py`, source of
 * truth `components/data/components.yaml`, version 1.0.0). It is mirrored here
 * as a frozen constant because the chaincode is an isolated TypeScript contract.
 *
 * @packageDocumentation
 */

/**
 * On-chain lifecycle states for a device.
 *
 * Mirrors the P5 off-chain registration lifecycle (DETECTED -> CONFIRMED ->
 * REGISTERED) extended with the ENRICHED stage. The chaincode enforces strict
 * forward progression so the ledger never records an event that did not occur
 * off-chain: every transition must be accompanied by a record hash anchoring
 * the corresponding off-chain record.
 */
export enum LifecycleState {
  /** Device has been detected (off-chain CV detection confirmed for anchoring). */
  DETECTED = 'DETECTED',
  /** Device has been manually confirmed by an operator. */
  CONFIRMED = 'CONFIRMED',
  /** Device has been registered in the EcoTrace ecosystem. */
  REGISTERED = 'REGISTERED',
  /** Device passport has been enriched (brand, condition, materials, carbon). */
  ENRICHED = 'ENRICHED',
}

/**
 * The lifecycle state a device enters on registration.
 * Devices are anchored on-chain from the DETECTED stage, mirroring the P5
 * off-chain entry point, then progress via UpdateLifecycle.
 */
export const INITIAL_LIFECYCLE_STATE: LifecycleState = LifecycleState.DETECTED;

/**
 * Valid lifecycle state transitions on-chain.
 * Key: current state -> allowed next states (strict forward progression).
 */
export const VALID_LIFECYCLE_TRANSITIONS: ReadonlyMap<LifecycleState, ReadonlySet<LifecycleState>> = new Map([
  [LifecycleState.DETECTED, new Set([LifecycleState.CONFIRMED])],
  [LifecycleState.CONFIRMED, new Set([LifecycleState.REGISTERED])],
  [LifecycleState.REGISTERED, new Set([LifecycleState.ENRICHED])],
  [LifecycleState.ENRICHED, new Set()], // Terminal state for P6.1
]);

/**
 * Stored audit-event types, mirroring the P5 `DeviceEventType` vocabulary.
 * These label the immutable `LifecycleEvent` records persisted in the ledger.
 */
export enum DeviceEventType {
  DEVICE_DETECTED = 'DEVICE_DETECTED',
  DEVICE_CONFIRMED = 'DEVICE_CONFIRMED',
  DEVICE_REGISTERED = 'DEVICE_REGISTERED',
  DEVICE_ENRICHED = 'DEVICE_ENRICHED',
  DEVICE_EXTERNALLY_ANCHORED = 'DEVICE_EXTERNALLY_ANCHORED',
}

/**
 * Chaincode events emitted via `stub.setEvent` for important mutations.
 * Deterministic names with minimal payloads (device id + relevant fields).
 */
export enum ChaincodeEventType {
  /** Device asset registered on-chain (initial anchor). */
  DEVICE_REGISTERED = 'DEVICE_REGISTERED',
  /** Device lifecycle state transitioned (payload carries prev/new state). */
  DEVICE_LIFECYCLE_UPDATED = 'DEVICE_LIFECYCLE_UPDATED',
  /** Passport fingerprint (re-)anchored on-chain. */
  PASSPORT_ANCHORED = 'PASSPORT_ANCHORED',
}

/**
 * Actor roles that may perform on-chain actions.
 * Used for authorization and the immutable audit trail.
 */
export enum ActorRole {
  /** Platform operator / system (registration authority). */
  PLATFORM = 'PLATFORM',
  /** Authorized e-waste collector. */
  COLLECTOR = 'COLLECTOR',
  /** Recycling facility operator. */
  RECYCLER = 'RECYCLER',
  /** Government auditor / regulator (read/verify authority). */
  GOVERNMENT = 'GOVERNMENT',
  /** Device owner / consumer. */
  OWNER = 'OWNER',
}

/**
 * Trust verification result status.
 * Used for passport fingerprint verification operations.
 */
export enum TrustVerificationStatus {
  /** Fingerprint matches on-chain record. */
  MATCH = 'MATCH',
  /** Fingerprint does not match on-chain record. */
  MISMATCH = 'MISMATCH',
  /** No on-chain record found for the device. */
  NOT_FOUND = 'NOT_FOUND',
}

/**
 * Canonical 19-class device-detection taxonomy (authoritative order).
 * Mirrors `load_taxonomy()` from `intelligence/device_ai/dataset/taxonomy.py`
 * (source: `components/data/components.yaml`, version 1.0.0).
 */
export const TAXONOMY_VERSION = '1.0.0';

export const CANONICAL_CLASS_NAMES: readonly string[] = [
  'laptop', // 0
  'smartphone', // 1
  'tablet', // 2
  'desktop', // 3
  'server', // 4
  'monitor', // 5
  'crt_monitor', // 6
  'television', // 7
  'printer', // 8
  'keyboard', // 9
  'mouse', // 10
  'router', // 11
  'power_supply', // 12
  'cable', // 13
  'camera', // 14
  'game_console', // 15
  'smartwatch', // 16
  'headphones', // 17
  'battery', // 18
];

/**
 * On-chain device asset.
 * Minimal immutable provenance only — no images, no raw OCR, no personal data.
 */
export interface DeviceAsset {
  /** Unique public device identifier (e.g. DEV-2026-A1B2C3D4-01). */
  deviceId: string;
  /** EcoTrace ecosystem ID (QR code reference). */
  ecoId: string;
  /** Capture session that originated this device (provenance reference). */
  captureId: string | null;
  /** Device taxonomy class ID (0..18 per authoritative taxonomy). */
  classId: number;
  /** Canonical device type label (e.g. 'laptop', 'smartphone'). */
  deviceType: string;
  /** SHA-256 hex fingerprint of the off-chain DevicePassport. */
  passportFingerprint: string;
  /** Current on-chain lifecycle state. */
  lifecycleState: LifecycleState;
  /** MSP ID of the current custodian (registering/updating organization). */
  currentCustodian: string;
  /** ISO 8601 timestamp when the asset was created on-chain. */
  createdAt: string;
  /** ISO 8601 timestamp of the last state update. */
  updatedAt: string;
  /** Minimal metadata (hash references, collection point, etc.). */
  metadata: Record<string, string>;
}

/**
 * On-chain lifecycle event record.
 * Immutable audit-trail entry persisted per device.
 */
export interface LifecycleEvent {
  /** Deterministic unique event identifier. */
  eventId: string;
  /** Device this event belongs to. */
  deviceId: string;
  /** Type of lifecycle event (P5 DeviceEventType vocabulary). */
  eventType: DeviceEventType;
  /** Actor role that triggered the event (derived from submitting identity). */
  actorRole: ActorRole;
  /** Actor identifier (identity id / MSP user). */
  actorId: string;
  /** ISO 8601 transaction timestamp (from the proposal header). */
  timestamp: string;
  /** SHA-256 hash of the off-chain record this event anchors. */
  recordHash: string;
  /** Previous lifecycle state (null for the initial registration event). */
  previousState: LifecycleState | null;
  /** New lifecycle state. */
  newState: LifecycleState;
  /** Optional additional context. */
  metadata: Record<string, string>;
}

/**
 * Passport anchor record.
 * Links a device to its passport fingerprint for verification.
 */
export interface PassportAnchor {
  /** Device identifier. */
  deviceId: string;
  /** SHA-256 hex fingerprint of the DevicePassport. */
  passportFingerprint: string;
  /** Hash algorithm used (always 'sha256' in P6.1). */
  algorithm: string;
  /** ISO 8601 timestamp when anchored. */
  anchoredAt: string;
  /** Anchor transaction ID. */
  transactionId: string;
}

/**
 * Output for the GetDevice query.
 */
export interface GetDeviceOutput {
  /** Device asset if found, null if not exists. */
  device: DeviceAsset | null;
}

/**
 * Output for the DeviceExists query.
 */
export interface DeviceExistsOutput {
  /** Whether the device exists on-chain. */
  exists: boolean;
}

/**
 * Output for the GetDeviceHistory query.
 */
export interface GetDeviceHistoryOutput {
  /** Device identifier. */
  deviceId: string;
  /** Chronological event history (oldest first). */
  history: LifecycleEvent[];
}

/**
 * Output for the VerifyPassportFingerprint query.
 */
export interface VerifyPassportFingerprintOutput {
  /** Device identifier. */
  deviceId: string;
  /** Verification result. */
  status: TrustVerificationStatus;
  /** On-chain stored fingerprint (if any). */
  storedFingerprint: string | null;
  /** Input fingerprint that was verified. */
  inputFingerprint: string;
  /** Verification timestamp (from the transaction header — deterministic). */
  verifiedAt: string;
  /** Human-readable message. */
  message: string;
}

/**
 * Chaincode event payloads (emitted via setEvent).
 */
export interface DeviceRegisteredEvent {
  deviceId: string;
  ecoId: string;
  passportFingerprint: string;
  timestamp: string;
}

export interface DeviceLifecycleUpdatedEvent {
  deviceId: string;
  previousState: LifecycleState | null;
  newState: LifecycleState;
  eventType: DeviceEventType;
  actorRole: ActorRole;
  actorId: string;
  recordHash: string;
  timestamp: string;
}

export interface PassportAnchoredEvent {
  deviceId: string;
  passportFingerprint: string;
  algorithm: string;
  timestamp: string;
}

/**
 * Authorization context for transaction validation.
 * Derived from the submitting client identity (MSP) in production;
 * injectable/mocked for independent unit testing.
 */
export interface AuthorizationContext {
  /** MSP ID of the submitting identity. */
  mspId: string;
  /** Role resolved from the identity. */
  role: ActorRole;
  /** Unique identifier within the MSP. */
  identityId: string;
}

/**
 * Resolve an actor role from the submitting identity.
 *
 * P6.1 uses a v1 heuristic based on MSP ID / identity-id keyword matching.
 * The engineering spec targets Fabric identity attributes (`getAttributeValue`)
 * and multi-organization membership (EcoTraceOrg / recycler / government) in
 * later phases; this function is the single extension point.
 *
 * @param mspId MSP ID of the submitting identity
 * @param identityId Identity id string
 * @returns The resolved ActorRole (defaults to PLATFORM for the platform org)
 */
export function resolveActorRole(mspId: string, identityId: string): ActorRole {
  const haystack = `${mspId} ${identityId}`.toLowerCase();
  if (haystack.includes('collector')) {
    return ActorRole.COLLECTOR;
  }
  if (haystack.includes('recycler')) {
    return ActorRole.RECYCLER;
  }
  if (haystack.includes('government')) {
    return ActorRole.GOVERNMENT;
  }
  if (haystack.includes('owner')) {
    return ActorRole.OWNER;
  }
  return ActorRole.PLATFORM;
}

/**
 * Check if a lifecycle transition is valid.
 * @param currentState Current lifecycle state
 * @param newState Proposed new state
 * @returns true if the transition is allowed
 */
export function isValidTransition(currentState: LifecycleState, newState: LifecycleState): boolean {
  const allowed = VALID_LIFECYCLE_TRANSITIONS.get(currentState);
  return allowed ? allowed.has(newState) : false;
}

/**
 * Parse a raw string into a LifecycleState value.
 * Returns undefined for unknown values (does not throw) so callers can emit a
 * precise validation error.
 * @param raw Raw string value
 * @returns The LifecycleState, or undefined if not a valid state
 */
export function parseLifecycleState(raw: string): LifecycleState | undefined {
  if (Object.values(LifecycleState).includes(raw as LifecycleState)) {
    return raw as LifecycleState;
  }
  return undefined;
}

/**
 * Parse a raw string into an ActorRole value.
 * Returns undefined for unknown values (does not throw).
 * @param raw Raw string value
 * @returns The ActorRole, or undefined if not a valid role
 */
export function parseActorRole(raw: string): ActorRole | undefined {
  if (Object.values(ActorRole).includes(raw as ActorRole)) {
    return raw as ActorRole;
  }
  return undefined;
}

/**
 * Validate a SHA-256 hex string (64 lowercase/uppercase hex characters).
 * @param value Value to validate
 * @returns true if the value is a valid SHA-256 hex fingerprint
 */
export function isValidSha256Hex(value: string): boolean {
  return /^[a-f0-9]{64}$/i.test(value);
}

/**
 * Get the canonical device type label for a class ID.
 * Uses the authoritative 19-class taxonomy (laptop == 0).
 * @param classId Taxonomy class index
 * @returns The canonical lowercase label, or null if out of range
 */
export function getCanonicalDeviceType(classId: number): string | null {
  if (Number.isInteger(classId) && classId >= 0 && classId < CANONICAL_CLASS_NAMES.length) {
    return CANONICAL_CLASS_NAMES[classId];
  }
  return null;
}

/**
 * Validate class ID is within the authoritative taxonomy bounds (0..18).
 * @param classId Taxonomy class index
 * @returns true if valid
 */
export function isValidClassId(classId: number): boolean {
  return Number.isInteger(classId) && classId >= 0 && classId < CANONICAL_CLASS_NAMES.length;
}
