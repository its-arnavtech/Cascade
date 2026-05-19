import { Link } from "react-router-dom";
import type { CSSProperties } from "react";
import { AlertTriangle, BarChart3, Database, Layers3, Search, ShieldCheck, Sparkles } from "lucide-react";
import { useAnomalies, useApprovals, useCounts, useExecutions, useExperiments, useFeatureWindows, useIncidents, useInvestigations, useKnowledgeStats, useLiveDemoStatus, useRemediationPlans, useResilienceScores, useSystemHealth, useTelemetry, useTopologyGraph } from "../api/hooks";
import { Badge } from "../components/Badge";
import { TargetWorkloadPanel, TopologyGraphView } from "../components/IntelligencePanels";
import { StatCard } from "../components/cards/StatCard";
import { StatusPanel } from "../components/cards/StatusPanel";
import { DataTable } from "../components/tables/DataTable";

export function OverviewPage() {
  const counts = useCounts();
  const health = useSystemHealth();
  const telemetry = useTelemetry({ limit: 120 });
  const features = useFeatureWindows({ limit: 12 });
  const anomalies = useAnomalies({ limit: 60 });
  const experiments = useExperiments({ limit: 60 });
  const incidents = useIncidents({ limit: 6 });
  const investigations = useInvestigations({ limit: 4 });
  const scores = useResilienceScores({ limit: 8 });
  const remediation = useRemediationPlans({ limit: 5 });
  const approvals = useApprovals({ limit: 5 });
  const executions = useExecutions({ limit: 5 });
  const liveStatus = useLiveDemoStatus();
  const knowledgeStats = useKnowledgeStats();
  const topology = useTopologyGraph();
  const degradedCount = health.data?.filter((item) => !item.ok).length ?? 0;
  const safetyScore = health.data?.length ? Math.round(((health.data.length - degradedCount) / health.data.length) * 100) : undefined;
  const latestIncident = incidents.data?.incidents?.[0];
  const latestAnomaly = anomalies.data?.anomalies?.[0];

  return (
    <div className="page overview-page">
      <div className="metric-grid">
        <StatCard icon={BarChart3} tone="info" label="Telemetry Events" value={formatNumber(counts.data?.telemetry_events)} detail={counts.isFetching ? "Refreshing from API" : "From retrieval counts"} trend="up" />
        <StatCard icon={AlertTriangle} tone={Number(counts.data?.anomaly_events ?? 0) > 0 ? "warn" : "good"} label="Active Anomalies" value={formatNumber(counts.data?.anomaly_events)} detail={`${anomalies.data?.count ?? 0} recent signals`} trend={Number(counts.data?.anomaly_events ?? 0) > 0 ? "up" : undefined} />
        <StatCard icon={Database} tone="violet" label="Knowledge Chunks" value={formatNumber(counts.data?.knowledge_chunks ?? knowledgeStats.data?.knowledge_chunks ?? knowledgeStats.data?.chunks)} detail="Indexed evidence corpus" trend="up" />
        <StatCard icon={ShieldCheck} tone="good" label="Safety Gates" value={safetyScore == null ? "-" : `${safetyScore}%`} detail={degradedCount ? `${degradedCount} checks degraded` : "Execution locked by policy"} trend={degradedCount ? "down" : "up"} />
      </div>

      <div className="overview-grid">
        <StatusPanel title="Platform Signal & Risk Trends" loading={telemetry.isLoading || features.isLoading || anomalies.isLoading || scores.isLoading || experiments.isLoading} error={telemetry.error ?? features.error ?? anomalies.error ?? scores.error ?? experiments.error}>
          <SignalTrends
            telemetry={telemetry.data?.events ?? []}
            features={features.data?.features ?? []}
            anomalies={anomalies.data?.anomalies ?? []}
            scores={scores.data?.scores ?? []}
            experiments={experiments.data?.experiments ?? []}
          />
        </StatusPanel>
        <StatusPanel title="Priority Incidents" loading={incidents.isLoading} error={incidents.error}>
          <DataTable
            caption="Priority incidents"
            rows={incidents.data?.incidents ?? []}
            empty="No data returned."
            columns={[
              { key: "title", label: "Incident", width: "34%", render: (row) => <strong>{String(row.title ?? row.incident_id ?? "-")}</strong> },
              { key: "service", label: "Service", width: "22%" },
              { key: "severity", label: "Severity", width: "16%", render: (row) => <Badge tone={severityTone(row.severity)}>{String(row.severity ?? "-")}</Badge> },
              { key: "started_at", label: "Detected", width: "16%", render: (row) => shortTime(row.started_at) },
              { key: "status", label: "Status", width: "12%", render: (row) => <Badge tone={statusTone(row.status)}>{String(row.status ?? "open")}</Badge> },
            ]}
          />
        </StatusPanel>
      </div>

      <div className="overview-lower">
        <TargetWorkloadPanel />

        <RemediationWorkflowPanel plans={remediation.data?.plans ?? []} approvals={approvals.data?.approvals ?? []} executions={executions.data?.executions ?? []} liveReady={isRemediationLiveReady(liveStatus.data)} />

        <div className="side-stack">
          <StatusPanel title="Topology Graph" loading={topology.isLoading} error={topology.error}>
            <TopologyGraphView value={topology.data} />
          </StatusPanel>
          <section className="panel knowledge-panel">
            <div className="panel-heading"><h2>Knowledge Search</h2></div>
            <Link className="searchbox-link" to="/knowledge">
              <Search size={18} />
              <span>Search knowledge chunks, runbooks, incidents...</span>
            </Link>
          </section>
          <section className="panel next-step-panel">
            <div className="panel-heading"><h2>Recommended Next Step</h2></div>
            <div className="next-step">
              <span className="next-step-icon"><Sparkles size={18} /></span>
              <div className="next-step-copy">
                <strong>{recommendedTitle(latestIncident, latestAnomaly).title}{recommendedTitle(latestIncident, latestAnomaly).service ? <code>{recommendedTitle(latestIncident, latestAnomaly).service}</code> : null}</strong>
                <p>{investigations.data?.count ? `${investigations.data.count} investigation records available for comparison.` : `${remediation.data?.count ?? 0} remediation plans available for review.`}</p>
              </div>
              <Link className="outline-action" to="/investigations">Start Investigation</Link>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function RemediationWorkflowPanel({ plans, approvals, executions, liveReady }: { plans: Record<string, unknown>[]; approvals: Record<string, unknown>[]; executions: Record<string, unknown>[]; liveReady: boolean }) {
  const latestPlan = plans[0];
  const latestApproval = approvals[0];
  const latestExecution = executions[0];
  const hasActivity = Boolean(latestPlan || latestApproval || latestExecution);
  const steps = [
    { label: "Generate Plan", state: latestPlan ? "done" : "ready" },
    { label: "Validate Dry Run", state: latestExecution?.dry_run || latestExecution?.validation_status ? "done" : hasActivity ? "ready" : "pending" },
    { label: "Approval Required", state: latestApproval ? "done" : "pending" },
    { label: liveReady ? "Live Gate Ready" : "Real Execution Disabled", state: liveReady ? "ready" : "disabled" },
    { label: "Bounded Local Execution", state: liveReady && latestExecution?.executed ? "done" : "pending" },
  ];
  return (
    <section className="panel workflow-panel">
      <div className="panel-heading"><h2>Remediation Workflow</h2><Badge tone={liveReady ? "bad" : "dry"}>{liveReady ? "Live demo mode" : "Dry-run mode"}</Badge></div>
      <div className="workflow-track">
        {steps.map((step, index) => (
          <div className={`workflow-step ${step.state}`} key={step.label}>
            <span>{step.state === "done" ? "ok" : index + 1}</span>
            <strong>{step.label}</strong>
          </div>
        ))}
      </div>
      {hasActivity ? (
        <div className="workflow-details">
          <WorkflowFact label="Latest plan" value={latestPlan?.plan_id ?? latestPlan?.id ?? "No plan returned"} />
          <WorkflowFact label="Approval" value={latestApproval?.decision ?? latestApproval?.status ?? "No approval returned"} />
          <WorkflowFact label="Dry-run" value={latestExecution?.validation_status ?? latestExecution?.status ?? "No execution returned"} />
          <WorkflowFact label="Rollback" value={latestPlan?.rollback_steps ? "Available" : latestExecution?.rollback_available ? "Available" : "Not returned"} />
          <WorkflowFact label="Post-checks" value={latestPlan?.post_checks ? "Defined" : "Not returned"} />
        </div>
      ) : (
        <div className="state state-compact"><strong>No remediation activity yet</strong><span>Create a plan, record approval, then run dry-run validation. Real execution stays locked unless Live Demo Mode is explicitly enabled.</span></div>
      )}
      <div className="workflow-note">
        <span>{liveReady ? "Backend policy reports bounded local restart controls are available." : "Real execution is disabled. Dry-run validation is available now; use Live Demo Mode only on local kind."}</span>
        <Link className="outline-action" to="/remediation">Open Workflow</Link>
      </div>
    </section>
  );
}

function WorkflowFact({ label, value }: { label: string; value: unknown }) {
  return <div><span>{label}</span><strong className="identifier">{String(value ?? "-")}</strong></div>;
}

function SignalTrends({ telemetry, features, anomalies, scores, experiments }: { telemetry: Record<string, unknown>[]; features: Record<string, unknown>[]; anomalies: Record<string, unknown>[]; scores: Record<string, unknown>[]; experiments: Record<string, unknown>[] }) {
  const volume = bucketCounts(telemetry, "timestamp");
  const anomalyCounts = bucketCounts(anomalies, "detected_at");
  const anomalyScores = bucketAverage(anomalies, "detected_at", "risk_score");
  const latency = bucketAverage(features, "window_start", "latency_p95_ms");
  const errors = bucketSum(features, "window_start", "error_count");
  const eventCounts = bucketSum(features, "window_start", "event_count");
  const experimentCounts = bucketCounts(experiments, "timestamp", "started_at");
  const resilience = bucketAverage(scores, "computed_at", "resilience_score");
  const hasData = [volume, anomalyCounts, anomalyScores, latency, errors, eventCounts, experimentCounts, resilience].some((series) => series.length > 0);
  if (!hasData) return <div className="state">No recent telemetry or anomaly points found yet. Generate traffic or run a dry-run/live demo, then refresh.</div>;
  return (
    <div className="signal-panel">
      <div className="trend-grid">
        <LineChart title="Telemetry volume" empty="No telemetry events returned." series={[{ label: "events", points: volume.length ? volume : eventCounts, color: "#60a5fa" }]} />
        <LineChart title="Anomaly trend" empty="No anomalies returned." series={[{ label: "count", points: anomalyCounts, color: "#f59e0b" }, { label: "score", points: anomalyScores, color: "#fb7185", scale: 100 }]} />
        <LineChart title="Latency and errors" empty="No feature windows returned." series={[{ label: "latency p95", points: latency, color: "#22d3ee" }, { label: "errors", points: errors, color: "#f97316" }]} />
        <LineChart title="Chaos and resilience" empty="No chaos/remediation event trend returned." series={[{ label: "events", points: experimentCounts, color: "#a78bfa" }, { label: "score", points: resilience, color: "#4ade80", scale: 100 }]} />
      </div>
      <p><Layers3 size={15} /> Lines are aggregated from live retrieval telemetry, feature, anomaly, experiment, and score APIs.</p>
    </div>
  );
}

type ChartPoint = { bucket: string; value: number };
type ChartSeries = { label: string; points: ChartPoint[]; color: string; scale?: number };

function LineChart({ title, series, empty }: { title: string; series: ChartSeries[]; empty: string }) {
  const active = series.filter((item) => item.points.length);
  if (!active.length) return <div className="line-card"><strong>{title}</strong><div className="state">{empty}</div></div>;
  const buckets = [...new Set(active.flatMap((item) => item.points.map((point) => point.bucket)))].sort();
  const values = active.flatMap((item) => item.points.map((point) => point.value * (item.scale ?? 1)));
  const max = Math.max(1, ...values);
  const width = 320;
  const height = 126;
  const padding = 14;
  return (
    <div className="line-card">
      <div className="line-card-head"><strong>{title}</strong><span>{buckets.length} points</span></div>
      <svg className="line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
        <path className="gridline" d={`M ${padding} ${height - padding} H ${width - padding}`} />
        <path className="gridline" d={`M ${padding} ${height / 2} H ${width - padding}`} />
        {active.map((item) => {
          const map = new Map(item.points.map((point) => [point.bucket, point.value * (item.scale ?? 1)]));
          const d = buckets.map((bucket, index) => {
            const x = padding + (buckets.length === 1 ? 0 : index * ((width - padding * 2) / (buckets.length - 1)));
            const y = height - padding - ((map.get(bucket) ?? 0) / max) * (height - padding * 2);
            return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
          }).join(" ");
          return <path key={item.label} d={d} fill="none" stroke={item.color} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />;
        })}
      </svg>
      <div className="line-legend">{active.map((item) => <span key={item.label} style={{ "--series-color": item.color } as CSSProperties}>{item.label}</span>)}</div>
    </div>
  );
}

function bucketCounts(rows: Record<string, unknown>[], ...timeKeys: string[]): ChartPoint[] {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const bucket = timeBucket(row, timeKeys);
    if (bucket) counts.set(bucket, (counts.get(bucket) ?? 0) + 1);
  }
  return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(-12).map(([bucket, value]) => ({ bucket, value }));
}

function bucketSum(rows: Record<string, unknown>[], timeKey: string, valueKey: string): ChartPoint[] {
  const sums = new Map<string, number>();
  for (const row of rows) {
    const bucket = timeBucket(row, [timeKey]);
    const value = Number(row[valueKey]);
    if (bucket && Number.isFinite(value)) sums.set(bucket, (sums.get(bucket) ?? 0) + value);
  }
  return [...sums.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(-12).map(([bucket, value]) => ({ bucket, value }));
}

function bucketAverage(rows: Record<string, unknown>[], timeKey: string, valueKey: string): ChartPoint[] {
  const sums = new Map<string, { total: number; count: number }>();
  for (const row of rows) {
    const bucket = timeBucket(row, [timeKey]);
    const value = Number(row[valueKey]);
    if (bucket && Number.isFinite(value)) {
      const current = sums.get(bucket) ?? { total: 0, count: 0 };
      sums.set(bucket, { total: current.total + value, count: current.count + 1 });
    }
  }
  return [...sums.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(-12).map(([bucket, item]) => ({ bucket, value: item.total / item.count }));
}

function timeBucket(row: Record<string, unknown>, keys: string[]) {
  const value = keys.map((key) => row[key]).find(Boolean);
  if (!value) return undefined;
  const date = new Date(String(value).replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return undefined;
  date.setSeconds(0, 0);
  return date.toISOString();
}

function formatNumber(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return new Intl.NumberFormat("en-US", { notation: number >= 1_000_000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(number);
}

function clamp(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, value));
}

function severityTone(value: unknown): "good" | "warn" | "bad" | "neutral" {
  const severity = String(value ?? "").toLowerCase();
  if (severity.includes("critical") || severity.includes("high")) return "bad";
  if (severity.includes("warn") || severity.includes("medium")) return "warn";
  if (severity.includes("low")) return "good";
  return "neutral";
}

function statusTone(value: unknown): "good" | "warn" | "bad" | "info" | "neutral" {
  const status = String(value ?? "").toLowerCase();
  if (status.includes("resolved") || status.includes("closed") || status.includes("monitor")) return "good";
  if (status.includes("fail") || status.includes("error")) return "bad";
  if (status.includes("open") || status.includes("active") || status.includes("identified")) return "warn";
  if (status.includes("investigat") || status.includes("pending")) return "info";
  return "neutral";
}

function shortTime(value: unknown) {
  if (!value) return "-";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function recommendedTitle(incident?: Record<string, unknown>, anomaly?: Record<string, unknown>) {
  if (incident?.title) return { title: `Investigate ${String(incident.title).toLowerCase()}` };
  if (anomaly?.service) return { title: "Investigate elevated signal in ", service: String(anomaly.service) };
  return { title: "Review current reliability signals" };
}

function isRemediationLiveReady(value: Record<string, unknown> | undefined) {
  const command = value?.command_center as Record<string, unknown> | undefined;
  const remediation = value?.remediation as Record<string, unknown> | undefined;
  return Boolean(command?.dangerous_actions_enabled && remediation?.dangerous_actions_enabled && remediation?.real_remediation_enabled && remediation?.execution_enabled && remediation?.live_demo_mode && remediation?.allowed_target_namespace === "cascade-targets");
}
