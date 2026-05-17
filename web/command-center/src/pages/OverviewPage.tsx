import { Link } from "react-router-dom";
import { AlertCircle, Beaker, BookOpen, CheckCircle, RefreshCw, ShieldCheck, Stethoscope } from "lucide-react";
import { useAnomalies, useChaosRuns, useCounts, useIncidents, useInvestigations, useRemediationPlans, useResilienceScores, useSystemHealth } from "../api/hooks";
import { Badge } from "../components/Badge";
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
  const degradedCount = health.data?.filter((item) => !item.ok).length ?? 0;
  const degraded = degradedCount > 0 || Boolean(counts.error);
  const checkedAt = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  function refreshAll() {
    void Promise.all([counts.refetch(), health.refetch(), anomalies.refetch(), incidents.refetch(), investigations.refetch(), runs.refetch(), scores.refetch(), remediation.refetch()]);
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <h2>Overview</h2>
          <p>Reliability triage across telemetry, incidents, investigations, chaos, and remediation.</p>
        </div>
        <button type="button" onClick={refreshAll}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>
      <div className={`hero-status ${degraded ? "degraded" : "online"}`}>
        <div>
          {degraded ? <AlertCircle size={18} /> : <CheckCircle size={18} />}
          <strong>{degraded ? `${degradedCount || 1} services degraded - check /system` : "All systems operational"}</strong>
        </div>
        <span>Last checked {checkedAt}</span>
      </div>
      <div className="stats-grid stats-group">
        <StatCard label="Telemetry Events" value={counts.data?.telemetry_events ?? "-"} />
        <StatCard label="Experiment Events" value={counts.data?.experiment_events ?? "-"} />
        <StatCard label="Anomalies" value={counts.data?.anomaly_events ?? "-"} tone={Number(counts.data?.anomaly_events ?? 0) > 0 ? "bad" : "default"} />
        <StatCard label="Incidents" value={counts.data?.incidents ?? "-"} tone={Number(counts.data?.incidents ?? 0) > 0 ? "bad" : "default"} />
      </div>
      <div className="stats-grid stats-group">
        <StatCard label="Knowledge Chunks" value={counts.data?.knowledge_chunks ?? "-"} />
        <StatCard label="Investigations" value={investigations.data?.count ?? "-"} />
        <StatCard label="Chaos Runs" value={runs.data?.count ?? "-"} detail={`${scores.data?.count ?? "-"} resilience scores`} tone="teal" />
        <StatCard label="Remediation Plans" value={remediation.data?.count ?? "-"} />
      </div>
      <section className="panel">
        <div className="section-title">Quick actions</div>
        <div className="quick-action-grid">
          <Link to="/knowledge"><BookOpen size={24} /><strong>Search knowledge</strong><span>Find source-grounded runbooks and evidence chunks.</span></Link>
          <Link to="/investigations"><Stethoscope size={24} /><strong>Start investigation</strong><span>Launch a deterministic read-only agent workflow.</span></Link>
          <Link to="/chaos"><Beaker size={24} /><strong>Create chaos plan</strong><span>Prepare a dry-run resilience experiment.</span></Link>
          <Link to="/remediation"><ShieldCheck size={24} /><strong>Create remediation plan</strong><span>Draft safe operator-reviewed next steps.</span></Link>
        </div>
      </section>
      <div className="grid two">
        <StatusPanel title="Recent Anomalies" loading={anomalies.isLoading} error={anomalies.error}>
          <DataTable
            caption="Recent anomalies"
            rows={anomalies.data?.anomalies ?? []}
            getRowClassName={(row) => row.severity === "critical" ? "row-critical" : ""}
            columns={[{ key: "service", label: "Service", width: "42%" }, { key: "severity", label: "Severity", width: "28%", render: (row) => <Badge tone={severityTone(row.severity)}>{String(row.severity ?? "-")}</Badge> }, { key: "risk_score", label: "Risk", width: "30%" }]}
          />
        </StatusPanel>
        <StatusPanel title="Recent Incidents" loading={incidents.isLoading} error={incidents.error}>
          <DataTable caption="Recent incidents" rows={incidents.data?.incidents ?? []} getRowClassName={(row) => row.severity === "critical" ? "row-critical" : ""} columns={[{ key: "title", label: "Title", width: "45%" }, { key: "service", label: "Service", width: "30%" }, { key: "severity", label: "Severity", width: "25%", render: (row) => <Badge tone={severityTone(row.severity)}>{String(row.severity ?? "-")}</Badge> }]} />
        </StatusPanel>
        <StatusPanel title="Recent Investigations" loading={investigations.isLoading} error={investigations.error}>
          <DataTable caption="Recent investigations" rows={investigations.data?.investigations ?? []} columns={[{ key: "status", label: "Status", width: "28%", render: (row) => <Badge tone={statusTone(row.status)}>{String(row.status ?? "-")}</Badge> }, { key: "service", label: "Service", width: "30%" }, { key: "final_summary", label: "Summary" }]} />
        </StatusPanel>
        <StatusPanel title="Recent Remediation Plans" loading={remediation.isLoading} error={remediation.error}>
          <DataTable caption="Recent remediation plans" rows={remediation.data?.plans ?? []} columns={[{ key: "service", label: "Service", width: "30%" }, { key: "action_type", label: "Action", width: "36%", render: (row) => <Badge tone="teal">{String(row.action_type ?? "-")}</Badge> }, { key: "status", label: "Status", render: (row) => <Badge tone={statusTone(row.status)}>{String(row.status ?? "-")}</Badge> }]} />
        </StatusPanel>
      </div>
    </div>
  );
}

function severityTone(value: unknown) {
  const severity = String(value ?? "").toLowerCase();
  if (severity.includes("critical") || severity.includes("high")) return "bad";
  if (severity.includes("warn") || severity.includes("medium")) return "warn";
  if (severity.includes("low") || severity.includes("ok")) return "good";
  return "neutral";
}

function statusTone(value: unknown) {
  const status = String(value ?? "").toLowerCase();
  if (status.includes("complete") || status.includes("approved") || status.includes("success")) return "good";
  if (status.includes("fail") || status.includes("reject") || status.includes("error")) return "bad";
  if (status.includes("run") || status.includes("pending") || status.includes("draft")) return "info";
  return "neutral";
}
