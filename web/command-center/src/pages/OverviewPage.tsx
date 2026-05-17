import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { Activity, AlertTriangle, Check, Database, Info, Lock, Search, ShieldCheck, Sparkles } from "lucide-react";
import {
  useAnomalies,
  useChaosRuns,
  useCounts,
  useFeatureWindows,
  useIncidents,
  useInvestigations,
  useRemediationPlans,
  useResilienceScores,
  useSystemHealth,
} from "../api/hooks";
import { Badge } from "../components/Badge";
import { DataTable } from "../components/tables/DataTable";

export function OverviewPage() {
  const counts = useCounts();
  const health = useSystemHealth();
  const anomalies = useAnomalies({ limit: 8 });
  const incidents = useIncidents({ limit: 8 });
  const investigations = useInvestigations({ limit: 8 });
  const runs = useChaosRuns({ limit: 8 });
  const scores = useResilienceScores({ limit: 8 });
  const remediation = useRemediationPlans({ limit: 8 });
  const features = useFeatureWindows({ limit: 24 });
  const degradedCount = health.data?.filter((item) => !item.ok).length ?? 0;
  const safetyPercent = health.data?.length ? Math.round(((health.data.length - degradedCount) / health.data.length) * 100) : undefined;
  const topIncident = incidents.data?.incidents?.[0];
  const topAnomaly = anomalies.data?.anomalies?.[0];

  return (
    <div className="page">
      <div className="metric-grid">
        <MetricCard tone="blue" icon={<Activity />} label="Telemetry Events" value={formatLarge(counts.data?.telemetry_events)} delta={`${features.data?.count ?? 0} feature windows`} />
        <MetricCard tone="amber" icon={<AlertTriangle />} label="Active Anomalies" value={formatLarge(counts.data?.anomaly_events)} delta={`${anomalies.data?.count ?? 0} recent signals`} />
        <MetricCard tone="violet" icon={<Database />} label="Knowledge Chunks" value={formatLarge(counts.data?.knowledge_chunks)} delta={`${counts.data?.knowledge_documents ?? "-"} documents`} />
        <MetricCard tone="emerald" icon={<ShieldCheck />} label="Safety Gates" value={safetyPercent === undefined ? "-" : `${safetyPercent}%`} delta={degradedCount ? `${degradedCount} degraded` : "All gates healthy"} />
      </div>

      <div className="overview-grid">
        <section className="panel">
          <div className="panel-title">
            <span>Platform Signal & Risk Trends</span>
            <button type="button" className="btn">24 Hours</button>
          </div>
          <div className="legend">
            <span style={{ color: "#3b82f6" }}><i />Telemetry Events</span>
            <span style={{ color: "#f59e0b" }}><i />Anomaly Score</span>
            <span style={{ color: "#a855f7" }}><i />Risk Score</span>
          </div>
          <SignalChart
            telemetry={(features.data?.features ?? []).map((row) => Number(row.event_count ?? 0))}
            anomaly={(anomalies.data?.anomalies ?? []).map((row) => Number(row.risk_score ?? 0))}
            risk={(scores.data?.scores ?? []).map((row) => Number(row.resilience_score ?? 0))}
          />
          <div className="panel-foot">
            <span><Info size={14} /> Spike analysis uses real recent telemetry and detector rows when available.</span>
            <Link className="btn" to="/telemetry">View Full Telemetry</Link>
          </div>
        </section>

        <section className="panel">
          <div className="panel-title">
            <span>Priority Incidents</span>
            <Link className="btn" to="/incidents">View All</Link>
          </div>
          <DataTable rows={incidents.data?.incidents ?? []} empty="No priority incidents" columns={[
            { key: "title", label: "Incident" },
            { key: "service", label: "Service" },
            { key: "severity", label: "Severity", render: (row) => <Badge tone={severityTone(row.severity)}>{String(row.severity ?? "Low")}</Badge> },
            { key: "started_at", label: "Detected" },
            { key: "status", label: "Status", render: (row) => <Badge tone="teal">{String(row.status ?? "Investigating")}</Badge> },
          ]} />
        </section>
      </div>

      <div className="overview-bottom">
        <section className="panel topology">
          <h2>Service Topology</h2>
          <div className="topology-map">
            <span className="topology-line l1" /><span className="topology-line l2" /><span className="topology-line l3" /><span className="topology-line l4" /><span className="topology-line l5" />
            {["frontend", "recommendationservice", "cartservice", "checkoutservice", "paymentservice", "shippingservice"].map((name, index) => (
              <div className={`svc s${index + 1}`} key={name}><strong>{name}</strong><span>{serviceOk(health.data, name) ? "Healthy" : "Monitoring"}</span></div>
            ))}
          </div>
        </section>

        <section className="panel">
          <h2>Remediation Workflow</h2>
          <div className="workflow-line">
            {["Evidence gathered", "Plan generated", "Human approved", "Dry-run validated", "Execution disabled"].map((label, index) => (
              <div className={`workflow-step ${index === 4 ? "disabled" : ""}`} key={label}>
                <span className="workflow-dot">{index === 4 ? <Lock size={15} /> : <Check size={17} />}</span>
                <span>{label}</span>
              </div>
            ))}
          </div>
          <div className="panel-foot">
            <span>Execution is disabled. Approval and dry-run validation remain the safe workflow.</span>
            <button className="btn btn-dry" type="button" disabled title="Real execution is disabled by policy"><Lock size={14} />Enable Execution</button>
          </div>
        </section>

        <div className="stack">
          <section className="panel">
            <h2>Knowledge Search</h2>
            <Link className="search-box" to="/knowledge">
              <Search size={18} />
              <span>Search knowledge chunks, runbooks, incidents...</span>
            </Link>
            <div className="chips">
              <span className="chip">checkout errors</span>
              <span className="chip">payment timeouts</span>
              <span className="chip">high latency</span>
              <span className="chip">+ Add filter</span>
            </div>
          </section>

          <section className="panel">
            <h2>Recommended Next Step</h2>
            <div className="recommend">
              <span className="recommend-icon"><Sparkles size={20} /></span>
              <span className="recommend-text">
                <strong>{topIncident?.service ? `Investigate elevated error rate in ${topIncident.service}` : topAnomaly?.service ? `Investigate anomaly in ${topAnomaly.service}` : "Review latest platform signals"}</strong>
                <span>{topIncident || topAnomaly ? "Similar patterns found in recent reliability signals." : "No urgent incident is currently available from the API."}</span>
              </span>
              <Link className="btn" to="/investigations">Start Investigation</Link>
            </div>
          </section>
        </div>
      </div>
      <div className="panel-foot" style={{ justifyContent: "flex-end" }}>Data as of {new Date().toLocaleTimeString()} <Info size={14} /></div>
    </div>
  );
}

function MetricCard({ tone, icon, label, value, delta }: { tone: "blue" | "amber" | "violet" | "emerald"; icon: ReactNode; label: string; value: string; delta: string }) {
  return (
    <section className={`metric-card ${tone}`}>
      <div className="metric-inner">
        <div className="metric-main">
          <span className="metric-icon">{icon}</span>
          <div>
            <div className="metric-label">{label}</div>
            <div className="metric-value">{value}</div>
            <div className="metric-delta">↗ {delta}</div>
          </div>
        </div>
      </div>
    </section>
  );
}

function SignalChart({ telemetry, anomaly, risk }: { telemetry: number[]; anomaly: number[]; risk: number[] }) {
  const t = normalizeSeries(telemetry);
  const a = normalizeSeries(anomaly);
  const r = normalizeSeries(risk);
  const hasData = t.length || a.length || r.length;
  return (
    <div className="chart-wrap">
      {!hasData ? <div className="state">Waiting for trend data from recent API rows.</div> : null}
      <svg className="trend-chart" viewBox="0 0 720 300" role="img" aria-label="Platform signal and risk trends">
        {[45, 90, 135, 180, 225].map((y) => <line key={y} className="chart-grid" x1="42" x2="700" y1={y} y2={y} />)}
        <polyline className="chart-line" stroke="#3b82f6" points={points(t, 42, 700, 36, 250)} />
        <polyline className="chart-line" stroke="#f59e0b" points={points(a, 42, 700, 36, 250)} />
        <polyline className="chart-line" stroke="#a855f7" points={points(r, 42, 700, 36, 250)} />
        <text x="42" y="282" fill="#94a3b8" fontSize="12">recent</text>
        <text x="650" y="282" fill="#94a3b8" fontSize="12">now</text>
      </svg>
    </div>
  );
}

function normalizeSeries(values: number[]) {
  return values.filter((value) => Number.isFinite(value));
}

function points(values: number[], minX: number, maxX: number, minY: number, maxY: number) {
  if (!values.length) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = max - min || 1;
  return values.map((value, index) => {
    const x = minX + ((maxX - minX) * index) / Math.max(1, values.length - 1);
    const y = maxY - ((value - min) / spread) * (maxY - minY);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function formatLarge(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  if (number >= 1_000_000) return `${(number / 1_000_000).toFixed(1)}M`;
  if (number >= 1_000) return number.toLocaleString();
  return String(number);
}

function severityTone(value: unknown): "good" | "warn" | "bad" | "neutral" {
  const severity = String(value ?? "").toLowerCase();
  if (severity.includes("critical") || severity.includes("high")) return "bad";
  if (severity.includes("medium") || severity.includes("warn")) return "warn";
  if (severity.includes("low")) return "good";
  return "neutral";
}

function serviceOk(items: unknown, service: string) {
  if (!Array.isArray(items)) return true;
  const normalized = service.toLowerCase();
  const match = items.find((item) => String((item as { name?: string }).name ?? "").toLowerCase().includes(normalized));
  return match ? Boolean((match as { ok?: boolean }).ok) : true;
}
