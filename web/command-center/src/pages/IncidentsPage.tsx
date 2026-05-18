import { useState } from "react";
import type { ReactNode } from "react";
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
  const selectedIncident = incidents.data?.incidents.find((incident) => incident.incident_id === selected);

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Incidents</h2><p>Incident records, reports, evidence, and safe follow-up workflows.</p></div></div>
      <StatusPanel title="Recent Incidents" loading={incidents.isLoading} error={incidents.error}>
        <DataTable
          caption="Recent incidents"
          rows={incidents.data?.incidents ?? []}
          getRowClassName={(row) => row.incident_id === selected ? "row-selected" : row.severity === "critical" ? "row-critical" : ""}
          onRowClick={(row) => setSelected(String(row.incident_id ?? ""))}
          columns={[
            { key: "started_at", label: "Started", width: "150px" },
            { key: "title", label: "Title" },
            { key: "service", label: "Service", width: "160px" },
            { key: "severity", label: "Severity", width: "120px", render: (row) => <Badge tone={severityTone(row.severity)}>{String(row.severity ?? "-")}</Badge> },
            { key: "action", label: "Open", width: "90px", align: "right", render: (row) => <button className="btn compact" onClick={(event) => { event.stopPropagation(); setSelected(String(row.incident_id ?? "")); }}>View</button> },
          ]}
        />
      </StatusPanel>
      <StatusPanel title="Incident Detail / Report" loading={detail.isLoading} error={detail.error}>
        {selected ? (
          <>
            <div className="form-row">
              <button className="btn btn-primary" onClick={() => createInvestigation.mutate({ trigger_type: "incident", trigger_id: selected, namespace: "cascade-targets", objective: `Investigate incident ${selected}`, mode: "deterministic", max_steps: 12 })}>Start investigation</button>
              <button className="btn btn-dry" onClick={() => createPlan.mutate({ trigger_type: "incident", trigger_id: selected, service: selectedIncident?.service ?? "", namespace: "cascade-targets", objective: `Create safe remediation plan for incident ${selected}`, preferred_action_type: "investigate_only" })}>Create remediation plan</button>
            </div>
            <IncidentReport value={detail.data} fallback={selectedIncident} selected={selected} />
          </>
        ) : (
          <div className="state">Select an incident to view report and evidence.</div>
        )}
      </StatusPanel>
    </div>
  );
}

function IncidentReport({ value, fallback, selected }: { value: unknown; fallback?: Record<string, unknown>; selected: string }) {
  const record = asRecord(value);
  const incident = asRecord(record?.incident) ?? record;
  const report = asRecord(record?.report) ?? asRecord(record?.incident_report) ?? asRecord(record?.data);
  const metadata = {
    started_at: incident?.started_at ?? fallback?.started_at,
    service: incident?.service ?? fallback?.service,
    severity: incident?.severity ?? fallback?.severity,
    status: incident?.status ?? fallback?.status ?? "open",
    correlation_id: incident?.correlation_id ?? incident?.incident_id ?? selected,
  };

  if (!incident && !report) return <JsonBlock value={value} />;

  return (
    <div className="incident-report">
      <section className="detail-card">
        <h3>Incident metadata</h3>
        <LabeledRow label="Started" value={String(metadata.started_at ?? "-")} />
        <LabeledRow label="Service" value={String(metadata.service ?? "-")} />
        <LabeledRow label="Severity" value={<Badge tone={severityTone(metadata.severity)}>{String(metadata.severity ?? "-")}</Badge>} />
        <LabeledRow label="Status" value={<Badge tone={statusTone(metadata.status)}>{String(metadata.status ?? "-")}</Badge>} />
        <LabeledRow label="Correlation ID" value={<code>{String(metadata.correlation_id ?? "-")}</code>} />
      </section>
      <section className="detail-card">
        <h3>{String(report?.title ?? incident?.title ?? "Incident report")}</h3>
        {report ? Object.entries(report).filter(([key]) => key !== "title").slice(0, 8).map(([key, reportValue]) => (
          <LabeledRow key={key} label={labelize(key)} value={formatValue(reportValue)} />
        )) : (
          <>
            <LabeledRow label="Summary" value={String(incident?.summary ?? "No structured report available.")} />
            <JsonBlock value={value} />
          </>
        )}
      </section>
    </div>
  );
}

function LabeledRow({ label, value }: { label: string; value: ReactNode }) {
  return <div className="labeled-row"><span>{label}</span><strong>{value ?? "-"}</strong></div>;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}

function formatValue(value: unknown): ReactNode {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return <JsonBlock value={value} />;
  return String(value);
}

function labelize(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function severityTone(value: unknown): "good" | "warn" | "bad" | "neutral" {
  const severity = String(value ?? "").toLowerCase();
  if (severity.includes("critical") || severity.includes("high")) return "bad";
  if (severity.includes("medium") || severity.includes("warn")) return "warn";
  if (severity.includes("low")) return "good";
  return "neutral";
}

function statusTone(value: unknown): "good" | "warn" | "bad" | "info" | "neutral" {
  const status = String(value ?? "").toLowerCase();
  if (status.includes("resolved") || status.includes("closed")) return "good";
  if (status.includes("critical") || status.includes("fail")) return "bad";
  if (status.includes("open") || status.includes("active")) return "warn";
  if (status.includes("pending") || status.includes("investigating")) return "info";
  return "neutral";
}
