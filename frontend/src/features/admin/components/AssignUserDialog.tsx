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
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { icons } from '@/lib/icons';
import { toApiError } from '@/api/client';
import type { PublicUser, Submission } from '@/types';

interface AssignUserDialogProps {
  submission: Submission;
  /** Eligible assignees for this role (from GET /users?role=). */
  candidates: readonly PublicUser[];
  /** True while the candidate list is loading. */
  isLoadingCandidates: boolean;
  /** True when the candidate query failed. */
  isCandidatesError: boolean;
  /** Whether the assignment request is in flight. */
  isPending: boolean;
  /** Performs the assignment; resolves on success, throws on failure. */
  onAssign: (userId: string) => Promise<unknown>;
  /** Copy for the trigger, title, and confirm button. */
  copy: {
    triggerLabel: string;
    title: string;
    description: string;
    selectLabel: string;
    selectPlaceholder: string;
    emptyMessage: string;
    confirmLabel: string;
    successMessage: string;
  };
}

/**
 * Shared assignment dialog for collector and recycler assignment.
 *
 * Select an eligible user → confirm → assign. The candidate list comes from the
 * backend directory lookup (GET /users?role=); the assignment itself is a PATCH
 * validated server-side. No client-side authorization — role guards live on the
 * backend. Callers render this only for submissions in an assignable status.
 */
export function AssignUserDialog({
  submission,
  candidates,
  isLoadingCandidates,
  isCandidatesError,
  isPending,
  onAssign,
  copy,
}: AssignUserDialogProps) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string>('');

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) setSelected('');
  };

  const handleAssign = async () => {
    if (!selected) return;
    try {
      await onAssign(selected);
      toast.success(copy.successMessage);
      handleOpenChange(false);
    } catch (error) {
      toast.error(toApiError(error).message);
    }
  };

  const noCandidates = !isLoadingCandidates && !isCandidatesError && candidates.length === 0;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          {copy.triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{copy.title}</DialogTitle>
          <DialogDescription>
            {copy.description} for the “{submission.category}” submission.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-2">
          <Label htmlFor="assign-user-select">{copy.selectLabel}</Label>
          {isLoadingCandidates ? (
            <p className="text-sm text-muted-foreground" aria-live="polite">
              Loading…
            </p>
          ) : isCandidatesError ? (
            <p className="text-sm text-destructive" role="alert">
              Could not load the list. Close and try again.
            </p>
          ) : noCandidates ? (
            <p className="text-sm text-muted-foreground">{copy.emptyMessage}</p>
          ) : (
            <Select value={selected} onValueChange={setSelected}>
              <SelectTrigger id="assign-user-select">
                <SelectValue placeholder={copy.selectPlaceholder} />
              </SelectTrigger>
              <SelectContent>
                {candidates.map((user) => (
                  <SelectItem key={user.id} value={user.id}>
                    {user.fullName}
                    {user.region ? ` — ${user.region}` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={isPending}>
            Cancel
          </Button>
          <Button onClick={handleAssign} disabled={isPending || !selected}>
            {isPending && <icons.spinner className="animate-spin" aria-hidden="true" />}
            {copy.confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
