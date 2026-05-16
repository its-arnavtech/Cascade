import { FormEvent, useState } from "react";
import { useCreateInvestigation, useCreateRemediationPlan, useInvestigation, useInvestigations } from "../api/hooks";
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
      <form className="form-grid" onSubmit={submit}>
        <select value={form.trigger_type} onChange={(e) => setForm({ ...form, trigger_type: e.target.value })}><option>manual</option><option>anomaly</option><option>incident</option><option>chaos</option></select>
        <input value={form.service} onChange={(e) => setForm({ ...form, service: e.target.value })} placeholder="service" />
        <input value={form.namespace} onChange={(e) => setForm({ ...form, namespace: e.target.value })} placeholder="namespace" />
        <input value={form.objective} onChange={(e) => setForm({ ...form, objective: e.target.value })} placeholder="objective" />
        <input type="number" min={1} max={20} value={form.max_steps} onChange={(e) => setForm({ ...form, max_steps: Number(e.target.value) })} />
        <button type="submit">Start investigation</button>
      </form>
      {create.error ? <div className="state error">{create.error.message}</div> : null}
      {create.data ? <div className="state success">Created investigation {String(create.data.investigation_id ?? "")}</div> : null}
      <StatusPanel title="Recent Investigations" loading={investigations.isLoading} error={investigations.error}>
        <DataTable rows={investigations.data?.investigations ?? []} columns={[{ key: "created_at", label: "Created" }, { key: "status", label: "Status" }, { key: "service", label: "Service" }, { key: "objective", label: "Objective" }, { key: "confidence", label: "Confidence" }, { key: "open", label: "Open", render: (row) => <button onClick={() => setSelected(String(row.investigation_id ?? ""))}>View</button> }]} />
      </StatusPanel>
      <StatusPanel title="Investigation Detail" loading={detail.isLoading} error={detail.error}>
        {selected ? (
          <>
            <button onClick={() => createPlan.mutate({ trigger_type: "investigation", trigger_id: selected, service: "", namespace: "cascade-targets", objective: `Create safe plan from investigation ${selected}`, preferred_action_type: "investigate_only" })}>Create remediation plan</button>
            <JsonBlock value={detail.data} />
          </>
        ) : <div className="state">Select an investigation to inspect steps, tool calls, report, and suggested remediation text.</div>}
      </StatusPanel>
    </div>
  );
}
