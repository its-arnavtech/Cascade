import { useState } from "react";
import { useCounts, useSystemHealth } from "../api/hooks";
import { Badge } from "../components/Badge";
import { JsonBlock } from "../components/JsonBlock";
import { StatusPanel } from "../components/cards/StatusPanel";
import { StatCard } from "../components/cards/StatCard";
import { DataTable } from "../components/tables/DataTable";

export function SystemPage() {
  const health = useSystemHealth();
  const counts = useCounts();
  const [showRaw, setShowRaw] = useState(false);
  return (
    <div className="page">
      <div className="page-heading"><div><h2>System Health</h2><p>Health checks through the command-center API proxy, plus exposed table and collection counts.</p></div></div>
      <StatusPanel title="Backend Service Status" loading={health.isLoading} error={health.error}>
        <div className="service-groups">
          {serviceGroups.map((group) => {
            const rows = (health.data ?? []).filter((item) => group.services.includes(item.name));
            return (
              <section key={group.label}>
                <h3>{group.label}</h3>
                <DataTable caption={`${group.label} service health`} rows={rows} columns={[{ key: "name", label: "Service", width: "200px" }, { key: "ok", label: "Status", width: "90px", render: (row) => <Badge tone={row.ok ? "good" : "bad"}>{row.ok ? "ok" : "degraded"}</Badge> }, { key: "latencyMs", label: "Latency", width: "90px", render: (row) => row.latencyMs == null ? <span className="muted">-</span> : `${row.latencyMs} ms` }, { key: "error", label: "Error", render: (row) => <span className="muted">{String(row.error ?? "-")}</span> }]} />
              </section>
            );
          })}
        </div>
      </StatusPanel>
      <StatusPanel title="Debug Counts" loading={counts.isLoading} error={counts.error}>
        {showRaw ? <JsonBlock value={counts.data} /> : <div className="stats-grid compact">{Object.entries(counts.data ?? {}).map(([key, value]) => <StatCard key={key} label={key.replace(/_/g, " ")} value={value ?? "-"} />)}</div>}
        <button type="button" className="link-button" onClick={() => setShowRaw((value) => !value)}>{showRaw ? "Hide raw counts" : "View raw counts"}</button>
      </StatusPanel>
    </div>
  );
}

const serviceGroups = [
  { label: "Ingestion & storage", services: ["feature-extractor-service", "anomaly-detector-service"] },
  { label: "Knowledge & retrieval", services: ["retrieval-service", "knowledge-retrieval-service"] },
  { label: "Agent layer", services: ["agent-tool-gateway", "agent-orchestrator-service"] },
  { label: "Chaos", services: ["chaos-planner-service", "chaos-executor-service"] },
  { label: "Remediation", services: ["remediation-recommender-service", "approval-service", "remediation-executor-service"] },
];
