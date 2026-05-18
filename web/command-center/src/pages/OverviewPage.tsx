import { Link } from "react-router-dom";
import { AlertTriangle, BarChart3, BookOpen, CheckCircle2, Database, GitBranch, Layers3, Search, ShieldCheck, Sparkles } from "lucide-react";
import { useAnomalies, useCounts, useFeatureWindows, useIncidents, useInvestigations, useKnowledgeStats, useRemediationPlans, useResilienceScores, useSystemHealth } from "../api/hooks";
import { Badge } from "../components/Badge";
import { StatCard } from "../components/cards/StatCard";
import { StatusPanel } from "../components/cards/StatusPanel";
import { DataTable } from "../components/tables/DataTable";

export function OverviewPage() {
  const counts = useCounts();
  const health = useSystemHealth();
  const features = useFeatureWindows({ limit: 12 });
  const anomalies = useAnomalies({ limit: 8 });
  const incidents = useIncidents({ limit: 6 });
  const investigations = useInvestigations({ limit: 4 });
  const scores = useResilienceScores({ limit: 8 });
  const remediation = useRemediationPlans({ limit: 5 });
  const knowledgeStats = useKnowledgeStats();
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
        <StatusPanel title="Platform Signal & Risk Trends" loading={features.isLoading || anomalies.isLoading || scores.isLoading} error={features.error ?? anomalies.error ?? scores.error}>
          <SignalTrends
            features={features.data?.features ?? []}
            anomalies={anomalies.data?.anomalies ?? []}
            scores={scores.data?.scores ?? []}
          />
        </StatusPanel>
        <StatusPanel title="Priority Incidents" loading={incidents.isLoading} error={incidents.error}>
          <DataTable
            caption="Priority incidents"
            rows={incidents.data?.incidents ?? []}
            empty="No incidents returned by the API."
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
        <section className="panel topology-panel">
          <div className="panel-heading"><h2>Service Topology</h2></div>
          <div className="topology-map">
            {targetServices.map((service) => (
              <div key={service} className={`topology-node ${serviceHealthTone(service, health.data)}`}>
                <CheckCircle2 size={14} />
                <strong>{service}</strong>
                <span>{serviceHealthLabel(service, health.data)}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="panel workflow-panel">
          <div className="panel-heading"><h2>Remediation Workflow</h2></div>
          <div className="workflow-track">
            {["Evidence gathered", "Plan generated", "Human approved", "Dry-run validated", "Execution disabled"].map((step, index) => (
              <div className={`workflow-step ${index === 4 ? "disabled" : "done"}`} key={step}>
                <span>{index === 4 ? "↻" : "✓"}</span>
                <strong>{step}</strong>
              </div>
            ))}
          </div>
          <div className="workflow-note">
            <span>Execution is disabled. Enable outside the UI only after operator review.</span>
            <button type="button" className="btn-dry" disabled>Enable Execution</button>
          </div>
        </section>

        <div className="side-stack">
          <section className="panel knowledge-panel">
            <div className="panel-heading"><h2>Knowledge Search</h2></div>
            <Link className="searchbox-link" to="/knowledge">
              <Search size={18} />
              <span>Search knowledge chunks, runbooks, incidents...</span>
            </Link>
            <div className="query-chips">
              <span>checkout errors</span>
              <span>payment timeouts</span>
              <span>high latency</span>
            </div>
          </section>
          <section className="panel next-step-panel">
            <div className="panel-heading"><h2>Recommended Next Step</h2></div>
            <div className="next-step">
              <span className="next-step-icon"><Sparkles size={18} /></span>
              <div>
                <strong>{recommendedTitle(latestIncident, latestAnomaly)}</strong>
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

const targetServices = ["frontend", "recommendationservice", "cartservice", "checkoutservice", "paymentservice", "shippingservice"];

function SignalTrends({ features, anomalies, scores }: { features: Record<string, unknown>[]; anomalies: Record<string, unknown>[]; scores: Record<string, unknown>[] }) {
  const points = features.length ? features.slice(0, 10) : anomalies.slice(0, 10);
  if (!points.length && !scores.length) return <div className="state">No platform signal data returned yet.</div>;
  return (
    <div className="signal-panel">
      <div className="signal-legend">
        <span className="blue">Telemetry Events</span>
        <span className="amber">Anomaly Score</span>
        <span className="violet">Risk Score</span>
      </div>
      <div className="trend-bars">
        {(points.length ? points : scores).slice(0, 12).map((point, index) => {
          const events = Number(point.event_count ?? point.telemetry_events ?? 0);
          const risk = Number(point.risk_score ?? point.resilience_score ?? 0);
          const errors = Number(point.error_count ?? 0);
          return (
            <div className="trend-column" key={String(point.window_id ?? point.anomaly_id ?? point.score_id ?? index)}>
              <span className="bar blue" style={{ height: `${clamp(events, 12, 100)}%` }} />
              <span className="bar amber" style={{ height: `${clamp(errors || risk * 80, 8, 90)}%` }} />
              <span className="bar violet" style={{ height: `${clamp(risk <= 1 ? risk * 100 : risk, 8, 100)}%` }} />
            </div>
          );
        })}
      </div>
      <p><Layers3 size={15} /> Recent feature windows and risk signals are plotted from live API responses.</p>
    </div>
  );
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

function serviceHealthTone(service: string, health?: { name: string; ok: boolean }[]) {
  const match = health?.find((item) => item.name.includes(service));
  if (!match) return "monitoring";
  return match.ok ? "healthy" : "degraded";
}

function serviceHealthLabel(service: string, health?: { name: string; ok: boolean }[]) {
  const match = health?.find((item) => item.name.includes(service));
  if (!match) return "Monitoring";
  return match.ok ? "Healthy" : "Degraded";
}

function recommendedTitle(incident?: Record<string, unknown>, anomaly?: Record<string, unknown>) {
  if (incident?.title) return `Investigate ${String(incident.title).toLowerCase()}`;
  if (anomaly?.service) return `Investigate elevated signal in ${String(anomaly.service)}`;
  return "Review current reliability signals";
}
