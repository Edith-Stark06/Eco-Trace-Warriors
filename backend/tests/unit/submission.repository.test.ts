import { UserRole } from '@prisma/client';
import type { SubmissionRepository } from '@modules/submission';
import {
  activeCollector,
  activeRecycler,
  createSeededSubmissionRepository,
} from '../helpers/in-memory-submission-repository';

/**
 * Contract tests for the collector-workflow repository methods, exercised
 * against the in-memory mirror. These lock the behaviour the Prisma-backed
 * repository must also honour: assignment sets ASSIGNED, the dashboard query
 * filters to active statuses, and both listings are newest-first.
 */

const baseInput = {
  userId: 'user-1',
  category: 'Laptop',
  estimatedWeight: 2.5,
  address: '12 MG Road, Bengaluru',
  latitude: 12.9716,
  longitude: 77.5946,
};

function buildRepo(): SubmissionRepository {
  const seeded = createSeededSubmissionRepository();
  seeded.addUser(activeCollector('collector-1'));
  return seeded.repository;
}

describe('submission repository — collector workflow', () => {
  describe('assignCollector', () => {
    it('sets the assigned collector and moves the row to ASSIGNED', async () => {
      const repo = buildRepo();
      const created = await repo.create(baseInput);

      const assigned = await repo.assignCollector(created.id, 'collector-1');

      expect(assigned.assignedCollectorId).toBe('collector-1');
      expect(assigned.status).toBe('ASSIGNED');
    });
  });

  describe('updateStatus', () => {
    it('writes the new status without touching assignment', async () => {
      const repo = buildRepo();
      const created = await repo.create(baseInput);
      await repo.assignCollector(created.id, 'collector-1');

      const accepted = await repo.updateStatus(created.id, 'ACCEPTED');

      expect(accepted.status).toBe('ACCEPTED');
      expect(accepted.assignedCollectorId).toBe('collector-1');
    });
  });

  describe('updatePickupSchedule', () => {
    it('stamps the pickup time', async () => {
      const repo = buildRepo();
      const created = await repo.create(baseInput);
      const when = new Date('2026-07-22T09:00:00.000Z');

      const updated = await repo.updatePickupSchedule(created.id, when);

      expect(updated.pickupScheduledAt?.toISOString()).toBe('2026-07-22T09:00:00.000Z');
    });
  });

  describe('findByCollector', () => {
    it('returns every submission assigned to the collector, newest first', async () => {
      const repo = buildRepo();
      const first = await repo.create(baseInput);
      const second = await repo.create(baseInput);
      await repo.assignCollector(first.id, 'collector-1');
      await repo.assignCollector(second.id, 'collector-1');

      const rows = await repo.findByCollector('collector-1');

      expect(rows.map((r) => r.id)).toEqual([second.id, first.id]);
    });

    it('excludes submissions assigned to other collectors', async () => {
      const repo = buildRepo();
      const mine = await repo.create(baseInput);
      const theirs = await repo.create(baseInput);
      await repo.assignCollector(mine.id, 'collector-1');
      await repo.assignCollector(theirs.id, 'collector-2');

      const rows = await repo.findByCollector('collector-1');

      expect(rows.map((r) => r.id)).toEqual([mine.id]);
    });
  });

  describe('findCollectorAssignments', () => {
    it('returns only ASSIGNED/ACCEPTED/IN_PROGRESS rows, newest first', async () => {
      const repo = buildRepo();
      const assigned = await repo.create(baseInput);
      const inProgress = await repo.create(baseInput);
      const collected = await repo.create(baseInput);
      await repo.assignCollector(assigned.id, 'collector-1');
      await repo.assignCollector(inProgress.id, 'collector-1');
      await repo.updateStatus(inProgress.id, 'ACCEPTED');
      await repo.updateStatus(inProgress.id, 'IN_PROGRESS');
      await repo.assignCollector(collected.id, 'collector-1');
      await repo.updateStatus(collected.id, 'ACCEPTED');
      await repo.updateStatus(collected.id, 'IN_PROGRESS');
      await repo.updateStatus(collected.id, 'COLLECTED');

      const rows = await repo.findCollectorAssignments('collector-1');

      expect(rows.map((r) => r.id)).toEqual([inProgress.id, assigned.id]);
    });
  });

  describe('findCollectorById', () => {
    it('resolves a seeded collector', async () => {
      const repo = buildRepo();

      const collector = await repo.findCollectorById('collector-1');

      expect(collector).toEqual({ id: 'collector-1', role: UserRole.COLLECTOR, isActive: true });
    });

    it('returns null for an unknown id', async () => {
      const repo = buildRepo();

      expect(await repo.findCollectorById('ghost')).toBeNull();
    });
  });
});

describe('submission repository — recycler workflow', () => {
  /** A repo seeded with both a collector and a recycler as assignment targets. */
  function buildRecyclerRepo(): SubmissionRepository {
    const seeded = createSeededSubmissionRepository();
    seeded.addUser(activeCollector('collector-1'));
    seeded.addUser(activeRecycler('recycler-1'));
    return seeded.repository;
  }

  /** Creates a submission and drives it to COLLECTED for recycler-flow tests. */
  async function createCollected(repo: SubmissionRepository): Promise<string> {
    const created = await repo.create(baseInput);
    await repo.assignCollector(created.id, 'collector-1');
    await repo.updateStatus(created.id, 'ACCEPTED');
    await repo.updateStatus(created.id, 'IN_PROGRESS');
    await repo.updateStatus(created.id, 'COLLECTED');
    return created.id;
  }

  describe('assignRecycler', () => {
    it('sets the assigned recycler without changing status', async () => {
      const repo = buildRecyclerRepo();
      const id = await createCollected(repo);

      const assigned = await repo.assignRecycler(id, 'recycler-1');

      expect(assigned.assignedRecyclerId).toBe('recycler-1');
      expect(assigned.status).toBe('COLLECTED');
    });
  });

  describe('updateRecyclerProcessing', () => {
    it('moves the row to RECYCLING and stamps the processing time', async () => {
      const repo = buildRecyclerRepo();
      const id = await createCollected(repo);
      await repo.assignRecycler(id, 'recycler-1');
      const when = new Date('2026-07-22T09:00:00.000Z');

      const updated = await repo.updateRecyclerProcessing(id, when);

      expect(updated.status).toBe('RECYCLING');
      expect(updated.processingStartedAt?.toISOString()).toBe('2026-07-22T09:00:00.000Z');
    });
  });

  describe('updateRecyclerCompletion', () => {
    it('moves the row to RECYCLED and records the recovery outcome', async () => {
      const repo = buildRecyclerRepo();
      const id = await createCollected(repo);
      await repo.assignRecycler(id, 'recycler-1');
      const when = new Date('2026-07-23T09:00:00.000Z');

      const updated = await repo.updateRecyclerCompletion(id, when, {
        recoveredWeight: 12.5,
        recyclerNotes: 'Separated lithium batteries.',
        materialRecovery: { plastic: 3.2, metal: 6.1, glass: 3.2 },
      });

      expect(updated.status).toBe('RECYCLED');
      expect(updated.recycledAt?.toISOString()).toBe('2026-07-23T09:00:00.000Z');
      expect(updated.recoveredWeight).toBe(12.5);
      expect(updated.recyclerNotes).toBe('Separated lithium batteries.');
      expect(updated.materialRecovery).toEqual({ plastic: 3.2, metal: 6.1, glass: 3.2 });
    });

    it('stores null material recovery when none is provided', async () => {
      const repo = buildRecyclerRepo();
      const id = await createCollected(repo);
      await repo.assignRecycler(id, 'recycler-1');

      const updated = await repo.updateRecyclerCompletion(id, new Date(), { recoveredWeight: 5 });

      expect(updated.recoveredWeight).toBe(5);
      expect(updated.recyclerNotes).toBeNull();
      expect(updated.materialRecovery).toBeNull();
    });
  });

  describe('findRecyclerAssignments', () => {
    it('returns only COLLECTED/RECYCLING rows for the recycler, newest first', async () => {
      const repo = buildRecyclerRepo();
      const collected = await createCollected(repo);
      const recycling = await createCollected(repo);
      const done = await createCollected(repo);
      await repo.assignRecycler(collected, 'recycler-1');
      await repo.assignRecycler(recycling, 'recycler-1');
      await repo.updateRecyclerProcessing(recycling, new Date());
      await repo.assignRecycler(done, 'recycler-1');
      await repo.updateRecyclerProcessing(done, new Date());
      await repo.updateRecyclerCompletion(done, new Date(), { recoveredWeight: 5 });

      const rows = await repo.findRecyclerAssignments('recycler-1');

      expect(rows.map((r) => r.id)).toEqual([recycling, collected]);
    });

    it('excludes submissions assigned to other recyclers', async () => {
      const repo = buildRecyclerRepo();
      const mine = await createCollected(repo);
      const theirs = await createCollected(repo);
      await repo.assignRecycler(mine, 'recycler-1');
      await repo.assignRecycler(theirs, 'recycler-2');

      const rows = await repo.findRecyclerAssignments('recycler-1');

      expect(rows.map((r) => r.id)).toEqual([mine]);
    });
  });

  describe('findRecyclerById', () => {
    it('resolves a seeded recycler', async () => {
      const repo = buildRecyclerRepo();

      const recycler = await repo.findRecyclerById('recycler-1');

      expect(recycler).toEqual({ id: 'recycler-1', role: UserRole.RECYCLER, isActive: true });
    });

    it('returns null for an unknown id', async () => {
      const repo = buildRecyclerRepo();

      expect(await repo.findRecyclerById('ghost')).toBeNull();
    });
  });
});
