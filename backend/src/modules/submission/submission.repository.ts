import type { PrismaClient, SubmissionStatus } from '@prisma/client';

/**
 * Repositories are the only place Prisma is used for the submission module.
 * Services depend on these interfaces, never on Prisma directly —
 * see docs/engineering/06_BACKEND.md (Layering).
 */

/** Input for creating a submission row. Owner and status are set by the service. */
export interface CreateSubmissionInput {
  readonly userId: string;
  readonly category: string;
  readonly description?: string | undefined;
  readonly estimatedWeight: number;
  readonly address: string;
  readonly latitude: number;
  readonly longitude: number;
  readonly imageUrls?: readonly string[] | undefined;
}

/** Mutable fields on an update. Only provided keys are written. */
export interface UpdateSubmissionInput {
  readonly category?: string | undefined;
  readonly description?: string | undefined;
  readonly estimatedWeight?: number | undefined;
  readonly address?: string | undefined;
  readonly latitude?: number | undefined;
  readonly longitude?: number | undefined;
  readonly imageUrls?: readonly string[] | undefined;
}

/** Submission row as read by the module. */
export interface SubmissionRecord {
  readonly id: string;
  readonly userId: string;
  readonly category: string;
  readonly description: string | null;
  readonly estimatedWeight: number;
  readonly address: string;
  readonly latitude: number;
  readonly longitude: number;
  readonly imageUrls: string[];
  readonly status: SubmissionStatus;
  readonly assignedCollectorId: string | null;
  readonly assignedRecyclerId: string | null;
  readonly pickupScheduledAt: Date | null;
  readonly completedAt: Date | null;
  readonly createdAt: Date;
  readonly updatedAt: Date;
}

export interface SubmissionRepository {
  create(input: CreateSubmissionInput): Promise<SubmissionRecord>;
  findById(id: string): Promise<SubmissionRecord | null>;
  /** Submissions owned by a user, newest first. */
  findByUser(userId: string): Promise<SubmissionRecord[]>;
  /** Every submission, newest first (admin view). */
  findAll(): Promise<SubmissionRecord[]>;
  update(id: string, input: UpdateSubmissionInput): Promise<SubmissionRecord>;
  delete(id: string): Promise<void>;
}

const submissionSelect = {
  id: true,
  userId: true,
  category: true,
  description: true,
  estimatedWeight: true,
  address: true,
  latitude: true,
  longitude: true,
  imageUrls: true,
  status: true,
  assignedCollectorId: true,
  assignedRecyclerId: true,
  pickupScheduledAt: true,
  completedAt: true,
  createdAt: true,
  updatedAt: true,
} as const;

/** Strips undefined keys so Prisma only writes fields the caller supplied. */
function toUpdateData(input: UpdateSubmissionInput): Record<string, unknown> {
  const data: Record<string, unknown> = {};
  if (input.category !== undefined) data['category'] = input.category;
  if (input.description !== undefined) data['description'] = input.description;
  if (input.estimatedWeight !== undefined) data['estimatedWeight'] = input.estimatedWeight;
  if (input.address !== undefined) data['address'] = input.address;
  if (input.latitude !== undefined) data['latitude'] = input.latitude;
  if (input.longitude !== undefined) data['longitude'] = input.longitude;
  if (input.imageUrls !== undefined) data['imageUrls'] = input.imageUrls;
  return data;
}

/** Creates the submission repository backed by Prisma. */
export function createSubmissionRepository(deps: {
  readonly prisma: PrismaClient;
}): SubmissionRepository {
  const { prisma } = deps;

  return {
    async create(input: CreateSubmissionInput): Promise<SubmissionRecord> {
      return prisma.submission.create({
        data: {
          userId: input.userId,
          category: input.category,
          description: input.description ?? null,
          estimatedWeight: input.estimatedWeight,
          address: input.address,
          latitude: input.latitude,
          longitude: input.longitude,
          imageUrls: input.imageUrls ? [...input.imageUrls] : [],
        },
        select: submissionSelect,
      });
    },

    async findById(id: string): Promise<SubmissionRecord | null> {
      return prisma.submission.findUnique({ where: { id }, select: submissionSelect });
    },

    async findByUser(userId: string): Promise<SubmissionRecord[]> {
      return prisma.submission.findMany({
        where: { userId },
        orderBy: { createdAt: 'desc' },
        select: submissionSelect,
      });
    },

    async findAll(): Promise<SubmissionRecord[]> {
      return prisma.submission.findMany({
        orderBy: { createdAt: 'desc' },
        select: submissionSelect,
      });
    },

    async update(id: string, input: UpdateSubmissionInput): Promise<SubmissionRecord> {
      return prisma.submission.update({
        where: { id },
        data: toUpdateData(input),
        select: submissionSelect,
      });
    },

    async delete(id: string): Promise<void> {
      await prisma.submission.delete({ where: { id } });
    },
  };
}
