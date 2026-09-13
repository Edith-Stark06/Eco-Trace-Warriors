import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { icons } from '@/lib/icons';
import type { CreateUserResult } from '@/types';

interface GeneratedPasswordDialogProps {
  /** The one-shot creation result, or null while there is nothing to show. */
  result: CreateUserResult | null;
  /**
   * Called when the dialog is dismissed. The caller MUST clear the held
   * result here (e.g. `setResult(null)`) — this component holds no copy of
   * its own, so once the parent clears it, the plaintext password is gone
   * from the UI entirely: not in localStorage, sessionStorage, the TanStack
   * Query cache, or a URL — it only ever existed in this one render.
   */
  onClose: () => void;
}

/**
 * Shows the server-generated password exactly once, immediately after
 * POST /users succeeds. Mirrors RewardSuccessDialog's result-driven pattern:
 * open state is derived from `result` (non-null → open), and dismissing
 * always calls `onClose`, which the parent uses to drop the password from
 * memory for good.
 */
export function GeneratedPasswordDialog({ result, onClose }: GeneratedPasswordDialogProps) {
  const handleCopy = () => {
    if (!result) return;
    void navigator.clipboard
      .writeText(result.generatedPassword)
      .then(() => toast.success('Password copied to clipboard.'))
      .catch(() => toast.error('Could not copy the password. Please copy it manually.'));
  };

  return (
    <Dialog open={result !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        {result && (
          <>
            <DialogHeader>
              <DialogTitle>User created</DialogTitle>
              <DialogDescription>
                {result.user.email} was created as {result.user.role}.
              </DialogDescription>
            </DialogHeader>

            <Alert variant="destructive">
              <icons.alert className="size-4" aria-hidden="true" />
              <AlertDescription>
                Save this password securely. It will not be shown again.
              </AlertDescription>
            </Alert>

            <div className="flex flex-col gap-2">
              <Label htmlFor="generated-password">Generated password</Label>
              <div className="flex gap-2">
                <Input
                  id="generated-password"
                  readOnly
                  value={result.generatedPassword}
                  className="font-mono"
                  onFocus={(e) => e.currentTarget.select()}
                />
                <Button type="button" variant="outline" size="icon" onClick={handleCopy}>
                  <icons.copy aria-hidden="true" />
                  <span className="sr-only">Copy password</span>
                </Button>
              </div>
            </div>

            <DialogFooter>
              <Button onClick={onClose} className="w-full sm:w-auto">
                Done
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
