import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { StatCard } from '@/components/dashboard/StatCard';
import { icons } from '@/lib/icons';
import { toApiError } from '@/api/client';
import type { RewardSummary, Submission } from '@/types';
import { formatMetric, formatPoints } from '@/features/consumer/lib/reward-display';
import { useIssueReward } from '@/features/admin/hooks/use-admin';

interface IssueRewardDialogProps {
  submission: Submission;
  /** Optional custom trigger; defaults to an outline "Issue Reward" button. */
  trigger?: React.ReactNode;
}

/**
 * Manual reward issuance for a RECYCLED submission (admin override).
 *
 * A two-step flow inside one dialog: confirm → issue → show the backend result.
 * The reward is computed entirely by the backend (POST /rewards/issue/:id); the
 * client only displays the returned `RewardSummary` verbatim and never computes
 * any figure. Callers should render this only for eligible submissions.
 */
export function IssueRewardDialog({ submission, trigger }: IssueRewardDialogProps) {
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<RewardSummary | null>(null);
  const { mutateAsync, isPending } = useIssueReward();
  const CoinsIcon = icons.coins;

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) setResult(null);
  };

  const handleIssue = async () => {
    try {
      const summary = await mutateAsync(submission.id);
      toast.success('Reward issued.');
      setResult(summary);
    } catch (error) {
      toast.error(toApiError(error).message);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button variant="outline" size="sm">
            <CoinsIcon aria-hidden="true" />
            Issue Reward
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        {result ? (
          <>
            <DialogHeader>
              <DialogTitle>Reward issued</DialogTitle>
              <DialogDescription>
                The backend issued the following reward for the “{submission.category}” submission.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 sm:grid-cols-2">
              <StatCard
                label="GreenCoins Awarded"
                value={formatPoints(result.greenCoinsAwarded)}
                icon="coins"
              />
              <StatCard
                label="Updated Balance"
                value={formatPoints(result.updatedBalance)}
                icon="coins"
              />
              <StatCard
                label="CO₂ Saved"
                value={formatMetric(result.sustainability.co2Saved, result.sustainability.co2Unit)}
                icon="recycler"
              />
              <StatCard
                label="Energy Saved"
                value={formatMetric(
                  result.sustainability.energySaved,
                  result.sustainability.energyUnit,
                )}
                icon="dashboard"
              />
            </div>
            <DialogFooter>
              <Button onClick={() => handleOpenChange(false)} className="w-full sm:w-auto">
                Done
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Issue reward?</DialogTitle>
              <DialogDescription>
                Manually issue the reward for the “{submission.category}” submission. Points and
                sustainability metrics are calculated by the system. This can only be done once.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => handleOpenChange(false)}
                disabled={isPending}
              >
                Cancel
              </Button>
              <Button onClick={handleIssue} disabled={isPending}>
                {isPending && <icons.spinner className="animate-spin" aria-hidden="true" />}
                Issue Reward
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
