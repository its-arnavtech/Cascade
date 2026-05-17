import { useState } from "react";
import { useCreateInvestigation, useCreateRemediationPlan, useIncident, useIncidents } from "../api/hooks";
import { Badge } from "../components/Badge";
import { JsonBlock } from "../components/JsonBlock";
import { StatusPanel } from "../components/cards/StatusPanel";
import { DataTable } from "../components/tables/DataTable";

export function IncidentsPage() {
  const incidents = useIncidents({ limit: 30 });
  const [selected, setSelected] = useState<string>("");
  const detail = useIncident(selected);
  const createInvestigation = useCreateInvestigation();
  const createPlan = useCreateRemediationPlan();

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Incidents</h2><p>Incident records, reports, evidence, and safe follow-up workflows.</p></div></div>
      <StatusPanel title="Recent Incidents" loading={incidents.isLoading} error={incidents.error}>
        <DataTable
          rows={incidents.data?.incidents ?? []}
          columns={[
            { key: "started_at", label: "Started" },
            { key: "title", label: "Title" },
            { key: "service", label: "Service" },
            { key: "severity", label: "Severity", render: (row) => <Badge tone={severityTone(row.severity)}>{String(row.severity ?? "-")}</Badge> },
            { key: "action", label: "Open", render: (row) => <button className="btn" onClick={() => setSelected(String(row.incident_id ?? ""))}>View</button> },
          ]}
        />
      </StatusPanel>
      <StatusPanel title="Incident Detail / Report" loading={detail.isLoading} error={detail.error}>
        {selected ? (
          <>
            <div className="form-row">
              <button className="btn btn-primary" onClick={() => createInvestigation.mutate({ trigger_type: "incident", trigger_id: selected, namespace: "cascade-targets", objective: `Investigate incident ${selected}`, mode: "deterministic", max_steps: 12 })}>Start investigation</button>
              <button className="btn btn-dry" onClick={() => createPlan.mutate({ trigger_type: "incident", trigger_id: selected, service: "", namespace: "cascade-targets", objective: `Create safe remediation plan for incident ${selected}`, preferred_action_type: "investigate_only" })}>Create remediation plan</button>
            </div>
            <JsonBlock value={detail.data} />
          </>
        ) : (
          <div className="state">Select an incident to view report and evidence.</div>
        )}
      </StatusPanel>
    </div>
  );
}

function severityTone(value: unknown): "good" | "warn" | "bad" | "neutral" {
  const severity = String(value ?? "").toLowerCase();
  if (severity.includes("critical") || severity.includes("high")) return "bad";
  if (severity.includes("medium") || severity.includes("warn")) return "warn";
  if (severity.includes("low")) return "good";
  return "neutral";
}
