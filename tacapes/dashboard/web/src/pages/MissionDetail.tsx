import { useParams } from 'react-router-dom';

import { AppShell } from '@/components/shell/AppShell';

// Placeholder. Real implementation lands in Phase 5 of the dashboard-redesign plan.
export function MissionDetailPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <AppShell>
      <h1 className="text-xl font-semibold">Mission {id}</h1>
      <p className="text-muted-foreground mt-2">Detail page lands in Phase 5.</p>
    </AppShell>
  );
}
