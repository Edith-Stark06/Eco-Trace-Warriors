import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { StatCard } from '@/components/dashboard/StatCard';
import { icons } from '@/lib/icons';
import type { CompleteRecyclingResult } from '@/types';
import { formatMetric, formatPoints } from '@/features/consumer/lib/reward-display';
import { statusLabel } from '@/features/consumer/lib/submission-display';

interface RewardSuccessDialogProps {
  /** The backend completion result, or null while there is nothing to show. */
  result: CompleteRecyclingResult | null;
  /** Called when the dialog is dismissed (Continue / overlay / escape). */
  onClose: () => void;
}

/**
 * Post-completion reward summary. Presents the GreenCoins awarded, the updated
 * balance, and the sustainability impact exactly as returned by the backend —
 * no value is recomputed on the client. Open state is derived from `result`
 * (non-null → open); dismissing calls `onClose`.
 */
export function RewardSuccessDialog({ result, onClose }: RewardSuccessDialogProps) {
  const SuccessIcon = icons.check;

  return (
    <Dialog open={result !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        {result && (
          <>
            <DialogHeader>
              <div
                className="mx-auto flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary"
                aria-hidden="true"
              >
                <SuccessIcon className="size-6" />
              </div>
              <DialogTitle className="text-center">Congratulations!</DialogTitle>
              <DialogDescription className="text-center">
                Recycling completed and rewards have been issued for this submission.
              </DialogDescription>
            </DialogHeader>

            <div className="grid gap-4 sm:grid-cols-2">
              <StatCard
                label="GreenCoins Awarded"
                value={formatPoints(result.reward.greenCoinsAwarded)}
                icon="coins"
              />
              <StatCard
                label="Updated Balance"
                value={formatPoints(result.reward.updatedBalance)}
                icon="coins"
              />
              <StatCard
                label="CO₂ Saved"
                value={formatMetric(
                  result.reward.sustainability.co2Saved,
                  result.reward.sustainability.co2Unit,
                )}
                icon="recycler"
              />
              <StatCard
                label="Energy Saved"
                value={formatMetric(
                  result.reward.sustainability.energySaved,
                  result.reward.sustainability.energyUnit,
                )}
                icon="dashboard"
              />
              <StatCard
                label="Landfill Diverted"
                value={formatMetric(
                  result.reward.sustainability.landfillDiverted,
                  result.reward.sustainability.landfillUnit,
                )}
                icon="package"
              />
              <StatCard
                label="Submission Status"
                value={statusLabel(result.submission.status)}
                icon="check"
              />
            </div>

            <DialogFooter>
              <Button onClick={onClose} className="w-full sm:w-auto">
                Continue
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
