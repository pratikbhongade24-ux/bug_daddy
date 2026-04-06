import { DashboardLiveClient } from "@/components/dashboard-live-client";
import { emptyDashboardSummary, getDashboardSummary, getScenarios, getTriggers } from "@/lib/api";

export default async function OverviewPage() {
  const [summary, scenarios, triggers] = await Promise.all([
    getDashboardSummary().catch(() => emptyDashboardSummary()),
    getScenarios().catch(() => []),
    getTriggers().catch(() => []),
  ]);

  return <DashboardLiveClient initialSummary={summary} scenarios={scenarios} triggers={triggers} />;
}
