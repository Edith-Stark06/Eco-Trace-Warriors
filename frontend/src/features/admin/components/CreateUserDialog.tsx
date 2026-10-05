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
import { Input } from '@/components/ui/input';
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
import { CREATABLE_USER_ROLES } from '@/types';
import type { CreatableUserRole, CreateUserResult } from '@/types';

/** Human-readable label for each creatable role, in dropdown order. */
const ROLE_LABELS: Record<CreatableUserRole, string> = {
  COLLECTOR: 'Collector',
  RECYCLER: 'Recycler',
  GOVERNMENT: 'Government',
};

interface CreateUserDialogProps {
  isPending: boolean;
  onCreate: (input: { email: string; role: CreatableUserRole }) => Promise<CreateUserResult>;
  /** Called with the backend result on success, after this dialog closes. */
  onCreated: (result: CreateUserResult) => void;
}

/**
 * ADMIN-only "Create User" dialog for operational accounts (COLLECTOR,
 * RECYCLER, GOVERNMENT). ADMIN and CONSUMER are never offered — the dropdown
 * only ever renders the three allowed roles, and the backend independently
 * re-validates and rejects anything else regardless of what this UI sends.
 *
 * The backend generates the password; this dialog never sees or handles a
 * password field itself. On success it hands the result (including the
 * one-time plaintext password) to the parent via `onCreated` and closes —
 * the parent is responsible for displaying it in `GeneratedPasswordDialog`.
 */
export function CreateUserDialog({ isPending, onCreate, onCreated }: CreateUserDialogProps) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<CreatableUserRole | ''>('');

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) {
      setEmail('');
      setRole('');
    }
  };

  const handleSubmit = async () => {
    if (!email.trim() || !role) return;
    try {
      const result = await onCreate({ email: email.trim(), role });
      handleOpenChange(false);
      onCreated(result);
    } catch (error) {
      toast.error(toApiError(error).message);
    }
  };

  const canSubmit = email.trim().length > 0 && role !== '';

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm">
          <icons.plus aria-hidden="true" />
          Create user
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create user</DialogTitle>
          <DialogDescription>
            Provision a Collector, Recycler, or Government account. A secure password is
            generated automatically and shown once you confirm.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="create-user-email">Email</Label>
            <Input
              id="create-user-email"
              type="email"
              placeholder="name@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="off"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="create-user-role">Role</Label>
            <Select value={role} onValueChange={(value) => setRole(value as CreatableUserRole)}>
              <SelectTrigger id="create-user-role">
                <SelectValue placeholder="Select a role" />
              </SelectTrigger>
              <SelectContent>
                {CREATABLE_USER_ROLES.map((value) => (
                  <SelectItem key={value} value={value}>
                    {ROLE_LABELS[value]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={isPending}>
            Cancel
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={isPending || !canSubmit}>
            {isPending && <icons.spinner className="animate-spin" aria-hidden="true" />}
            Create user
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
