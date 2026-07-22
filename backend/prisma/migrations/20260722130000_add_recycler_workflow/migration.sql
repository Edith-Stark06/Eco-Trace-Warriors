-- AlterEnum
ALTER TYPE "SubmissionStatus" ADD VALUE 'RECYCLING' BEFORE 'RECYCLED';

-- AlterTable
ALTER TABLE "submissions" ADD COLUMN     "materialRecovery" JSONB,
ADD COLUMN     "processingStartedAt" TIMESTAMP(3),
ADD COLUMN     "recoveredWeight" DOUBLE PRECISION,
ADD COLUMN     "recycledAt" TIMESTAMP(3),
ADD COLUMN     "recyclerNotes" TEXT;
