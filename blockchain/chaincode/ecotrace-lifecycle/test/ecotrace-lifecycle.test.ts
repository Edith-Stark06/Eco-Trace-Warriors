/**
 * Test Suite for the EcoTrace Device Lifecycle Chaincode
 *
 * P6.1 — Hyperledger Fabric Chaincode for EcoTrace Device Lifecycle Management
 *
 * All tests run against the in-memory mock stub — no live Fabric network is
 * required. Covers registration, duplicate rejection, input validation, the P5
 * lifecycle state machine (DETECTED -> CONFIRMED -> REGISTERED -> ENRICHED),
 * passport fingerprint verification, read-only guarantees, event emission,
 * authorization, and deterministic serialization/response behavior.
 */

import { EcoTraceLifecycleContract } from '../src/ecotrace-lifecycle';
import {
  ActorRole,
  CANONICAL_CLASS_NAMES,
  DeviceAsset,
  DeviceEventType,
  LifecycleState,
  TrustVerificationStatus,
  getCanonicalDeviceType,
  isValidClassId,
  isValidSha256Hex,
  isValidTransition,
  parseLifecycleState,
  resolveActorRole,
} from '../src/types';
import { MockContext, createMockContext } from './mock-context';

describe('EcoTraceLifecycleContract', () => {
  let contract: EcoTraceLifecycleContract;

  const DEVICE_ID = 'DEV-2026-TEST-001';
  const ECO_ID = 'ECO-2026-TEST-001';
  const CLASS_ID = 0; // laptop
  const DEVICE_TYPE = 'laptop';
  const FINGERPRINT = 'a'.repeat(64);
  const METADATA = { location: 'Delhi', collector: 'GreenCollect' };

  const recordHash = (seed: string): string => seed.repeat(64).slice(0, 64);

  beforeEach(() => {
    contract = new EcoTraceLifecycleContract();
  });

  /**
   * Create a fresh context with DEVICE_ID already registered by the platform.
   */
  async function registeredContext(
    seconds: number = 1_700_000_000,
    mspId: string = 'EcoTraceOrg',
    userId: string = 'platform-admin'
  ): Promise<MockContext> {
    const ctx = createMockContext(seconds, mspId, userId);
    await contract.RegisterDevice(
      ctx,
      DEVICE_ID,
      ECO_ID,
      CLASS_ID,
      DEVICE_TYPE,
      FINGERPRINT,
      JSON.stringify(METADATA)
    );
    return ctx;
  }

  describe('Device Registration', () => {
    it('registers a valid device (initial DETECTED state, fingerprint anchored)', async () => {
      const ctx = createMockContext(1_700_000_100, 'EcoTraceOrg', 'platform-admin');

      const result = await contract.RegisterDevice(
        ctx,
        DEVICE_ID,
        ECO_ID,
        CLASS_ID,
        DEVICE_TYPE,
        FINGERPRINT,
        JSON.stringify(METADATA)
      );

      const device: DeviceAsset = JSON.parse(result);
      expect(device.deviceId).toBe(DEVICE_ID);
      expect(device.ecoId).toBe(ECO_ID);
      expect(device.captureId).toBeNull();
      expect(device.classId).toBe(CLASS_ID);
      expect(device.deviceType).toBe(DEVICE_TYPE);
      expect(device.passportFingerprint).toBe(FINGERPRINT);
      expect(device.lifecycleState).toBe(LifecycleState.DETECTED);
      expect(device.currentCustodian).toBe('EcoTraceOrg');
      expect(device.createdAt).toBe(new Date(1_700_000_100 * 1000).toISOString());
      expect(device.updatedAt).toBe(device.createdAt);
      expect(device.metadata).toEqual(METADATA);

      // Immutable on-chain record present
      const exists = JSON.parse(await contract.DeviceExists(ctx, DEVICE_ID));
      expect(exists.exists).toBe(true);
    });

    it('rejects a duplicate device ID', async () => {
      const ctx = createMockContext();
      await contract.RegisterDevice(
        ctx, DEVICE_ID, ECO_ID, CLASS_ID, DEVICE_TYPE, FINGERPRINT, '{}'
      );

      await expect(
        contract.RegisterDevice(
          ctx, DEVICE_ID, ECO_ID, CLASS_ID, DEVICE_TYPE, 'b'.repeat(64), '{}'
        )
      ).rejects.toThrow(`Device ${DEVICE_ID} already exists on-chain`);
    });

    it('rejects a missing/invalid device ID', async () => {
      const ctx = createMockContext();

      await expect(
        contract.RegisterDevice(ctx, '', ECO_ID, CLASS_ID, DEVICE_TYPE, FINGERPRINT, '{}')
      ).rejects.toThrow('deviceId is required and cannot be empty');

      await expect(
        contract.RegisterDevice(ctx, '   ', ECO_ID, CLASS_ID, DEVICE_TYPE, FINGERPRINT, '{}')
      ).rejects.toThrow('deviceId is required and cannot be empty');
    });

    it('rejects missing ecoId, invalid classId, missing deviceType, invalid fingerprint', async () => {
      const ctx = createMockContext();

      await expect(
        contract.RegisterDevice(ctx, DEVICE_ID, '', CLASS_ID, DEVICE_TYPE, FINGERPRINT, '{}')
      ).rejects.toThrow('ecoId is required and cannot be empty');

      await expect(
        contract.RegisterDevice(ctx, DEVICE_ID, ECO_ID, 19, DEVICE_TYPE, FINGERPRINT, '{}')
      ).rejects.toThrow('Invalid classId: 19. Must be 0-18.');

      await expect(
        contract.RegisterDevice(ctx, DEVICE_ID, ECO_ID, -1, DEVICE_TYPE, FINGERPRINT, '{}')
      ).rejects.toThrow(/Invalid classId/);

      await expect(
        contract.RegisterDevice(ctx, DEVICE_ID, ECO_ID, CLASS_ID, '', FINGERPRINT, '{}')
      ).rejects.toThrow('deviceType is required and cannot be empty');

      await expect(
        contract.RegisterDevice(ctx, DEVICE_ID, ECO_ID, CLASS_ID, DEVICE_TYPE, 'not-a-hash', '{}')
      ).rejects.toThrow('passportFingerprint must be a valid SHA-256 hex string (64 characters)');
    });

    it('handles empty and malformed metadata', async () => {
      const ctx = createMockContext();

      const empty = JSON.parse(
        await contract.RegisterDevice(
          ctx, 'DEV-EMPTY-META', ECO_ID, CLASS_ID, DEVICE_TYPE, FINGERPRINT, ''
        )
      );
      expect(empty.metadata).toEqual({});

      await expect(
        contract.RegisterDevice(
          ctx, 'DEV-BAD-META', ECO_ID, CLASS_ID, DEVICE_TYPE, FINGERPRINT, '{invalid json}'
        )
      ).rejects.toThrow('metadataJSON must be valid JSON');
    });

    it('captures captureId provenance from metadata when provided', async () => {
      const ctx = createMockContext();
      const result = await contract.RegisterDevice(
        ctx, 'DEV-CAPTURE', ECO_ID, CLASS_ID, DEVICE_TYPE, FINGERPRINT,
        JSON.stringify({ captureId: 'CAP-1234' })
      );
      const device: DeviceAsset = JSON.parse(result);
      expect(device.captureId).toBe('CAP-1234');
    });
  });

  describe('Lifecycle State Machine', () => {
    it('advances through the full P5 progression DETECTED -> CONFIRMED -> REGISTERED -> ENRICHED', async () => {
      const ctx = await registeredContext(1_700_000_200);
      const stub = ctx.getMockStub();

      // On a live network every transaction carries its own header timestamp;
      // advance the mock clock per transition to model that faithfully.
      stub.setTimestamp(1_700_000_300);
      let device: DeviceAsset = JSON.parse(
        await contract.UpdateLifecycle(ctx, DEVICE_ID, 'CONFIRMED', recordHash('c'), '{}')
      );
      expect(device.lifecycleState).toBe(LifecycleState.CONFIRMED);

      stub.setTimestamp(1_700_000_400);
      device = JSON.parse(
        await contract.UpdateLifecycle(ctx, DEVICE_ID, 'REGISTERED', recordHash('d'), '{}')
      );
      expect(device.lifecycleState).toBe(LifecycleState.REGISTERED);

      stub.setTimestamp(1_700_000_500);
      device = JSON.parse(
        await contract.UpdateLifecycle(ctx, DEVICE_ID, 'ENRICHED', recordHash('e'), '{}')
      );
      expect(device.lifecycleState).toBe(LifecycleState.ENRICHED);

      // createdAt is immutable; updatedAt tracks the latest transition.
      expect(device.createdAt).toBe('2023-11-14T22:16:40.000Z');
      expect(device.updatedAt).toBe('2023-11-14T22:21:40.000Z');
      expect(device.updatedAt).not.toBe(device.createdAt);
    });

    it('rejects invalid lifecycle state strings', async () => {
      const ctx = await registeredContext();

      await expect(
        contract.UpdateLifecycle(ctx, DEVICE_ID, 'INVALID_STATE', recordHash('c'), '{}')
      ).rejects.toThrow('Invalid lifecycle state: INVALID_STATE');
    });

    it('rejects invalid (backward) transitions', async () => {
      const ctx = await registeredContext();
      await contract.UpdateLifecycle(ctx, DEVICE_ID, 'CONFIRMED', recordHash('c'), '{}');

      // CONFIRMED -> DETECTED is a backward transition
      await expect(
        contract.UpdateLifecycle(ctx, DEVICE_ID, 'DETECTED', recordHash('c'), '{}')
      ).rejects.toThrow(/Invalid lifecycle transition: CONFIRMED -> DETECTED/);
    });

    it('rejects skipped transitions (DETECTED -> REGISTERED without CONFIRMED)', async () => {
      const ctx = await registeredContext();

      await expect(
        contract.UpdateLifecycle(ctx, DEVICE_ID, 'REGISTERED', recordHash('d'), '{}')
      ).rejects.toThrow(/Invalid lifecycle transition: DETECTED -> REGISTERED/);
    });

    it('rejects transitions from the terminal ENRICHED state', async () => {
      const ctx = await registeredContext();
      await contract.UpdateLifecycle(ctx, DEVICE_ID, 'CONFIRMED', recordHash('c'), '{}');
      await contract.UpdateLifecycle(ctx, DEVICE_ID, 'REGISTERED', recordHash('d'), '{}');
      await contract.UpdateLifecycle(ctx, DEVICE_ID, 'ENRICHED', recordHash('e'), '{}');

      await expect(
        contract.UpdateLifecycle(ctx, DEVICE_ID, 'CONFIRMED', recordHash('c'), '{}')
      ).rejects.toThrow(/Invalid lifecycle transition: ENRICHED -> CONFIRMED/);
    });

    it('rejects updating a non-existent device', async () => {
      const ctx = createMockContext();
      await expect(
        contract.UpdateLifecycle(ctx, 'DEV-MISSING', 'CONFIRMED', recordHash('c'), '{}')
      ).rejects.toThrow('Device DEV-MISSING not found');
    });

    it('requires a valid recordHash backing every transition', async () => {
      const ctx = await registeredContext();

      await expect(
        contract.UpdateLifecycle(ctx, DEVICE_ID, 'CONFIRMED', 'not-a-hash', '{}')
      ).rejects.toThrow('recordHash must be a valid SHA-256 hex string (64 characters)');
    });

    it('records the P5 DeviceEventType vocabulary in chronological history', async () => {
      const ctx = await registeredContext(1_700_000_300);
      await contract.UpdateLifecycle(ctx, DEVICE_ID, 'CONFIRMED', recordHash('c'), '{}');
      await contract.UpdateLifecycle(ctx, DEVICE_ID, 'REGISTERED', recordHash('d'), '{}');
      await contract.UpdateLifecycle(ctx, DEVICE_ID, 'ENRICHED', recordHash('e'), '{}');

      const output = JSON.parse(await contract.GetDeviceHistory(ctx, DEVICE_ID));
      expect(output.deviceId).toBe(DEVICE_ID);
      expect(output.history.map((e: { eventType: string }) => e.eventType)).toEqual([
        DeviceEventType.DEVICE_REGISTERED, // initial registration
        DeviceEventType.DEVICE_CONFIRMED,
        DeviceEventType.DEVICE_REGISTERED,
        DeviceEventType.DEVICE_ENRICHED,
      ]);

      // Deterministic sequential event ids
      expect(output.history[0].eventId).toBe(`evt-${DEVICE_ID}-1`);
      expect(output.history[3].eventId).toBe(`evt-${DEVICE_ID}-4`);
    });
  });

  describe('Read-Only Queries', () => {
    it('gets a device by ID', async () => {
      const ctx = await registeredContext();
      const output = JSON.parse(await contract.GetDevice(ctx, DEVICE_ID));
      expect(output.device).toBeDefined();
      expect(output.device.deviceId).toBe(DEVICE_ID);
      expect(output.device.lifecycleState).toBe(LifecycleState.DETECTED);
    });

    it('returns null for a non-existent device', async () => {
      const ctx = createMockContext();
      const output = JSON.parse(await contract.GetDevice(ctx, 'DEV-MISSING'));
      expect(output.device).toBeNull();
    });

    it('DeviceExists is true for a registered device and false otherwise', async () => {
      const ctx = await registeredContext();
      expect(JSON.parse(await contract.DeviceExists(ctx, DEVICE_ID)).exists).toBe(true);
      expect(JSON.parse(await contract.DeviceExists(ctx, 'DEV-MISSING')).exists).toBe(false);
    });

    it('GetDeviceHistory returns the registration event for a new device', async () => {
      const ctx = await registeredContext();
      const output = JSON.parse(await contract.GetDeviceHistory(ctx, DEVICE_ID));
      expect(output.history).toHaveLength(1);
      expect(output.history[0].eventType).toBe(DeviceEventType.DEVICE_REGISTERED);
      expect(output.history[0].timestamp).toBeDefined();
    });

    it('GetDeviceHistory throws for a non-existent device', async () => {
      const ctx = createMockContext();
      await expect(contract.GetDeviceHistory(ctx, 'DEV-MISSING')).rejects.toThrow(/not found/);
    });

    it('GetAllDeviceIds returns registered device IDs via range query', async () => {
      const ctx = await registeredContext();
      await contract.RegisterDevice(
        ctx, 'DEV-2026-B', ECO_ID, CLASS_ID, DEVICE_TYPE, FINGERPRINT, '{}'
      );
      await contract.RegisterDevice(
        ctx, 'DEV-2026-A', ECO_ID, CLASS_ID, DEVICE_TYPE, FINGERPRINT, '{}'
      );

      const ids: string[] = JSON.parse(await contract.GetAllDeviceIds(ctx));
      expect(ids).toHaveLength(3);
      expect(ids).toContain(DEVICE_ID);
      expect(ids).toContain('DEV-2026-A');
      expect(ids).toContain('DEV-2026-B');
    });
  });

  describe('Passport Fingerprint Verification', () => {
    it('returns MATCH for the registered fingerprint', async () => {
      const ctx = await registeredContext(1_700_000_400);

      const output = JSON.parse(await contract.VerifyPassportFingerprint(ctx, DEVICE_ID, FINGERPRINT));
      expect(output.deviceId).toBe(DEVICE_ID);
      expect(output.status).toBe(TrustVerificationStatus.MATCH);
      expect(output.storedFingerprint).toBe(FINGERPRINT);
      expect(output.inputFingerprint).toBe(FINGERPRINT);
      expect(output.message).toContain('matches');
    });

    it('returns MISMATCH for a differing fingerprint', async () => {
      const ctx = await registeredContext();

      const output = JSON.parse(
        await contract.VerifyPassportFingerprint(ctx, DEVICE_ID, 'f'.repeat(64))
      );
      expect(output.status).toBe(TrustVerificationStatus.MISMATCH);
      expect(output.storedFingerprint).toBe(FINGERPRINT);
      expect(output.message).toContain('does not match');
    });

    it('returns NOT_FOUND for a device with no on-chain record', async () => {
      const ctx = createMockContext(1_700_000_500);
      const output = JSON.parse(
        await contract.VerifyPassportFingerprint(ctx, 'DEV-MISSING', FINGERPRINT)
      );
      expect(output.status).toBe(TrustVerificationStatus.NOT_FOUND);
      expect(output.storedFingerprint).toBeNull();
      expect(output.message).toContain('not found');
    });

    it('rejects a malformed fingerprint input', async () => {
      const ctx = await registeredContext();
      await expect(
        contract.VerifyPassportFingerprint(ctx, DEVICE_ID, 'short')
      ).rejects.toThrow(/valid SHA-256 hex string/);
    });

    it('is deterministic across repeated calls and identical contexts', async () => {
      const ctxA = await registeredContext(1_700_000_600);
      const ctxB = await registeredContext(1_700_000_600);

      const a1 = await contract.VerifyPassportFingerprint(ctxA, DEVICE_ID, FINGERPRINT);
      const a2 = await contract.VerifyPassportFingerprint(ctxA, DEVICE_ID, FINGERPRINT);
      const b1 = await contract.VerifyPassportFingerprint(ctxB, DEVICE_ID, FINGERPRINT);

      expect(a1).toBe(a2);
      expect(a1).toBe(b1);
    });
  });

  describe('Passport Anchoring (P5 FabricExternalTrustLedger interface)', () => {
    it('anchors a passport via AnchorDevicePassport (deviceId, fingerprint, algorithm)', async () => {
      const ctx = await registeredContext();
      const newFp = 'b'.repeat(64);

      const anchor = JSON.parse(await contract.AnchorDevicePassport(ctx, DEVICE_ID, newFp, 'sha256'));
      expect(anchor.deviceId).toBe(DEVICE_ID);
      expect(anchor.passportFingerprint).toBe(newFp);
      expect(anchor.algorithm).toBe('sha256');
      expect(anchor.transactionId).toBeDefined();
      expect(anchor.anchoredAt).toBeDefined();

      // Verification now prefers the anchor record
      const match = JSON.parse(await contract.VerifyPassportFingerprint(ctx, DEVICE_ID, newFp));
      expect(match.status).toBe(TrustVerificationStatus.MATCH);
      expect(match.message).toContain('anchor');

      const stale = JSON.parse(await contract.VerifyPassportFingerprint(ctx, DEVICE_ID, FINGERPRINT));
      expect(stale.status).toBe(TrustVerificationStatus.MISMATCH);
    });

    it('defaults the algorithm to sha256 and updates the device fingerprint', async () => {
      const ctx = await registeredContext();
      const newFp = 'c'.repeat(64);

      const anchor = JSON.parse(await contract.AnchorDevicePassport(ctx, DEVICE_ID, newFp));
      expect(anchor.algorithm).toBe('sha256');

      const { device } = JSON.parse(await contract.GetDevice(ctx, DEVICE_ID)) as {
        device: DeviceAsset;
      };
      expect(device.passportFingerprint).toBe(newFp);
    });

    it('GetDeviceAnchor returns the anchor or null', async () => {
      const ctx = await registeredContext();
      expect(JSON.parse(await contract.GetDeviceAnchor(ctx, DEVICE_ID))).toBeNull();

      await contract.AnchorDevicePassport(ctx, DEVICE_ID, 'd'.repeat(64), 'sha256');
      const anchor = JSON.parse(await contract.GetDeviceAnchor(ctx, DEVICE_ID));
      expect(anchor.deviceId).toBe(DEVICE_ID);
      expect(anchor.algorithm).toBe('sha256');
    });

    it('rejects an unsupported algorithm and a malformed fingerprint', async () => {
      const ctx = await registeredContext();
      await expect(
        contract.AnchorDevicePassport(ctx, DEVICE_ID, 'e'.repeat(64), 'sha1')
      ).rejects.toThrow(/Unsupported fingerprint algorithm: sha1/);

      await expect(
        contract.AnchorDevicePassport(ctx, DEVICE_ID, 'not-a-hash', 'sha256')
      ).rejects.toThrow(/valid SHA-256 hex string/);
    });

    it('rejects anchoring a non-existent device', async () => {
      const ctx = createMockContext();
      await expect(
        contract.AnchorDevicePassport(ctx, 'DEV-MISSING', 'f'.repeat(64), 'sha256')
      ).rejects.toThrow('Device DEV-MISSING not found');
    });
  });

  describe('Read-Only Guarantees', () => {
    it('read-only queries never mutate ledger state', async () => {
      const ctx = await registeredContext();
      await contract.UpdateLifecycle(ctx, DEVICE_ID, 'CONFIRMED', recordHash('c'), '{}');
      await contract.AnchorDevicePassport(ctx, DEVICE_ID, 'b'.repeat(64), 'sha256');

      const stub = ctx.getMockStub();
      const before = JSON.stringify([...stub.getStateMap().entries()]);
      const beforeEvents = JSON.stringify([...stub.getEvents().entries()]);

      await contract.GetDevice(ctx, DEVICE_ID);
      await contract.DeviceExists(ctx, DEVICE_ID);
      await contract.GetDeviceHistory(ctx, DEVICE_ID);
      await contract.VerifyPassportFingerprint(ctx, DEVICE_ID, FINGERPRINT);
      await contract.GetDeviceAnchor(ctx, DEVICE_ID);
      await contract.GetAllDeviceIds(ctx);

      const after = JSON.stringify([...stub.getStateMap().entries()]);
      const afterEvents = JSON.stringify([...stub.getEvents().entries()]);

      expect(after).toBe(before);
      expect(afterEvents).toBe(beforeEvents);
    });
  });

  describe('Chaincode Event Emission', () => {
    it('emits DEVICE_REGISTERED on registration', async () => {
      const ctx = await registeredContext();
      const events = ctx.getMockStub().getEvents();
      expect(events.has('DEVICE_REGISTERED')).toBe(true);

      const payload = JSON.parse(events.get('DEVICE_REGISTERED')!.toString());
      expect(payload.deviceId).toBe(DEVICE_ID);
      expect(payload.passportFingerprint).toBe(FINGERPRINT);
    });

    it('emits DEVICE_LIFECYCLE_UPDATED with prev/new state on transitions', async () => {
      const ctx = await registeredContext();
      await contract.UpdateLifecycle(ctx, DEVICE_ID, 'CONFIRMED', recordHash('c'), '{}');

      const events = ctx.getMockStub().getEvents();
      expect(events.has('DEVICE_LIFECYCLE_UPDATED')).toBe(true);
      const payload = JSON.parse(events.get('DEVICE_LIFECYCLE_UPDATED')!.toString());
      expect(payload.previousState).toBe(LifecycleState.DETECTED);
      expect(payload.newState).toBe(LifecycleState.CONFIRMED);
      expect(payload.eventType).toBe(DeviceEventType.DEVICE_CONFIRMED);
    });

    it('emits PASSPORT_ANCHORED when a passport is anchored', async () => {
      const ctx = await registeredContext();
      await contract.AnchorDevicePassport(ctx, DEVICE_ID, 'c'.repeat(64), 'sha256');

      const events = ctx.getMockStub().getEvents();
      expect(events.has('PASSPORT_ANCHORED')).toBe(true);
      const payload = JSON.parse(events.get('PASSPORT_ANCHORED')!.toString());
      expect(payload.passportFingerprint).toBe('c'.repeat(64));
    });
  });

  describe('Authorization', () => {
    it('requires PLATFORM role to register a device', async () => {
      const ctx = createMockContext(1_700_000_700, 'CollectorOrg', 'collector-user');
      await expect(
        contract.RegisterDevice(
          ctx, DEVICE_ID, ECO_ID, CLASS_ID, DEVICE_TYPE, FINGERPRINT, '{}'
        )
      ).rejects.toThrow(/Authorization failed/);
    });

    it('requires PLATFORM role to update lifecycle', async () => {
      // Same ledger, different submitting identity: the device genuinely exists,
      // so the rejection can only come from the authorization check.
      const ctx = await registeredContext();
      ctx.setClientIdentity('CollectorOrg', 'collector-user');

      await expect(
        contract.UpdateLifecycle(ctx, DEVICE_ID, 'CONFIRMED', recordHash('c'), '{}')
      ).rejects.toThrow(/Authorization failed/);

      // A rejected transition must leave the asset untouched.
      const { device } = JSON.parse(await contract.GetDevice(ctx, DEVICE_ID));
      expect(device.lifecycleState).toBe(LifecycleState.DETECTED);
    });

    it('requires PLATFORM role to anchor a passport', async () => {
      const ctx = await registeredContext();
      ctx.setClientIdentity('RecyclerOrg', 'recycler-user');

      await expect(
        contract.AnchorDevicePassport(ctx, DEVICE_ID, 'd'.repeat(64), 'sha256')
      ).rejects.toThrow(/Authorization failed/);

      // A rejected anchor must not overwrite the registered fingerprint.
      const { device } = JSON.parse(await contract.GetDevice(ctx, DEVICE_ID));
      expect(device.passportFingerprint).toBe(FINGERPRINT);
    });

    it('records the submitting identity as the authoritative actor', async () => {
      const ctx = await registeredContext(1_700_001_000, 'EcoTraceOrg', 'platform-admin');
      await contract.UpdateLifecycle(ctx, DEVICE_ID, 'CONFIRMED', recordHash('c'), '{}');

      const output = JSON.parse(await contract.GetDeviceHistory(ctx, DEVICE_ID));
      const transition = output.history[1];
      expect(transition.actorRole).toBe(ActorRole.PLATFORM);
      expect(transition.actorId).toBe('platform-admin');
    });
  });

  describe('Deterministic Serialization / Response Behavior', () => {
    it('produces byte-identical registration JSON for identical inputs', async () => {
      const ctxA = createMockContext(1_700_001_100);
      const ctxB = createMockContext(1_700_001_100);

      const resultA = await contract.RegisterDevice(
        ctxA, 'DEV-DET-A', ECO_ID, CLASS_ID, DEVICE_TYPE, FINGERPRINT, '{}'
      );
      const resultB = await contract.RegisterDevice(
        ctxB, 'DEV-DET-A', ECO_ID, CLASS_ID, DEVICE_TYPE, FINGERPRINT, '{}'
      );
      expect(resultA).toBe(resultB);
    });

    it('normalizes fingerprints to lowercase for stable comparison', async () => {
      const ctx = createMockContext();
      const mixed = 'AbCd'.repeat(16); // 64 hex chars, mixed case
      await contract.RegisterDevice(
        ctx, DEVICE_ID, ECO_ID, CLASS_ID, DEVICE_TYPE, mixed, '{}'
      );

      const { device } = JSON.parse(await contract.GetDevice(ctx, DEVICE_ID)) as {
        device: DeviceAsset;
      };
      expect(device.passportFingerprint).toBe(mixed.toLowerCase());

      const output = JSON.parse(
        await contract.VerifyPassportFingerprint(ctx, DEVICE_ID, mixed.toUpperCase())
      );
      expect(output.status).toBe(TrustVerificationStatus.MATCH);
    });
  });

  describe('Utility Functions (shared with contract)', () => {
    it('isValidSha256Hex accepts 64 hex chars only', () => {
      expect(isValidSha256Hex('a'.repeat(64))).toBe(true);
      expect(isValidSha256Hex('A'.repeat(64))).toBe(true);
      expect(isValidSha256Hex('a'.repeat(63))).toBe(false);
      expect(isValidSha256Hex('z'.repeat(64))).toBe(false);
      expect(isValidSha256Hex('')).toBe(false);
    });

    it('parseLifecycleState parses valid states and rejects unknown values', () => {
      expect(parseLifecycleState('DETECTED')).toBe(LifecycleState.DETECTED);
      expect(parseLifecycleState('ENRICHED')).toBe(LifecycleState.ENRICHED);
      expect(parseLifecycleState('COLLECTED')).toBeUndefined();
      expect(parseLifecycleState('bogus')).toBeUndefined();
    });

    it('isValidTransition enforces the P5 progression', () => {
      expect(isValidTransition(LifecycleState.DETECTED, LifecycleState.CONFIRMED)).toBe(true);
      expect(isValidTransition(LifecycleState.CONFIRMED, LifecycleState.REGISTERED)).toBe(true);
      expect(isValidTransition(LifecycleState.REGISTERED, LifecycleState.ENRICHED)).toBe(true);
      expect(isValidTransition(LifecycleState.ENRICHED, LifecycleState.CONFIRMED)).toBe(false);
      expect(isValidTransition(LifecycleState.CONFIRMED, LifecycleState.DETECTED)).toBe(false);
      expect(isValidTransition(LifecycleState.DETECTED, LifecycleState.REGISTERED)).toBe(false);
    });

    it('resolveActorRole derives roles from MSP/identity keywords', () => {
      expect(resolveActorRole('EcoTraceOrg', 'platform-admin')).toBe(ActorRole.PLATFORM);
      expect(resolveActorRole('CollectorOrg', 'collector-user')).toBe(ActorRole.COLLECTOR);
      expect(resolveActorRole('RecyclerOrg', 'recycler-user')).toBe(ActorRole.RECYCLER);
      expect(resolveActorRole('GovOrg', 'government-auditor')).toBe(ActorRole.GOVERNMENT);
      expect(resolveActorRole('OwnerOrg', 'owner-user')).toBe(ActorRole.OWNER);
    });

    it('exposes the authoritative 19-class taxonomy', () => {
      expect(CANONICAL_CLASS_NAMES).toHaveLength(19);
      expect(CANONICAL_CLASS_NAMES[0]).toBe('laptop');
      expect(CANONICAL_CLASS_NAMES[3]).toBe('desktop');
      expect(CANONICAL_CLASS_NAMES[5]).toBe('monitor');
      expect(CANONICAL_CLASS_NAMES[6]).toBe('crt_monitor');
      expect(CANONICAL_CLASS_NAMES[18]).toBe('battery');
      expect(isValidClassId(0)).toBe(true);
      expect(isValidClassId(18)).toBe(true);
      expect(isValidClassId(19)).toBe(false);
      expect(isValidClassId(-1)).toBe(false);
      expect(getCanonicalDeviceType(0)).toBe('laptop');
      expect(getCanonicalDeviceType(18)).toBe('battery');
      expect(getCanonicalDeviceType(19)).toBeNull();
    });
  });
});
