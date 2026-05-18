import { FormEvent, useState } from "react";
import type { ReactNode } from "react";
import { useCreateInvestigation, useCreateRemediationPlan, useInvestigation, useInvestigations } from "../api/hooks";
import { Badge } from "../components/Badge";
import { JsonBlock } from "../components/JsonBlock";
import { StatusPanel } from "../components/cards/StatusPanel";
import { DataTable } from "../components/tables/DataTable";

export function InvestigationsPage() {
  const investigations = useInvestigations({ limit: 30 });
  const create = useCreateInvestigation();
  const createPlan = useCreateRemediationPlan();
  const [selected, setSelected] = useState("");
  const detail = useInvestigation(selected);
  const [form, setForm] = useState({ trigger_type: "manual", service: "recommendationservice", namespace: "cascade-targets", objective: "Investigate recent reliability signals", max_steps: 12 });

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate({ ...form, mode: "deterministic", max_steps: Number(form.max_steps) });
  }

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Investigations</h2><p>Deterministic agent runs with read-only tools and evidence reports.</p></div></div>
      <form className="form-grid two-column" onSubmit={submit}>
        <div className="form-field"><label htmlFor="investigation-trigger">Trigger type</label><select id="investigation-trigger" value={form.trigger_type} onChange={(event) => setForm({ ...form, trigger_type: event.target.value })}><option>manual</option><option>anomaly</option><option>incident</option><option>chaos</option></select></div>
        <div className="form-field"><label htmlFor="investigation-objective">Objective</label><input id="investigation-objective" value={form.objective} onChange={(event) => setForm({ ...form, objective: event.target.value })} placeholder="objective" /></div>
        <div className="form-field"><label htmlFor="investigation-service">Service</label><input id="investigation-service" value={form.service} onChange={(event) => setForm({ ...form, service: event.target.value })} placeholder="service" /></div>
        <div className="form-field"><label htmlFor="investigation-steps">Max steps</label><input id="investigation-steps" type="number" min={1} max={20} value={form.max_steps} onChange={(event) => setForm({ ...form, max_steps: Number(event.target.value) })} /></div>
        <div className="form-field"><label htmlFor="investigation-namespace">Namespace</label><input id="investigation-namespace" value={form.namespace} onChange={(event) => setForm({ ...form, namespace: event.target.value })} placeholder="namespace" /></div>
        <button type="submit" className="btn btn-primary full" disabled={create.isPending}>{create.isPending ? <span className="spinner" /> : null}{create.isPending ? "Starting..." : "Start investigation"}</button>
      </form>
      <div aria-live="polite">{create.error ? <div className="state error">{create.error.message}</div> : null}{create.data ? <div className="state success">Created investigation {String(create.data.investigation_id ?? "")}</div> : null}</div>
      <StatusPanel title="Recent Investigations" loading={investigations.isLoading} error={investigations.error}>
        <DataTable caption="Recent investigations" rows={investigations.data?.investigations ?? []} columns={[
          { key: "created_at", label: "Created", width: "150px" },
          { key: "status", label: "Status", width: "130px", render: (row) => <Badge tone={statusTone(row.status)}>{String(row.status ?? "-")}</Badge> },
          { key: "service", label: "Service", width: "150px" },
          { key: "objective", label: "Objective", render: (row) => String(row.objective ?? "").slice(0, 200) },
          { key: "confidence", label: "Confidence", width: "110px", render: (row) => formatConfidence(row.confidence) },
          { key: "open", label: "Open", width: "90px", align: "right", render: (row) => <button className="btn compact" onClick={() => setSelected(String(row.investigation_id ?? ""))}>View</button> },
        ]} />
      </StatusPanel>
      <StatusPanel title="Investigation Detail" loading={detail.isLoading} error={detail.error}>
        {selected ? (
          <>
            <button className="btn btn-dry" onClick={() => createPlan.mutate({ trigger_type: "investigation", trigger_id: selected, service: "", namespace: "cascade-targets", objective: `Create safe plan from investigation ${selected}`, preferred_action_type: "investigate_only" })}>Create remediation plan</button>
            <InvestigationDetail value={detail.data} />
          </>
        ) : <div className="state">Select an investigation to inspect steps, tool calls, report, and suggested remediation text.</div>}
      </StatusPanel>
    </div>
  );
}

function InvestigationDetail({ value }: { value: unknown }) {
  const record = asRecord(value) ?? {};
  const investigation = asRecord(record.investigation) ?? record;
  const steps = asArray(record.steps) ?? asArray(record.tool_calls) ?? asArray(investigation.steps) ?? asArray(investigation.tool_calls);
  const confidence = Number(investigation.confidence ?? record.confidence ?? 0);

  return (
    <div className="investigation-detail">
      <section className="detail-card">
        <h3>Summary</h3>
        <div className="summary-grid">
          <LabeledRow label="Status" value={<Badge tone={statusTone(investigation.status)}>{String(investigation.status ?? "-")}</Badge>} />
          <LabeledRow label="Service" value={String(investigation.service ?? "-")} />
          <LabeledRow label="Created" value={String(investigation.created_at ?? "-")} />
          <div className="confidence-row"><span>Confidence</span><div className="confidence-track"><div style={{ width: `${Math.max(0, Math.min(100, confidence <= 1 ? confidence * 100 : confidence))}%` }} /></div><strong>{formatConfidence(confidence)}</strong></div>
        </div>
      </section>
      {steps?.length ? (
        <section className="detail-card">
          <h3>Steps and tool calls</h3>
          <div className="timeline">
            {steps.map((step, index) => {
              const item = asRecord(step) ?? {};
              return <details key={String(item.id ?? index)} open={index === 0}><summary><span className="timeline-num">{index + 1}</span><strong>{String(item.tool_name ?? item.name ?? item.tool ?? `Step ${index + 1}`)}</strong><Badge tone={statusTone(item.status)}>{String(item.status ?? "recorded")}</Badge></summary><JsonBlock value={item.result ?? item.output ?? item} /></details>;
            })}
          </div>
        </section>
      ) : <JsonBlock value={value} />}
    </div>
  );
}

function LabeledRow({ label, value }: { label: string; value: ReactNode }) {
  return <div className="labeled-row"><span>{label}</span><strong>{value}</strong></div>;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}

function asArray(value: unknown): unknown[] | undefined {
  return Array.isArray(value) ? value : undefined;
}

function statusTone(value: unknown): "good" | "warn" | "bad" | "info" | "dry" | "neutral" {
  const status = String(value ?? "").toLowerCase();
  if (status.includes("complete") || status.includes("success")) return "good";
  if (status.includes("fail") || status.includes("error")) return "bad";
  if (status.includes("run") || status.includes("investigating")) return "info";
  if (status.includes("pending") || status.includes("dry")) return "dry";
  if (status.includes("warn")) return "warn";
  return "neutral";
}

function formatConfidence(value: unknown) {
  const confidence = Number(value);
  if (!Number.isFinite(confidence)) return "-";
  const percent = confidence <= 1 ? confidence * 100 : confidence;
  return `${Math.round(percent)}%`;
}
