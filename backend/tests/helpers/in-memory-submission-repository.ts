import { randomUUID } from 'node:crypto';
import { UserRole } from '@prisma/client';
import type {
  CollectorRecord,
  CreateSubmissionRepositoryInput,
  SubmissionRecord,
  SubmissionRepository,
  UpdateSubmissionRepositoryInput,
} from '@modules/submission';

/** A submission repository preloaded with known collector rows for tests. */
export interface SeededSubmissionRepository {
  readonly repository: SubmissionRepository;
  /** Registers a user the repository can resolve as an assignment target. */
  addUser(user: CollectorRecord): void;
}

/**
 * In-memory implementation of the submission repository for integration tests.
 * Lets the full HTTP stack run through Supertest without a database.
 * Mirrors the Prisma-backed repository's ordering (newest first) and semantics.
 */
export function createInMemorySubmissionRepository(): SubmissionRepository {
  return createSeededSubmissionRepository().repository;
}

/** Active statuses surfaced on the collector dashboard — mirrors the Prisma repo. */
const ACTIVE_COLLECTOR_STATUSES: readonly SubmissionRecord['status'][] = [
  'ASSIGNED',
  'ACCEPTED',
  'IN_PROGRESS',
];

/**
 * Variant that also exposes a user store so tests can register collectors that
 * assignCollector() validates against. Timestamps are monotonic for
 * deterministic ordering.
 */
export function createSeededSubmissionRepository(): SeededSubmissionRepository {
  const byId = new Map<string, SubmissionRecord>();
  const usersById = new Map<string, CollectorRecord>();
  let clock = 0;

  // Monotonic timestamps keep createdAt ordering deterministic across fast writes.
  const nextDate = (): Date => new Date(Date.UTC(2026, 6, 22, 0, 0, 0, clock++));

  const byCreatedAtDesc = (a: SubmissionRecord, b: SubmissionRecord): number =>
    b.createdAt.getTime() - a.createdAt.getTime();

  const mustGet = (id: string): SubmissionRecord => {
    const existing = byId.get(id);
    if (!existing) {
      // Mirrors Prisma's update-on-missing behaviour; the service guards this.
      throw new Error(`Submission ${id} not found`);
    }
    return existing;
  };

  const repository: SubmissionRepository = {
    create(input: CreateSubmissionRepositoryInput): Promise<SubmissionRecord> {
      const now = nextDate();
      const record: SubmissionRecord = {
        id: randomUUID(),
        userId: input.userId,
        category: input.category,
        description: input.description ?? null,
        estimatedWeight: input.estimatedWeight,
        address: input.address,
        latitude: input.latitude,
        longitude: input.longitude,
        imageUrls: input.imageUrls ? [...input.imageUrls] : [],
        status: 'PENDING',
        assignedCollectorId: null,
        assignedRecyclerId: null,
        pickupScheduledAt: null,
        completedAt: null,
        createdAt: now,
        updatedAt: now,
      };
      byId.set(record.id, record);
      return Promise.resolve(record);
    },

    findById(id: string): Promise<SubmissionRecord | null> {
      return Promise.resolve(byId.get(id) ?? null);
    },

    findByUser(userId: string): Promise<SubmissionRecord[]> {
      const rows = [...byId.values()].filter((r) => r.userId === userId).sort(byCreatedAtDesc);
      return Promise.resolve(rows);
    },

    findAll(): Promise<SubmissionRecord[]> {
      return Promise.resolve([...byId.values()].sort(byCreatedAtDesc));
    },

    update(id: string, input: UpdateSubmissionRepositoryInput): Promise<SubmissionRecord> {
      const existing = byId.get(id);
      if (!existing) {
        // Mirrors Prisma's update-on-missing behaviour; the service guards this.
        return Promise.reject(new Error(`Submission ${id} not found`));
      }
      const updated: SubmissionRecord = {
        ...existing,
        ...(input.category !== undefined ? { category: input.category } : {}),
        ...(input.description !== undefined ? { description: input.description } : {}),
        ...(input.estimatedWeight !== undefined ? { estimatedWeight: input.estimatedWeight } : {}),
        ...(input.address !== undefined ? { address: input.address } : {}),
        ...(input.latitude !== undefined ? { latitude: input.latitude } : {}),
        ...(input.longitude !== undefined ? { longitude: input.longitude } : {}),
        ...(input.imageUrls !== undefined ? { imageUrls: [...input.imageUrls] } : {}),
        updatedAt: nextDate(),
      };
      byId.set(id, updated);
      return Promise.resolve(updated);
    },

    delete(id: string): Promise<void> {
      byId.delete(id);
      return Promise.resolve();
    },

    assignCollector(id: string, collectorId: string): Promise<SubmissionRecord> {
      const updated: SubmissionRecord = {
        ...mustGet(id),
        assignedCollectorId: collectorId,
        status: 'ASSIGNED',
        updatedAt: nextDate(),
      };
      byId.set(id, updated);
      return Promise.resolve(updated);
    },

    updateStatus(id: string, status: SubmissionRecord['status']): Promise<SubmissionRecord> {
      const updated: SubmissionRecord = { ...mustGet(id), status, updatedAt: nextDate() };
      byId.set(id, updated);
      return Promise.resolve(updated);
    },

    updatePickupSchedule(id: string, pickupScheduledAt: Date): Promise<SubmissionRecord> {
      const updated: SubmissionRecord = {
        ...mustGet(id),
        pickupScheduledAt,
        updatedAt: nextDate(),
      };
      byId.set(id, updated);
      return Promise.resolve(updated);
    },

    findByCollector(collectorId: string): Promise<SubmissionRecord[]> {
      const rows = [...byId.values()]
        .filter((r) => r.assignedCollectorId === collectorId)
        .sort(byCreatedAtDesc);
      return Promise.resolve(rows);
    },

    findCollectorAssignments(collectorId: string): Promise<SubmissionRecord[]> {
      const rows = [...byId.values()]
        .filter(
          (r) =>
            r.assignedCollectorId === collectorId && ACTIVE_COLLECTOR_STATUSES.includes(r.status),
        )
        .sort(byCreatedAtDesc);
      return Promise.resolve(rows);
    },

    findCollectorById(collectorId: string): Promise<CollectorRecord | null> {
      return Promise.resolve(usersById.get(collectorId) ?? null);
    },
  };

  return {
    repository,
    addUser(user: CollectorRecord): void {
      usersById.set(user.id, user);
    },
  };
}

/** Convenience: a CollectorRecord for an active COLLECTOR with the given id. */
export function activeCollector(id: string): CollectorRecord {
  return { id, role: UserRole.COLLECTOR, isActive: true };
}
