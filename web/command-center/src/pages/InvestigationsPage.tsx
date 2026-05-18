import { FormEvent, MouseEvent, useRef, useState } from "react";
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
  const detailRef = useRef<HTMLElement | null>(null);
  const detail = useInvestigation(selected);
  const [form, setForm] = useState({ trigger_type: "manual", service: "recommendationservice", namespace: "cascade-targets", objective: "Investigate recent reliability signals", max_steps: 12 });

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate({ ...form, mode: "deterministic", max_steps: Number(form.max_steps) });
  }

  function viewInvestigation(event: MouseEvent<HTMLButtonElement>, row: Record<string, unknown>) {
    event.stopPropagation();
    const id = getInvestigationId(row);
    if (!id) return;
    setSelected(id);
    window.requestAnimationFrame(() => detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Investigations</h2><p>Deterministic agent runs with read-only tools and evidence reports.</p></div></div>
      <form className="form-grid two-column" onSubmit={submit}>
        <div className="form-field"><label htmlFor="investigation-trigger">Trigger type</label><select id="investigation-trigger" value={form.trigger_type} onChange={(e) => setForm({ ...form, trigger_type: e.target.value })}><option>manual</option><option>anomaly</option><option>incident</option><option>chaos</option></select></div>
        <div className="form-field"><label htmlFor="investigation-objective">Objective</label><input id="investigation-objective" value={form.objective} onChange={(e) => setForm({ ...form, objective: e.target.value })} placeholder="objective" /></div>
        <div className="form-field"><label htmlFor="investigation-service">Service</label><input id="investigation-service" value={form.service} onChange={(e) => setForm({ ...form, service: e.target.value })} placeholder="service" /></div>
        <div className="form-field"><label htmlFor="investigation-steps">Max steps</label><input id="investigation-steps" type="number" min={1} max={20} value={form.max_steps} onChange={(e) => setForm({ ...form, max_steps: Number(e.target.value) })} /></div>
        <div className="form-field"><label htmlFor="investigation-namespace">Namespace</label><input id="investigation-namespace" value={form.namespace} onChange={(e) => setForm({ ...form, namespace: e.target.value })} placeholder="namespace" /></div>
        <button type="submit" className="full" disabled={create.isPending}>{create.isPending ? <span className="spinner" /> : null}{create.isPending ? "Starting..." : "Start investigation"}</button>
      </form>
      <div aria-live="polite">{create.error ? <div className="state error">{create.error.message}</div> : null}{create.data ? <div className="state success">Created investigation {String(create.data.investigation_id ?? "")}</div> : null}</div>
      <StatusPanel title="Recent Investigations" loading={investigations.isLoading} error={investigations.error}>
        <DataTable
          caption="Recent investigations"
          rows={investigations.data?.investigations ?? []}
          getRowClassName={(row) => getInvestigationId(row) === selected ? "row-selected" : ""}
          onRowClick={(row) => {
            const id = getInvestigationId(row);
            if (id) setSelected(id);
          }}
          columns={[
            { key: "created_at", label: "Created", width: "140px" },
            { key: "status", label: "Status", width: "118px", render: (row) => <Badge tone={statusTone(row.status)}>{String(row.status ?? "-")}</Badge> },
            { key: "service", label: "Service", width: "140px" },
            { key: "objective", label: "Objective", render: (row) => String(row.objective ?? "").slice(0, 200) },
            { key: "confidence", label: "Confidence", width: "100px", render: (row) => formatConfidence(row.confidence) },
            {
              key: "open",
              label: "Open",
              width: "96px",
              align: "right",
              render: (row) => {
                const id = getInvestigationId(row);
                return (
                  <div className="table-actions">
                    <button
                      type="button"
                      className="compact table-action"
                      disabled={!id}
                      aria-label={id ? `View investigation ${id}` : "Investigation detail unavailable"}
                      onClick={(event) => viewInvestigation(event, row)}
                    >
                      View
                    </button>
                  </div>
                );
              },
            },
          ]}
        />
      </StatusPanel>
      <section ref={detailRef} className="detail-anchor" aria-live="polite">
      <StatusPanel title={selected ? `Investigation Detail: ${selected}` : "Investigation Detail"} loading={detail.isLoading} error={detail.error}>
        {selected ? (
          <>
            <button type="button" className="btn-dry" onClick={() => createPlan.mutate({ trigger_type: "investigation", trigger_id: selected, service: "", namespace: "cascade-targets", objective: `Create safe plan from investigation ${selected}`, preferred_action_type: "investigate_only" })}>Create remediation plan</button>
            {detail.data ? <InvestigationDetail value={detail.data} /> : <div className="state">No investigation detail was returned for this record yet.</div>}
          </>
        ) : <div className="state">Select an investigation to inspect steps, tool calls, report, and suggested remediation text.</div>}
      </StatusPanel>
      </section>
    </div>
  );
}

function getInvestigationId(row: Record<string, unknown>) {
  const id = row.investigation_id ?? row.run_id ?? row.id;
  return id === undefined || id === null || id === "" ? "" : String(id);
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
              return <details key={String(item.id ?? index)} open={index === 0}><summary><span>{index + 1}</span><strong>{String(item.tool_name ?? item.name ?? item.tool ?? `Step ${index + 1}`)}</strong><Badge tone={statusTone(item.status)}>{String(item.status ?? "recorded")}</Badge></summary><JsonBlock value={item.result ?? item.output ?? item} /></details>;
            })}
          </div>
        </section>
      ) : <JsonBlock value={value} />}
    </div>
  );
}

function LabeledRow({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="labeled-row"><span>{label}</span><strong>{value}</strong></div>;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}

function asArray(value: unknown): unknown[] | undefined {
  return Array.isArray(value) ? value : undefined;
}

function statusTone(value: unknown): "good" | "warn" | "bad" | "info" | "neutral" {
  const status = String(value ?? "").toLowerCase();
  if (status.includes("complete") || status.includes("success")) return "good";
  if (status.includes("fail") || status.includes("error")) return "bad";
  if (status.includes("run") || status.includes("pending")) return "info";
  if (status.includes("warn")) return "warn";
  return "neutral";
}

function formatConfidence(value: unknown) {
  const confidence = Number(value);
  if (!Number.isFinite(confidence)) return "-";
  const percent = confidence <= 1 ? confidence * 100 : confidence;
  return `${Math.round(percent)}%`;
}
