/**
 * EcoTrace Device Lifecycle Chaincode
 *
 * P6.1 — Hyperledger Fabric Chaincode for EcoTrace Device Lifecycle Management
 *
 * Implements the on-chain contract for immutable device lifecycle and trust
 * provenance. The ledger acts as an external, tamper-evident trust layer for
 * the P5 passport architecture — it stores only identifiers, lifecycle state,
 * timestamps, and hashes (never images, raw OCR, passports, or personal data).
 *
 * Determinism contract (see docs/engineering/09_BLOCKCHAIN.md):
 *   - timestamps come from the transaction header (getTxTimestamp), never the
 *     system clock
 *   - event ids are derived from a per-device monotonic sequence
 *   - no randomness, no external calls
 *
 * Transaction wire names are chosen to satisfy BOTH the P6.1 contract surface
 * (RegisterDevice / UpdateLifecycle / GetDevice / DeviceExists /
 * GetDeviceHistory / VerifyPassportFingerprint) AND the P5 external trust
 * adapter interface (`FabricExternalTrustLedger` in
 * `intelligence/device_ai/devices/external_trust.py` submits
 * "AnchorDevicePassport" and evaluates "GetDeviceAnchor").
 *
 * @packageDocumentation
 */

import { Context, Contract, Info, Transaction } from 'fabric-contract-api';
import {
  ActorRole,
  AuthorizationContext,
  ChaincodeEventType,
  DeviceAsset,
  DeviceEventType,
  DeviceExistsOutput,
  DeviceLifecycleUpdatedEvent,
  DeviceRegisteredEvent,
  GetDeviceHistoryOutput,
  GetDeviceOutput,
  INITIAL_LIFECYCLE_STATE,
  isValidClassId,
  isValidSha256Hex,
  isValidTransition,
  LifecycleEvent,
  LifecycleState,
  parseLifecycleState,
  PassportAnchor,
  PassportAnchoredEvent,
  resolveActorRole,
  TrustVerificationStatus,
  VALID_LIFECYCLE_TRANSITIONS,
  VerifyPassportFingerprintOutput,
} from './types';

/**
 * Chaincode storage key prefixes.
 */
const KEY_PREFIX = {
  DEVICE: 'device:',
  EVENT: 'event:',
  PASSPORT_ANCHOR: 'passport:',
  EVENT_INDEX: 'eventidx:',
} as const;

/**
 * Generate a deterministic ISO 8601 timestamp from the transaction header.
 *
 * The Fabric peer sets the transaction timestamp from the proposal header, so
 * the same endorsed transaction produces the same timestamp on every peer. The
 * `new Date()` fallback is reachable only with stubs that omit a timestamp and
 * never on a live Fabric network.
 */
function getTimestamp(ctx: Context): string {
  const txTimestamp = ctx.stub.getTxTimestamp();
  if (txTimestamp && txTimestamp.seconds) {
    return new Date(txTimestamp.seconds.low * 1000).toISOString();
  }
  // Test-only fallback; production Fabric always supplies a tx timestamp.
  return new Date().toISOString();
}

/**
 * Extract the authorization context from the submitting client identity.
 */
function getAuthorizationContext(ctx: Context): AuthorizationContext {
  const clientIdentity = ctx.clientIdentity;
  const mspId = clientIdentity.getMSPID();
  const identityId = clientIdentity.getID();
  return {
    mspId,
    role: resolveActorRole(mspId, identityId),
    identityId,
  };
}

/**
 * Assert the submitting identity holds one of the required roles.
 */
function requireRole(
  ctx: Context,
  requiredRoles: ActorRole[],
  operation: string
): AuthorizationContext {
  const auth = getAuthorizationContext(ctx);
  if (!requiredRoles.includes(auth.role)) {
    throw new Error(
      `Authorization failed: ${operation} requires one of [${requiredRoles.join(', ')}], ` +
        `but caller has role ${auth.role} (MSP: ${auth.mspId})`
    );
  }
  return auth;
}

/**
 * Parse a metadata JSON string into a plain string map.
 * Empty/undefined input resolves to `{}`; malformed JSON is rejected.
 */
function parseMetadata(metadataJSON: string | undefined): Record<string, string> {
  const raw = metadataJSON === undefined || metadataJSON.trim() === '' ? '{}' : metadataJSON;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error('metadataJSON must be valid JSON');
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('metadataJSON must be a JSON object');
  }
  return parsed as Record<string, string>;
}

/**
 * EcoTrace Device Lifecycle Contract
 */
@Info({
  title: 'EcoTrace Device Lifecycle Chaincode',
  description:
    'Hyperledger Fabric smart contract for immutable device lifecycle and trust provenance',
  version: '1.0.0',
})
export class EcoTraceLifecycleContract extends Contract {
  /**
   * Register a new device on-chain.
   *
   * Anchors the device asset in the DETECTED lifecycle state (the P5 off-chain
   * entry point) with its passport fingerprint as the primary cryptographic
   * identity. Rejects duplicate device IDs. Only callable by the PLATFORM role.
   *
   * @param ctx Transaction context
   * @param deviceId Unique device identifier
   * @param ecoId EcoTrace ecosystem ID (QR code reference)
   * @param classId Taxonomy class ID (0..18)
   * @param deviceType Canonical device type label
   * @param passportFingerprint SHA-256 hex fingerprint of the off-chain DevicePassport
   * @param metadataJSON Optional JSON string of additional metadata
   * @returns JSON string of the created DeviceAsset
   */
  @Transaction()
  public async RegisterDevice(
    ctx: Context,
    deviceId: string,
    ecoId: string,
    classId: number,
    deviceType: string,
    passportFingerprint: string,
    metadataJSON: string = '{}'
  ): Promise<string> {
    // Authorization: only the platform/registration authority can register.
    requireRole(ctx, [ActorRole.PLATFORM], 'RegisterDevice');

    // Validate required fields.
    if (!deviceId || deviceId.trim() === '') {
      throw new Error('deviceId is required and cannot be empty');
    }
    if (!ecoId || ecoId.trim() === '') {
      throw new Error('ecoId is required and cannot be empty');
    }
    const classIdNum = Number(classId);
    if (!isValidClassId(classIdNum)) {
      throw new Error(`Invalid classId: ${classId}. Must be 0-18.`);
    }
    if (!deviceType || deviceType.trim() === '') {
      throw new Error('deviceType is required and cannot be empty');
    }
    if (!passportFingerprint || !isValidSha256Hex(passportFingerprint)) {
      throw new Error('passportFingerprint must be a valid SHA-256 hex string (64 characters)');
    }

    // Reject duplicate device IDs.
    const deviceKey = this.deviceKey(deviceId);
    const existing = await ctx.stub.getState(deviceKey);
    if (existing && existing.length > 0) {
      throw new Error(`Device ${deviceId} already exists on-chain`);
    }

    const metadata = parseMetadata(metadataJSON);
    const timestamp = getTimestamp(ctx);
    const auth = getAuthorizationContext(ctx);

    const device: DeviceAsset = {
      deviceId,
      ecoId,
      captureId: metadata['captureId'] || null,
      classId: classIdNum,
      deviceType,
      passportFingerprint: passportFingerprint.toLowerCase(),
      lifecycleState: INITIAL_LIFECYCLE_STATE,
      currentCustodian: auth.mspId,
      createdAt: timestamp,
      updatedAt: timestamp,
      metadata,
    };

    await ctx.stub.putState(deviceKey, Buffer.from(JSON.stringify(device)));

    // Initial audit event (event type mirrors P5 DEVICE_REGISTERED).
    await this.recordEvent(
      ctx,
      deviceId,
      DeviceEventType.DEVICE_REGISTERED,
      auth,
      timestamp,
      device.passportFingerprint,
      null,
      INITIAL_LIFECYCLE_STATE,
      { ecoId, classId: String(classIdNum), deviceType }
    );

    // Emit chaincode event.
    const eventPayload: DeviceRegisteredEvent = {
      deviceId,
      ecoId,
      passportFingerprint: device.passportFingerprint,
      timestamp,
    };
    ctx.stub.setEvent(ChaincodeEventType.DEVICE_REGISTERED, Buffer.from(JSON.stringify(eventPayload)));

    return JSON.stringify(device);
  }

  /**
   * Update a device's lifecycle state.
   *
   * Enforces the strict P5 progression DETECTED -> CONFIRMED -> REGISTERED ->
   * ENRICHED. A transition is only recorded when the submitting identity holds
   * the required role and a valid SHA-256 record hash of the supporting
   * off-chain record is supplied — the chaincode never records an event merely
   * because an arbitrary transaction was submitted.
   *
   * @param ctx Transaction context
   * @param deviceId Device identifier
   * @param newState Target lifecycle state
   * @param recordHash SHA-256 hash of the off-chain record supporting the transition
   * @param metadataJSON Optional JSON string of additional metadata
   * @returns JSON string of the updated DeviceAsset
   */
  @Transaction()
  public async UpdateLifecycle(
    ctx: Context,
    deviceId: string,
    newState: string,
    recordHash: string,
    metadataJSON: string = '{}'
  ): Promise<string> {
    // Validate the target state explicitly (silently-undefined enums are rejected).
    const targetState = parseLifecycleState(newState);
    if (targetState === undefined) {
      throw new Error(`Invalid lifecycle state: ${newState}`);
    }

    // Authorization is per target transition (future orgs extend this map).
    const allowedRoles = this.getAllowedRolesForTransition(targetState);
    const auth = requireRole(ctx, allowedRoles, `UpdateLifecycle to ${targetState}`);

    // A transition must be backed by a hash of the supporting off-chain record.
    if (!recordHash || !isValidSha256Hex(recordHash)) {
      throw new Error('recordHash must be a valid SHA-256 hex string (64 characters)');
    }

    const metadata = parseMetadata(metadataJSON);

    const deviceKey = this.deviceKey(deviceId);
    const deviceBytes = await ctx.stub.getState(deviceKey);
    if (!deviceBytes || deviceBytes.length === 0) {
      throw new Error(`Device ${deviceId} not found`);
    }

    const device: DeviceAsset = JSON.parse(deviceBytes.toString());

    // Enforce a valid, forward-only transition.
    if (!isValidTransition(device.lifecycleState, targetState)) {
      const allowed = VALID_LIFECYCLE_TRANSITIONS.get(device.lifecycleState) || new Set<LifecycleState>();
      throw new Error(
        `Invalid lifecycle transition: ${device.lifecycleState} -> ${targetState}. ` +
          `Allowed: ${[...allowed].join(', ')}`
      );
    }

    const previousState = device.lifecycleState;
    const timestamp = getTimestamp(ctx);

    device.lifecycleState = targetState;
    device.updatedAt = timestamp;
    device.currentCustodian = auth.mspId;
    device.metadata = { ...device.metadata, ...metadata };

    await ctx.stub.putState(deviceKey, Buffer.from(JSON.stringify(device)));

    await this.recordEvent(
      ctx,
      deviceId,
      this.mapStateToEventType(targetState),
      auth,
      timestamp,
      recordHash.toLowerCase(),
      previousState,
      targetState,
      metadata
    );

    const eventPayload: DeviceLifecycleUpdatedEvent = {
      deviceId,
      previousState,
      newState: targetState,
      eventType: this.mapStateToEventType(targetState),
      actorRole: auth.role,
      actorId: auth.identityId,
      recordHash: recordHash.toLowerCase(),
      timestamp,
    };
    ctx.stub.setEvent(
      ChaincodeEventType.DEVICE_LIFECYCLE_UPDATED,
      Buffer.from(JSON.stringify(eventPayload))
    );

    return JSON.stringify(device);
  }

  /**
   * Anchor (or re-anchor) a device passport fingerprint.
   *
   * Creates/updates the PassportAnchor record so the on-chain fingerprint
   * tracks the latest off-chain passport (e.g. after enrichment). This is the
   * transaction invoked by the P5 `FabricExternalTrustLedger.anchor()` adapter
   * via `submitTransaction("AnchorDevicePassport", deviceId, fingerprint,
   * algorithm)`. Only callable by the PLATFORM role.
   *
   * @param ctx Transaction context
   * @param deviceId Device identifier
   * @param passportFingerprint SHA-256 hex fingerprint
   * @param algorithm Hash algorithm (only 'sha256' supported in P6.1)
   * @returns JSON string of the PassportAnchor
   */
  @Transaction()
  public async AnchorDevicePassport(
    ctx: Context,
    deviceId: string,
    passportFingerprint: string,
    algorithm: string = 'sha256'
  ): Promise<string> {
    requireRole(ctx, [ActorRole.PLATFORM], 'AnchorDevicePassport');

    if (!passportFingerprint || !isValidSha256Hex(passportFingerprint)) {
      throw new Error('passportFingerprint must be a valid SHA-256 hex string (64 characters)');
    }
    const algo = (algorithm || 'sha256').toLowerCase();
    if (algo !== 'sha256') {
      throw new Error(`Unsupported fingerprint algorithm: ${algorithm}. P6.1 supports 'sha256'.`);
    }

    const deviceKey = this.deviceKey(deviceId);
    const deviceBytes = await ctx.stub.getState(deviceKey);
    if (!deviceBytes || deviceBytes.length === 0) {
      throw new Error(`Device ${deviceId} not found`);
    }

    const device: DeviceAsset = JSON.parse(deviceBytes.toString());
    const timestamp = getTimestamp(ctx);
    const auth = getAuthorizationContext(ctx);
    const normalizedFingerprint = passportFingerprint.toLowerCase();

    const anchor: PassportAnchor = {
      deviceId,
      passportFingerprint: normalizedFingerprint,
      algorithm: algo,
      anchoredAt: timestamp,
      transactionId: ctx.stub.getTxID(),
    };

    const anchorKey = `${KEY_PREFIX.PASSPORT_ANCHOR}${deviceId}`;
    await ctx.stub.putState(anchorKey, Buffer.from(JSON.stringify(anchor)));

    // Re-anchor reflects on the device asset so verification stays consistent.
    if (device.passportFingerprint !== normalizedFingerprint) {
      device.passportFingerprint = normalizedFingerprint;
      device.updatedAt = timestamp;
      await ctx.stub.putState(deviceKey, Buffer.from(JSON.stringify(device)));
    }

    await this.recordEvent(
      ctx,
      deviceId,
      DeviceEventType.DEVICE_EXTERNALLY_ANCHORED,
      auth,
      timestamp,
      normalizedFingerprint,
      device.lifecycleState,
      device.lifecycleState,
      { operation: 'anchor_passport' }
    );

    const eventPayload: PassportAnchoredEvent = {
      deviceId,
      passportFingerprint: normalizedFingerprint,
      algorithm: algo,
      timestamp,
    };
    ctx.stub.setEvent(ChaincodeEventType.PASSPORT_ANCHORED, Buffer.from(JSON.stringify(eventPayload)));

    return JSON.stringify(anchor);
  }

  /**
   * Get a device asset by ID (read-only).
   *
   * @param ctx Transaction context
   * @param deviceId Device identifier
   * @returns JSON string of GetDeviceOutput
   */
  @Transaction(false)
  public async GetDevice(ctx: Context, deviceId: string): Promise<string> {
    const deviceBytes = await ctx.stub.getState(this.deviceKey(deviceId));
    const output: GetDeviceOutput = {
      device: deviceBytes && deviceBytes.length > 0 ? JSON.parse(deviceBytes.toString()) : null,
    };
    return JSON.stringify(output);
  }

  /**
   * Check whether a device exists on-chain (read-only).
   *
   * @param ctx Transaction context
   * @param deviceId Device identifier
   * @returns JSON string of DeviceExistsOutput
   */
  @Transaction(false)
  public async DeviceExists(ctx: Context, deviceId: string): Promise<string> {
    const deviceBytes = await ctx.stub.getState(this.deviceKey(deviceId));
    const output: DeviceExistsOutput = {
      exists: deviceBytes !== undefined && deviceBytes.length > 0,
    };
    return JSON.stringify(output);
  }

  /**
   * Get the deterministic chronological history for a device (read-only).
   *
   * Events are returned oldest-first in the exact order they were recorded.
   *
   * @param ctx Transaction context
   * @param deviceId Device identifier
   * @returns JSON string of GetDeviceHistoryOutput
   */
  @Transaction(false)
  public async GetDeviceHistory(ctx: Context, deviceId: string): Promise<string> {
    const deviceBytes = await ctx.stub.getState(this.deviceKey(deviceId));
    if (!deviceBytes || deviceBytes.length === 0) {
      throw new Error(`Device ${deviceId} not found`);
    }

    const indexBytes = await ctx.stub.getState(`${KEY_PREFIX.EVENT_INDEX}${deviceId}`);
    const eventIds: string[] =
      indexBytes && indexBytes.length > 0 ? JSON.parse(indexBytes.toString()) : [];

    const history: LifecycleEvent[] = [];
    for (const eventId of eventIds) {
      const eventBytes = await ctx.stub.getState(`${KEY_PREFIX.EVENT}${eventId}`);
      if (eventBytes && eventBytes.length > 0) {
        history.push(JSON.parse(eventBytes.toString()));
      }
    }

    const output: GetDeviceHistoryOutput = { deviceId, history };
    return JSON.stringify(output);
  }

  /**
   * Verify a passport fingerprint against the on-chain record (read-only).
   *
   * Deterministic result: MATCH | MISMATCH | NOT_FOUND. Checks the passport
   * anchor first (the latest anchored fingerprint), falling back to the device
   * asset fingerprint anchored at registration. Must not mutate state.
   *
   * @param ctx Transaction context
   * @param deviceId Device identifier
   * @param passportFingerprint Fingerprint to verify
   * @returns JSON string of VerifyPassportFingerprintOutput
   */
  @Transaction(false)
  public async VerifyPassportFingerprint(
    ctx: Context,
    deviceId: string,
    passportFingerprint: string
  ): Promise<string> {
    if (!passportFingerprint || !isValidSha256Hex(passportFingerprint)) {
      throw new Error('passportFingerprint must be a valid SHA-256 hex string (64 characters)');
    }

    const inputFingerprint = passportFingerprint.toLowerCase();
    const verifiedAt = getTimestamp(ctx);
    const result = (status: TrustVerificationStatus, stored: string | null, message: string): string =>
      JSON.stringify({
        deviceId,
        status,
        storedFingerprint: stored,
        inputFingerprint,
        verifiedAt,
        message,
      } satisfies VerifyPassportFingerprintOutput);

    // Prefer the passport anchor (latest anchored fingerprint).
    const anchorBytes = await ctx.stub.getState(`${KEY_PREFIX.PASSPORT_ANCHOR}${deviceId}`);
    if (anchorBytes && anchorBytes.length > 0) {
      const anchor: PassportAnchor = JSON.parse(anchorBytes.toString());
      if (anchor.passportFingerprint === inputFingerprint) {
        return result(
          TrustVerificationStatus.MATCH,
          anchor.passportFingerprint,
          'Passport fingerprint matches on-chain anchor'
        );
      }
      return result(
        TrustVerificationStatus.MISMATCH,
        anchor.passportFingerprint,
        'Passport fingerprint does not match on-chain anchor'
      );
    }

    // Fall back to the fingerprint stored on the device asset.
    const deviceBytes = await ctx.stub.getState(this.deviceKey(deviceId));
    if (!deviceBytes || deviceBytes.length === 0) {
      return result(
        TrustVerificationStatus.NOT_FOUND,
        null,
        'Device not found on-chain'
      );
    }

    const device: DeviceAsset = JSON.parse(deviceBytes.toString());
    if (device.passportFingerprint === inputFingerprint) {
      return result(
        TrustVerificationStatus.MATCH,
        device.passportFingerprint,
        'Passport fingerprint matches device asset'
      );
    }
    return result(
      TrustVerificationStatus.MISMATCH,
      device.passportFingerprint,
      'Passport fingerprint does not match device asset'
    );
  }

  /**
   * Get the passport anchor for a device (read-only).
   *
   * This is the query invoked by the P5 `FabricExternalTrustLedger.get_anchor()`
   * adapter via `evaluateTransaction("GetDeviceAnchor", deviceId)`.
   *
   * @param ctx Transaction context
   * @param deviceId Device identifier
   * @returns JSON string of the PassportAnchor, or "null" if not anchored
   */
  @Transaction(false)
  public async GetDeviceAnchor(ctx: Context, deviceId: string): Promise<string> {
    const anchorBytes = await ctx.stub.getState(`${KEY_PREFIX.PASSPORT_ANCHOR}${deviceId}`);
    if (!anchorBytes || anchorBytes.length === 0) {
      return JSON.stringify(null);
    }
    return anchorBytes.toString();
  }

  /**
   * List all registered device IDs (read-only, for admin/debugging).
   *
   * @param ctx Transaction context
   * @returns JSON array of device IDs
   */
  @Transaction(false)
  public async GetAllDeviceIds(ctx: Context): Promise<string> {
    // Plain string-prefixed keys require a range query, not a composite key.
    const iterator = await ctx.stub.getStateByRange(KEY_PREFIX.DEVICE, `${KEY_PREFIX.DEVICE}￿`);
    const deviceIds: string[] = [];

    try {
      let result = await iterator.next();
      while (!result.done) {
        if (result.value && result.value.key) {
          deviceIds.push(result.value.key.replace(KEY_PREFIX.DEVICE, ''));
        }
        result = await iterator.next();
      }
    } finally {
      await iterator.close();
    }

    return JSON.stringify(deviceIds);
  }

  /**
   * Get the allowed actor roles for a lifecycle transition.
   *
   * P6.1: all transitions are platform operations (confirmation, registration,
   * and enrichment are performed by the backend/registration authority). This
   * map is the extension point for future collector/recycler organizations.
   *
   * @param targetState Target lifecycle state
   * @returns Roles allowed to perform the transition
   */
  private getAllowedRolesForTransition(targetState: LifecycleState): ActorRole[] {
    switch (targetState) {
      case LifecycleState.CONFIRMED:
      case LifecycleState.REGISTERED:
      case LifecycleState.ENRICHED:
        return [ActorRole.PLATFORM];
      default:
        return [ActorRole.PLATFORM];
    }
  }

  /**
   * Map a target lifecycle state to its P5 `DeviceEventType` audit label.
   */
  private mapStateToEventType(state: LifecycleState): DeviceEventType {
    switch (state) {
      case LifecycleState.CONFIRMED:
        return DeviceEventType.DEVICE_CONFIRMED;
      case LifecycleState.REGISTERED:
        return DeviceEventType.DEVICE_REGISTERED;
      case LifecycleState.ENRICHED:
        return DeviceEventType.DEVICE_ENRICHED;
      default:
        return DeviceEventType.DEVICE_DETECTED;
    }
  }

  /**
   * Persist an immutable audit event and append it to the device's history
   * index. Event ids are deterministic (per-device monotonic sequence).
   */
  private async recordEvent(
    ctx: Context,
    deviceId: string,
    eventType: DeviceEventType,
    auth: AuthorizationContext,
    timestamp: string,
    recordHash: string,
    previousState: LifecycleState | null,
    newState: LifecycleState,
    metadata: Record<string, string>
  ): Promise<string> {
    const indexKey = `${KEY_PREFIX.EVENT_INDEX}${deviceId}`;
    const indexBytes = await ctx.stub.getState(indexKey);
    const eventIds: string[] =
      indexBytes && indexBytes.length > 0 ? JSON.parse(indexBytes.toString()) : [];

    const eventId = `evt-${deviceId}-${eventIds.length + 1}`;
    const event: LifecycleEvent = {
      eventId,
      deviceId,
      eventType,
      actorRole: auth.role,
      actorId: auth.identityId,
      timestamp,
      recordHash,
      previousState,
      newState,
      metadata,
    };

    await ctx.stub.putState(`${KEY_PREFIX.EVENT}${eventId}`, Buffer.from(JSON.stringify(event)));
    eventIds.push(eventId);
    await ctx.stub.putState(indexKey, Buffer.from(JSON.stringify(eventIds)));

    return eventId;
  }

  /**
   * Storage key for a device asset.
   */
  private deviceKey(deviceId: string): string {
    return `${KEY_PREFIX.DEVICE}${deviceId}`;
  }
}
