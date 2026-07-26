import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { ContentCard } from '@/components/dashboard/ContentCard';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { icons } from '@/lib/icons';
import { useAuth } from '@/hooks/use-auth';

/**
 * Settings (placeholder). Demonstrates the framework's form/tab primitives with
 * static, read-only content — no persistence, no business logic, no API calls.
 * Real settings management arrives in a later sprint. Default export for
 * React.lazy code-splitting.
 */
export default function SettingsPage() {
  const { user } = useAuth();
  const InfoIcon = icons.alert;

  return (
    <div className="flex flex-col gap-6">
      <DashboardHeader title="Settings" description="Manage your account and preferences." />

      <Alert>
        <InfoIcon aria-hidden="true" />
        <AlertTitle>Placeholder</AlertTitle>
        <AlertDescription>
          Settings management is not implemented yet. These fields are read-only previews of the
          shared framework.
        </AlertDescription>
      </Alert>

      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="preferences">Preferences</TabsTrigger>
        </TabsList>

        <TabsContent value="profile">
          <ContentCard title="Profile" description="Your account details.">
            <div className="grid gap-4 sm:max-w-md">
              <div className="grid gap-2">
                <Label htmlFor="settings-name">Full name</Label>
                <Input id="settings-name" value={user?.fullName ?? ''} readOnly disabled />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="settings-email">Email</Label>
                <Input id="settings-email" value={user?.email ?? ''} readOnly disabled />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="settings-role">Role</Label>
                <Input id="settings-role" value={user?.role ?? ''} readOnly disabled />
              </div>
            </div>
          </ContentCard>
        </TabsContent>

        <TabsContent value="preferences">
          <ContentCard title="Preferences" description="Appearance and notification options.">
            <p className="text-sm text-muted-foreground">
              Preference controls will appear here in a future sprint.
            </p>
          </ContentCard>
        </TabsContent>
      </Tabs>
    </div>
  );
}
