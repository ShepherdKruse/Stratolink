import MissionControlScreen from '@/components/dashboard-v2/MissionControl';

/**
 * Dashboard v2 — opt-in preview of the redesigned ground-station UI.
 * Lives alongside the production dashboard at /dashboard so we can A/B
 * compare. Wired to the same Supabase tables, so any uplinks Teddy sends
 * show up in both surfaces simultaneously.
 */
export default function DashboardV2Page() {
    return <MissionControlScreen />;
}
