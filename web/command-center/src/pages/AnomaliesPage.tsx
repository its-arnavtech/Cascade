import { useState } from "react";
import { useAnomalies, useCreateInvestigation } from "../api/hooks";
import { Badge } from "../components/Badge";
import { StatusPanel } from "../components/cards/StatusPanel";
import { DataTable } from "../components/tables/DataTable";

export function AnomaliesPage() {
  const [service, setService] = useState("");
  const anomalies = useAnomalies({ service, limit: 30 });
  const createInvestigation = useCreateInvestigation();

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Anomalies</h2><p>Detected model and threshold signals, with safe investigation creation.</p></div></div>
      <div className="filters"><label className="form-field">Service<input placeholder="service" value={service} onChange={(e) => setService(e.target.value)} /></label></div>
      <StatusPanel title="Recent Anomalies" loading={anomalies.isLoading} error={anomalies.error}>
        <DataTable
          rows={anomalies.data?.anomalies ?? []}
          columns={[
            { key: "detected_at", label: "Detected" },
            { key: "service", label: "Service" },
            { key: "severity", label: "Severity", render: (row) => <Badge tone={severityTone(row.severity)}>{String(row.severity ?? "-")}</Badge> },
            { key: "risk_score", label: "Risk" },
            { key: "detector_type", label: "Detector" },
            { key: "explanation", label: "Explanation" },
            {
              key: "action",
              label: "Action",
              render: (row) => (
                <button
                  className="btn btn-primary"
                  onClick={() =>
                    createInvestigation.mutate({
                      trigger_type: "anomaly",
                      trigger_id: row.anomaly_id ?? "",
                      service: row.service ?? "",
                      namespace: row.namespace ?? "cascade-targets",
                      objective: `Investigate anomaly for ${row.service ?? "service"}`,
                      mode: "deterministic",
                      max_steps: 12,
                    })
                  }
                >
                  Investigate
                </button>
              ),
            },
          ]}
        />
        {createInvestigation.error ? <div className="state error">{createInvestigation.error.message}</div> : null}
        {createInvestigation.data ? <div className="state success">Investigation started: {String(createInvestigation.data.investigation_id ?? "created")}</div> : null}
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
