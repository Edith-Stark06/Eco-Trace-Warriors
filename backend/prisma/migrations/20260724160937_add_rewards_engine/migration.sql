-- CreateEnum
CREATE TYPE "RewardReason" AS ENUM ('RECYCLING', 'BONUS', 'CAMPAIGN', 'ADJUSTMENT', 'REDEMPTION');

-- AlterTable
ALTER TABLE "submissions" ADD COLUMN     "co2Saved" DOUBLE PRECISION,
ADD COLUMN     "energySaved" DOUBLE PRECISION,
ADD COLUMN     "landfillDiverted" DOUBLE PRECISION,
ADD COLUMN     "rewardIssued" BOOLEAN NOT NULL DEFAULT false;

-- AlterTable
ALTER TABLE "users" ADD COLUMN     "greenCoins" INTEGER NOT NULL DEFAULT 0;

-- CreateTable
CREATE TABLE "reward_transactions" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "submissionId" TEXT NOT NULL,
    "points" INTEGER NOT NULL,
    "reason" "RewardReason" NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "reward_transactions_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "reward_transactions_submissionId_key" ON "reward_transactions"("submissionId");

-- CreateIndex
CREATE INDEX "reward_transactions_userId_idx" ON "reward_transactions"("userId");

-- AddForeignKey
ALTER TABLE "reward_transactions" ADD CONSTRAINT "reward_transactions_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "reward_transactions" ADD CONSTRAINT "reward_transactions_submissionId_fkey" FOREIGN KEY ("submissionId") REFERENCES "submissions"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
