import { useCounts, useSystemHealth } from "../api/hooks";
import { Badge } from "../components/Badge";
import { JsonBlock } from "../components/JsonBlock";
import { StatusPanel } from "../components/cards/StatusPanel";
import { DataTable } from "../components/tables/DataTable";
import type { HealthCheck } from "../api/types";

const subsystemGroups = [
  { label: "Ingestion & detection", services: ["anomaly-detector-service", "feature-extractor-service"] },
  { label: "Knowledge & retrieval", services: ["retrieval-service", "knowledge-retrieval-service"] },
  { label: "Agent layer", services: ["agent-tool-gateway", "agent-orchestrator-service"] },
  { label: "Chaos", services: ["chaos-planner-service", "chaos-executor-service"] },
  { label: "Remediation", services: ["remediation-recommender-service", "approval-service", "remediation-executor-service"] },
];

const columns = [
  { key: "name", label: "Service" },
  { key: "ok", label: "Status", render: (row: HealthCheck) => <Badge tone={row.ok ? "good" : "bad"}>{row.ok ? "ok" : "degraded"}</Badge> },
  { key: "latencyMs", label: "Latency ms" },
  { key: "error", label: "Error" },
];

export function SystemPage() {
  const health = useSystemHealth();
  const counts = useCounts();
  const rows = health.data ?? [];

  return (
    <div className="page">
      <div className="page-heading"><div><h2>System Health</h2><p>Health checks through the command-center API proxy, plus exposed table and collection counts.</p></div></div>
      <StatusPanel title="Backend Service Status" loading={health.isLoading} error={health.error}>
        <div className="subsystem-group">
          {subsystemGroups.map((group) => (
            <section className="subsystem-group" key={group.label}>
              <div className="subsystem-label">{group.label}</div>
              <DataTable rows={rows.filter((row) => group.services.includes(row.name))} columns={columns} />
            </section>
          ))}
        </div>
      </StatusPanel>
      <StatusPanel title="Debug Counts" loading={counts.isLoading} error={counts.error}><JsonBlock value={counts.data} /></StatusPanel>
    </div>
  );
}
