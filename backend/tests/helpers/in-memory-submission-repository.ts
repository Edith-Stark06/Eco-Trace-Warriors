import { randomUUID } from 'node:crypto';
import type {
  CreateSubmissionRepositoryInput,
  SubmissionRecord,
  SubmissionRepository,
  UpdateSubmissionRepositoryInput,
} from '@modules/submission';

/**
 * In-memory implementation of the submission repository for integration tests.
 * Lets the full HTTP stack run through Supertest without a database.
 * Mirrors the Prisma-backed repository's ordering (newest first) and semantics.
 */
export function createInMemorySubmissionRepository(): SubmissionRepository {
  const byId = new Map<string, SubmissionRecord>();
  let clock = 0;

  // Monotonic timestamps keep createdAt ordering deterministic across fast writes.
  const nextDate = (): Date => new Date(Date.UTC(2026, 6, 22, 0, 0, 0, clock++));

  const byCreatedAtDesc = (a: SubmissionRecord, b: SubmissionRecord): number =>
    b.createdAt.getTime() - a.createdAt.getTime();

  return {
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
  };
}
