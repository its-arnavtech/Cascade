import { Link } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { useAnomalies, useChaosRuns, useCounts, useIncidents, useInvestigations, useRemediationPlans, useResilienceScores, useSystemHealth } from "../api/hooks";
import { StatCard } from "../components/cards/StatCard";
import { StatusPanel } from "../components/cards/StatusPanel";
import { DataTable } from "../components/tables/DataTable";

export function OverviewPage() {
  const counts = useCounts();
  const health = useSystemHealth();
  const anomalies = useAnomalies({ limit: 5 });
  const incidents = useIncidents({ limit: 5 });
  const investigations = useInvestigations({ limit: 5 });
  const runs = useChaosRuns({ limit: 5 });
  const scores = useResilienceScores({ limit: 5 });
  const remediation = useRemediationPlans({ limit: 5 });
  const degraded = health.data?.some((item) => !item.ok) || Boolean(counts.error);

  function refreshAll() {
    void Promise.all([counts.refetch(), health.refetch(), anomalies.refetch(), incidents.refetch(), investigations.refetch(), runs.refetch(), scores.refetch(), remediation.refetch()]);
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <h2>Overview Dashboard</h2>
          <p>Live counts and recent work from Cascade APIs.</p>
        </div>
        <button onClick={refreshAll}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>
      <div className={`hero-status ${degraded ? "degraded" : "online"}`}>
        <strong>{degraded ? "Degraded" : "System online"}</strong>
        <span>Last refreshed {new Date().toLocaleTimeString()}</span>
      </div>
      <div className="stats-grid">
        <StatCard label="Telemetry Events" value={counts.data?.telemetry_events ?? "-"} />
        <StatCard label="Experiment Events" value={counts.data?.experiment_events ?? "-"} />
        <StatCard label="Anomalies" value={counts.data?.anomaly_events ?? "-"} tone={Number(counts.data?.anomaly_events ?? 0) > 0 ? "warn" : "default"} />
        <StatCard label="Incidents" value={counts.data?.incidents ?? "-"} />
        <StatCard label="Knowledge Chunks" value={counts.data?.knowledge_chunks ?? "-"} />
        <StatCard label="Investigations" value={investigations.data?.count ?? "-"} />
        <StatCard label="Chaos Runs / Scores" value={`${runs.data?.count ?? "-"} / ${scores.data?.count ?? "-"}`} />
        <StatCard label="Remediation Plans" value={remediation.data?.count ?? "-"} />
      </div>
      <div className="quick-actions">
        <Link to="/knowledge">Search knowledge</Link>
        <Link to="/investigations">Start investigation</Link>
        <Link to="/chaos">Create chaos dry-run plan</Link>
        <Link to="/remediation">Create remediation plan</Link>
      </div>
      <div className="grid two">
        <StatusPanel title="Recent Anomalies" loading={anomalies.isLoading} error={anomalies.error}>
          <DataTable rows={anomalies.data?.anomalies ?? []} columns={[{ key: "service", label: "Service" }, { key: "severity", label: "Severity" }, { key: "risk_score", label: "Risk" }]} />
        </StatusPanel>
        <StatusPanel title="Recent Incidents" loading={incidents.isLoading} error={incidents.error}>
          <DataTable rows={incidents.data?.incidents ?? []} columns={[{ key: "title", label: "Title" }, { key: "service", label: "Service" }, { key: "severity", label: "Severity" }]} />
        </StatusPanel>
        <StatusPanel title="Recent Investigations" loading={investigations.isLoading} error={investigations.error}>
          <DataTable rows={investigations.data?.investigations ?? []} columns={[{ key: "status", label: "Status" }, { key: "service", label: "Service" }, { key: "final_summary", label: "Summary" }]} />
        </StatusPanel>
        <StatusPanel title="Recent Remediation Plans" loading={remediation.isLoading} error={remediation.error}>
          <DataTable rows={remediation.data?.plans ?? []} columns={[{ key: "service", label: "Service" }, { key: "action_type", label: "Action" }, { key: "status", label: "Status" }]} />
        </StatusPanel>
      </div>
    </div>
  );
}
