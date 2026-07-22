import { UserRole } from '@prisma/client';
import type { SubmissionRepository } from '@modules/submission';
import {
  activeCollector,
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
