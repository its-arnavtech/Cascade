import { useState } from "react";
import { Link } from "react-router-dom";
import { useAnomalies, useCreateInvestigation } from "../api/hooks";
import { Badge } from "../components/Badge";
import { StatusPanel } from "../components/cards/StatusPanel";
import { DataTable } from "../components/tables/DataTable";

export function AnomaliesPage() {
  const [service, setService] = useState("");
  const [confirming, setConfirming] = useState<Set<string>>(new Set());
  const anomalies = useAnomalies({ service, limit: 30 });
  const createInvestigation = useCreateInvestigation();
  const created = createInvestigation.data?.investigation_id ? String(createInvestigation.data.investigation_id) : "";

  function requestInvestigation(row: { anomaly_id?: string; service?: string; namespace?: string }) {
    const id = row.anomaly_id ?? "";
    if (!id) return;
    if (!confirming.has(id)) {
      setConfirming((current) => new Set(current).add(id));
      window.setTimeout(() => setConfirming((current) => {
        const next = new Set(current);
        next.delete(id);
        return next;
      }), 3000);
      return;
    }
    createInvestigation.mutate({
      trigger_type: "anomaly",
      trigger_id: id,
      service: row.service ?? "",
      namespace: row.namespace ?? "cascade-targets",
      objective: `Investigate anomaly for ${row.service ?? "service"}`,
      mode: "deterministic",
      max_steps: 12,
    });
  }

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Anomalies</h2><p>Detected model and threshold signals, with safe investigation creation.</p></div></div>
      <div className="filters"><div className="form-field"><label htmlFor="anomaly-service">Service</label><input id="anomaly-service" placeholder="recommendationservice" value={service} onChange={(e) => setService(e.target.value)} /></div></div>
      <StatusPanel title="Recent Anomalies" loading={anomalies.isLoading} error={anomalies.error}>
        <DataTable
          caption="Recent anomalies"
          rows={anomalies.data?.anomalies ?? []}
          getRowClassName={(row) => row.severity === "critical" ? "row-critical" : ""}
          columns={[
            { key: "detected_at", label: "Detected", width: "110px" },
            { key: "service", label: "Service", width: "130px" },
            { key: "severity", label: "Severity", width: "90px", render: (row) => <Badge tone={severityTone(row.severity)}>{String(row.severity ?? "-")}</Badge> },
            { key: "risk_score", label: "Risk", width: "80px", render: (row) => <Badge tone={riskTone(row.risk_score)}>{formatRisk(row.risk_score)}</Badge> },
            { key: "detector_type", label: "Detector", width: "110px" },
            { key: "explanation", label: "Explanation" },
            {
              key: "action",
              label: "Action",
              width: "120px",
              align: "right",
              render: (row) => (
                created ? (
                  <Link className="badge-link" to="/investigations"><Badge tone="teal">Investigating</Badge></Link>
                ) : (
                  <button type="button" className={confirming.has(row.anomaly_id ?? "") ? "btn-warn compact" : "compact"} disabled={createInvestigation.isPending} onClick={() => requestInvestigation(row)}>
                    {confirming.has(row.anomaly_id ?? "") ? "Confirm?" : "Investigate"}
                  </button>
                )
              ),
            },
          ]}
        />
        <div aria-live="polite">
          {createInvestigation.error ? <div className="state error">{createInvestigation.error.message}</div> : null}
          {createInvestigation.data ? <div className="state success">Investigation started: {String(createInvestigation.data.investigation_id ?? "created")}</div> : null}
        </div>
      </StatusPanel>
    </div>
  );
}

function severityTone(value: unknown): "good" | "warn" | "bad" | "neutral" {
  const severity = String(value ?? "").toLowerCase();
  if (severity.includes("critical") || severity.includes("high")) return "bad";
  if (severity.includes("warning") || severity.includes("medium")) return "warn";
  if (severity.includes("low")) return "good";
  return "neutral";
}

function riskTone(value: unknown): "warn" | "bad" | "neutral" {
  const risk = Number(value ?? 0);
  if (risk >= 0.75) return "bad";
  if (risk >= 0.4) return "warn";
  return "neutral";
}

function formatRisk(value: unknown) {
  const risk = Number(value);
  if (!Number.isFinite(risk)) return "-";
  if (risk >= 0.75) return "high";
  if (risk >= 0.4) return "medium";
  return "low";
}
