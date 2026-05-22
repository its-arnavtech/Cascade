import { Link } from "react-router-dom";
import type { CSSProperties, ReactNode } from "react";
import { AlertTriangle, BarChart3, Bot, Database, GitBranch, Layers3, Search, ShieldCheck, Sparkles, Zap } from "lucide-react";
import { useAnomalies, useApprovals, useAutopilotRuns, useChaosPlans, useChaosRuns, useCounts, useExecutions, useExperiments, useFeatureWindows, useIncidents, useInvestigations, useKnowledgeStats, useLiveDemoStatus, useRcaReports, useRemediationPlans, useRemediationRollbackPlans, useRemediationVerifications, useResilienceScores, useSystemHealth, useTelemetry, useTopologyGraph } from "../api/hooks";
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
  const rca = useRcaReports({ limit: 5 });
  const autopilot = useAutopilotRuns({ limit: 5 });
  const scores = useResilienceScores({ limit: 8 });
  const chaosPlans = useChaosPlans({ limit: 5 });
  const chaosRuns = useChaosRuns({ limit: 5 });
  const remediation = useRemediationPlans({ limit: 5 });
  const approvals = useApprovals({ limit: 5 });
  const executions = useExecutions({ limit: 5 });
  const verifications = useRemediationVerifications({ limit: 5 });
  const rollbacks = useRemediationRollbackPlans({ limit: 5 });
  const liveStatus = useLiveDemoStatus();
  const knowledgeStats = useKnowledgeStats();
  const topology = useTopologyGraph();
  const degradedCount = health.data?.filter((item) => !item.ok).length ?? 0;
  const safetyScore = health.data?.length ? Math.round(((health.data.length - degradedCount) / health.data.length) * 100) : undefined;
  const latestIncident = incidents.data?.incidents?.[0];
  const latestAnomaly = anomalies.data?.anomalies?.[0];
  const latestRca = rca.data?.reports?.[0];

  return (
    <div className="page overview-page">
      <DemoModePanel liveStatus={liveStatus.data} />
      <div className="metric-grid">
        <StatCard icon={BarChart3} tone="info" label="Telemetry Events" value={formatNumber(counts.data?.telemetry_events)} detail={counts.isFetching ? "Refreshing from API" : "From retrieval counts"} trend="up" />
        <StatCard icon={AlertTriangle} tone={Number(counts.data?.anomaly_events ?? 0) > 0 ? "warn" : "good"} label="Active Anomalies" value={formatNumber(counts.data?.anomaly_events)} detail={`${anomalies.data?.count ?? 0} recent signals`} trend={Number(counts.data?.anomaly_events ?? 0) > 0 ? "up" : undefined} />
        <StatCard icon={Database} tone="violet" label="Knowledge Chunks" value={formatNumber(counts.data?.knowledge_chunks ?? knowledgeStats.data?.knowledge_chunks ?? knowledgeStats.data?.chunks)} detail="Indexed evidence corpus" trend="up" />
        <StatCard icon={ShieldCheck} tone="good" label="Safety Gates" value={safetyScore == null ? "-" : `${safetyScore}%`} detail={degradedCount ? `${degradedCount} checks degraded` : "Execution locked by policy"} trend={degradedCount ? "down" : "up"} />
      </div>

      <div className="work-status-grid">
        <StatusPanel title="Active Anomalies" loading={anomalies.isLoading} error={anomalies.error}>
          <DataTable
            caption="Active anomalies"
            rows={anomalies.data?.anomalies ?? []}
            empty="No active anomaly records returned."
            columns={[
              { key: "detected_at", label: "Detected", width: "130px", render: (row) => shortTime(row.detected_at) },
              { key: "service", label: "Service", width: "140px", render: (row) => <code className="inline-code">{String(row.service ?? "-")}</code> },
              { key: "severity", label: "Severity", width: "100px", render: (row) => <Badge tone={severityTone(row.severity)}>{String(row.severity ?? "-")}</Badge> },
              { key: "risk_score", label: "Risk", width: "80px", render: (row) => formatScore(row.risk_score) },
              { key: "explanation", label: "Evidence" },
            ]}
          />
        </StatusPanel>
        <StatusPanel title="Recent RCA" loading={rca.isLoading} error={rca.error}>
          <EvidenceSummary
            icon={<GitBranch size={18} />}
            title={String(latestRca?.likely_root_cause_service ?? "No root cause asserted")}
            subtitle={String(latestRca?.explanation ?? "No RCA evidence bundle returned. Run RCA after telemetry and topology are available.")}
            badge={<Badge tone={rcaTone(latestRca?.status)}>{String(latestRca?.status ?? "insufficient evidence").replace(/_/g, " ")}</Badge>}
            facts={[
              ["Target", latestRca?.target_service],
              ["Confidence", formatScore(latestRca?.confidence_score)],
              ["Affected", arrayLength(latestRca?.affected_downstream_services) ? `${arrayLength(latestRca?.affected_downstream_services)} services` : "No affected services returned"],
            ]}
            to="/causality"
          />
        </StatusPanel>
        <StatusPanel title="Autopilot Runs" loading={autopilot.isLoading} error={autopilot.error}>
          <RunStatusPanel runs={autopilot.data?.runs ?? []} />
        </StatusPanel>
      </div>

      <div className="work-status-grid">
        <StatusPanel title="Remediation Status" loading={remediation.isLoading || approvals.isLoading || executions.isLoading} error={remediation.error ?? approvals.error ?? executions.error}>
          <RemediationStatus plans={remediation.data?.plans ?? []} approvals={approvals.data?.approvals ?? []} executions={executions.data?.executions ?? []} />
        </StatusPanel>
        <StatusPanel title="Verification / Rollback" loading={verifications.isLoading || rollbacks.isLoading} error={verifications.error ?? rollbacks.error}>
          <VerificationStatus verifications={verifications.data?.verifications ?? []} rollbacks={rollbacks.data?.rollback_plans ?? []} />
        </StatusPanel>
        <StatusPanel title="Chaos Experiments" loading={chaosPlans.isLoading || chaosRuns.isLoading || experiments.isLoading} error={chaosPlans.error ?? chaosRuns.error ?? experiments.error}>
          <ChaosStatus plans={chaosPlans.data?.plans ?? []} runs={chaosRuns.data?.runs ?? []} experiments={experiments.data?.experiments ?? []} />
        </StatusPanel>
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
                <strong>{recommendedTitle(latestIncident, latestAnomaly, latestRca).title}{recommendedTitle(latestIncident, latestAnomaly, latestRca).service ? <code>{recommendedTitle(latestIncident, latestAnomaly, latestRca).service}</code> : null}</strong>
                <p>{latestRca?.explanation ? String(latestRca.explanation) : investigations.data?.count ? `${investigations.data.count} investigation records available for comparison.` : `${remediation.data?.count ?? 0} remediation plans available for review.`}</p>
              </div>
              <Link className="outline-action" to="/investigations">Start Investigation</Link>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function DemoModePanel({ liveStatus }: { liveStatus?: Record<string, unknown> }) {
  const command = liveStatus?.command_center as Record<string, unknown> | undefined;
  const chaos = liveStatus?.chaos as Record<string, unknown> | undefined;
  const remediation = liveStatus?.remediation as Record<string, unknown> | undefined;
  const localDemo = Boolean(command?.dangerous_actions_enabled || chaos?.live_demo_mode || remediation?.live_demo_mode);
  return (
    <section className="panel demo-helper">
      <div>
        <div className="status-chip-row">
          <Badge tone="good">read-only</Badge>
          <Badge tone="dry">dry-run</Badge>
          <Badge tone={localDemo ? "bad" : "neutral"}>{localDemo ? "local-demo" : "production-safe"}</Badge>
          <Badge tone="info">live data</Badge>
        </div>
        <h2>Cascade Demo Cockpit</h2>
        <p>Start with validation, generate telemetry, then run dry-run chaos, remediation, and Autopilot. Real actions stay disabled unless local demo mode is explicitly enabled.</p>
      </div>
      <div className="demo-command-list" aria-label="Safe demo commands">
        <code>.\scripts\demo-command-center.ps1 -Stage Validate</code>
        <code>.\scripts\demo-command-center.ps1 -Stage Telemetry</code>
        <code>.\scripts\demo-command-center.ps1 -Stage Autopilot</code>
      </div>
      <Link className="outline-action" to="/system">Check System</Link>
    </section>
  );
}

function EvidenceSummary({ icon, title, subtitle, badge, facts, to }: { icon: ReactNode; title: string; subtitle: string; badge: ReactNode; facts: Array<[string, unknown]>; to: string }) {
  return (
    <div className="demo-summary-card">
      <div className="intel-summary">
        <span className="intel-icon">{icon}</span>
        <div>
          <strong>{title}</strong>
          <span>{subtitle}</span>
        </div>
        {badge}
      </div>
      <div className="demo-facts">
        {facts.map(([label, value]) => <div key={label}><span>{label}</span><strong>{String(value ?? "No data returned.")}</strong></div>)}
      </div>
      <Link className="outline-action" to={to}>Open Evidence</Link>
    </div>
  );
}

function RunStatusPanel({ runs }: { runs: Record<string, unknown>[] }) {
  const latest = runs[0];
  if (!latest) return <div className="state state-compact"><strong>No Autopilot runs yet</strong><span>Run a dry-run Autopilot loop from the Autopilot page or demo script.</span></div>;
  const states = autopilotStates(latest);
  return (
    <div className="demo-summary-card">
      <div className="intel-summary">
        <span className="intel-icon"><Bot size={18} /></span>
        <div>
          <strong>{String(latest.final_result || latest.status || "Run recorded")}</strong>
          <span>{String(latest.service || "manual")} in {String(latest.mode || "dry_run")} mode</span>
        </div>
        <Badge tone={statusTone(latest.final_result ?? latest.status)}>{String(latest.final_result || latest.status || "unknown")}</Badge>
      </div>
      <div className="autopilot-state-strip">
        {states.map((item) => <span className={item.done ? "done" : item.blocked ? "blocked" : ""} key={item.label}>{item.label}</span>)}
      </div>
      <Link className="outline-action" to="/autopilot">Open Autopilot</Link>
    </div>
  );
}

function RemediationStatus({ plans, approvals, executions }: { plans: Record<string, unknown>[]; approvals: Record<string, unknown>[]; executions: Record<string, unknown>[] }) {
  const latestPlan = plans[0];
  const latestApproval = approvals[0];
  const latestExecution = executions[0];
  return (
    <EvidenceSummary
      icon={<ShieldCheck size={18} />}
      title={String(latestPlan?.action_summary ?? latestPlan?.action_type ?? "No remediation plan returned")}
      subtitle={latestExecution ? String(latestExecution.output_summary ?? latestExecution.validation_status ?? "Execution record returned") : "Plan, approval, and dry-run status appear here."}
      badge={<Badge tone={policyTone(policyDecision(latestPlan ?? {}).status ?? latestExecution?.validation_status)}>{String(policyDecision(latestPlan ?? {}).status ?? latestExecution?.validation_status ?? "dry-run ready").replace(/_/g, " ")}</Badge>}
      facts={[
        ["Plan", latestPlan?.plan_id ?? "none"],
        ["Approval", latestApproval?.decision ?? "none"],
        ["Dry-run", latestExecution?.dry_run === true ? "completed" : "not run"],
      ]}
      to="/remediation"
    />
  );
}

function VerificationStatus({ verifications, rollbacks }: { verifications: Record<string, unknown>[]; rollbacks: Record<string, unknown>[] }) {
  const latestVerification = verifications[0];
  const latestRollback = rollbacks[0];
  return (
    <EvidenceSummary
      icon={<ShieldCheck size={18} />}
      title={String(latestVerification?.status ?? "No verification result returned")}
      subtitle={String(latestVerification?.summary ?? latestRollback?.reason ?? "Verification and rollback records appear after remediation dry-runs or executions.")}
      badge={<Badge tone={verificationTone(latestVerification?.status ?? latestRollback?.status)}>{String(latestVerification?.status ?? latestRollback?.status ?? "insufficient evidence").replace(/_/g, " ")}</Badge>}
      facts={[
        ["Evidence", latestVerification?.evidence_quality ?? "none"],
        ["Rollback", latestRollback?.available === true ? "available" : latestRollback?.available === false ? "unavailable" : "not returned"],
        ["Auto", latestRollback?.auto_executable === true ? "yes" : "no"],
      ]}
      to="/remediation"
    />
  );
}

function ChaosStatus({ plans, runs, experiments }: { plans: Record<string, unknown>[]; runs: Record<string, unknown>[]; experiments: Record<string, unknown>[] }) {
  const latestPlan = plans[0];
  const latestRun = runs[0];
  const latestExperiment = experiments[0];
  return (
    <EvidenceSummary
      icon={<Zap size={18} />}
      title={String(latestRun?.status ?? latestPlan?.status ?? "No chaos run returned")}
      subtitle={String(latestPlan?.objective ?? latestExperiment?.event_type ?? "Dry-run chaos plans and bounded local demo runs appear here.")}
      badge={<Badge tone={latestRun?.dry_run === true ? "dry" : statusTone(latestRun?.status ?? latestPlan?.status)}>{latestRun?.dry_run === true ? "dry-run" : String(latestRun?.status ?? "planned")}</Badge>}
      facts={[
        ["Plan", latestPlan?.plan_id ?? "none"],
        ["Run", latestRun?.run_id ?? "none"],
        ["Cleanup", latestRun?.cleanup_status ?? "not run"],
      ]}
      to="/chaos"
    />
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

function formatScore(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number <= 1 ? `${Math.round(number * 100)}%` : String(Math.round(number));
}

function arrayLength(value: unknown) {
  return Array.isArray(value) ? value.length : 0;
}

function rcaTone(value: unknown): "good" | "warn" | "bad" | "teal" | "info" | "neutral" | "dry" {
  const status = String(value ?? "").toLowerCase();
  if (status === "ranked") return "teal";
  if (status.includes("insufficient")) return "warn";
  if (status.includes("low")) return "info";
  return "neutral";
}

function policyDecision(row: Record<string, unknown>) {
  const direct = row.policy_decision;
  const nested = (row.plan && typeof row.plan === "object" && !Array.isArray(row.plan) ? row.plan as Record<string, unknown> : {}).policy_decision;
  return (direct && typeof direct === "object" && !Array.isArray(direct) ? direct : nested && typeof nested === "object" && !Array.isArray(nested) ? nested : {}) as Record<string, unknown>;
}

function policyTone(value: unknown): "good" | "warn" | "bad" | "info" | "neutral" | "dry" {
  const status = String(value ?? "").toLowerCase();
  if (status === "blocked") return "bad";
  if (status === "requires_approval") return "warn";
  if (status === "dry_run_only") return "dry";
  if (status === "allowed_automatic") return "good";
  if (status === "allowed") return "info";
  return "neutral";
}

function verificationTone(value: unknown): "good" | "warn" | "bad" | "info" | "neutral" {
  const status = String(value ?? "").toLowerCase();
  if (status === "fixed" || status === "improved" || status === "rolled_back" || status.includes("valid")) return "good";
  if (status === "unchanged" || status === "insufficient_evidence" || status.includes("missing")) return "warn";
  if (status === "degraded" || status === "failed" || status.includes("error")) return "bad";
  if (status.includes("pending") || status.includes("dry")) return "info";
  return "neutral";
}

function autopilotStates(run: Record<string, unknown>) {
  const evidence = run.evidence && typeof run.evidence === "object" ? run.evidence as Record<string, unknown> : {};
  const recommendation = run.recommendation && typeof run.recommendation === "object" ? run.recommendation as Record<string, unknown> : {};
  const action = run.action && typeof run.action === "object" ? run.action as Record<string, unknown> : {};
  const verification = run.verification && typeof run.verification === "object" ? run.verification as Record<string, unknown> : {};
  const final = String(run.final_result ?? run.status ?? "").toLowerCase();
  return [
    { label: "investigated", done: Boolean(run.investigation_id || evidence.summary || run.evidence) },
    { label: "planned", done: Boolean(run.remediation_plan_id || recommendation.plan_id || run.recommendation) },
    { label: "policy checked", done: Boolean(recommendation.policy_decision || action.policy_decision || run.action) },
    { label: "dry-run", done: Boolean(run.dry_run_execution_id || action.dry_run_validation) },
    { label: final.includes("blocked") ? "blocked" : "executed", done: Boolean(run.execution_id), blocked: final.includes("blocked") || action.executed === false },
    { label: "verified", done: Boolean(verification.status || run.verification) },
  ];
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

function recommendedTitle(incident?: Record<string, unknown>, anomaly?: Record<string, unknown>, rca?: Record<string, unknown>) {
  if (rca?.likely_root_cause_service) return { title: "Review RCA evidence for ", service: String(rca.likely_root_cause_service) };
  if (incident?.title) return { title: `Investigate ${String(incident.title).toLowerCase()}` };
  if (anomaly?.service) return { title: "Investigate elevated signal in ", service: String(anomaly.service) };
  return { title: "Review current reliability signals" };
}

function isRemediationLiveReady(value: Record<string, unknown> | undefined) {
  const command = value?.command_center as Record<string, unknown> | undefined;
  const remediation = value?.remediation as Record<string, unknown> | undefined;
  return Boolean(command?.dangerous_actions_enabled && remediation?.dangerous_actions_enabled && remediation?.real_remediation_enabled && remediation?.execution_enabled && remediation?.live_demo_mode && remediation?.allowed_target_namespace === "cascade-targets");
}
