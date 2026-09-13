-- AlterTable
ALTER TABLE "submissions" ADD COLUMN     "deviceId" TEXT,
ADD COLUMN     "ecoId" TEXT;

-- CreateIndex
CREATE UNIQUE INDEX "submissions_deviceId_key" ON "submissions"("deviceId");

-- CreateIndex
CREATE UNIQUE INDEX "submissions_ecoId_key" ON "submissions"("ecoId");
