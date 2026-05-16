import { useCounts, useSystemHealth } from "../api/hooks";
import { Badge } from "../components/Badge";
import { JsonBlock } from "../components/JsonBlock";
import { StatusPanel } from "../components/cards/StatusPanel";
import { DataTable } from "../components/tables/DataTable";

export function SystemPage() {
  const health = useSystemHealth();
  const counts = useCounts();
  return (
    <div className="page">
      <div className="page-heading"><div><h2>System Health</h2><p>Health checks through the command-center API proxy, plus exposed table and collection counts.</p></div></div>
      <StatusPanel title="Backend Service Status" loading={health.isLoading} error={health.error}>
        <DataTable rows={health.data ?? []} columns={[{ key: "name", label: "Service" }, { key: "ok", label: "Status", render: (row) => <Badge tone={row.ok ? "good" : "bad"}>{row.ok ? "ok" : "degraded"}</Badge> }, { key: "latencyMs", label: "Latency ms" }, { key: "error", label: "Error" }]} />
      </StatusPanel>
      <StatusPanel title="Debug Counts" loading={counts.isLoading} error={counts.error}><JsonBlock value={counts.data} /></StatusPanel>
    </div>
  );
}
