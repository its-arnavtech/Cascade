import { FormEvent, useState } from "react";
import { dangerousActionsEnabled } from "../api/client";
import { useChaosPlans, useChaosPolicy, useChaosRuns, useCreateChaosPlan, useDryRunChaos, useResilienceScores } from "../api/hooks";
import { JsonBlock } from "../components/JsonBlock";
import { StatusPanel } from "../components/cards/StatusPanel";
import { DataTable } from "../components/tables/DataTable";

export function ChaosPage() {
  const policy = useChaosPolicy();
  const plans = useChaosPlans({ limit: 20 });
  const runs = useChaosRuns({ limit: 20 });
  const scores = useResilienceScores({ limit: 20 });
  const create = useCreateChaosPlan();
  const dryRun = useDryRunChaos();
  const [form, setForm] = useState({ target_service: "recommendationservice", target_namespace: "cascade-targets", experiment_kind: "pod_kill", duration_seconds: 30, objective: "Validate recommendationservice resilience with dry-run planning" });

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate({ ...form, duration_seconds: Number(form.duration_seconds), dry_run: true });
  }

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Chaos</h2><p>Dry-run planning and dry-run execution only from the UI.</p></div></div>
      <div className="banner warn">Real chaos execution is not exposed by default in the UI. Dangerous actions enabled: {String(dangerousActionsEnabled)}</div>
      <form className="form-grid" onSubmit={submit}>
        <input value={form.target_service} onChange={(e) => setForm({ ...form, target_service: e.target.value })} placeholder="target service" />
        <input value={form.target_namespace} onChange={(e) => setForm({ ...form, target_namespace: e.target.value })} placeholder="namespace" />
        <select value={form.experiment_kind} onChange={(e) => setForm({ ...form, experiment_kind: e.target.value })}><option>pod_kill</option><option>network_delay</option><option>stress_cpu</option></select>
        <input type="number" min={5} max={300} value={form.duration_seconds} onChange={(e) => setForm({ ...form, duration_seconds: Number(e.target.value) })} />
        <input value={form.objective} onChange={(e) => setForm({ ...form, objective: e.target.value })} placeholder="objective" />
        <button type="submit">Create dry-run plan</button>
      </form>
      {create.data ? <div className="state success">Created chaos plan {String(create.data.plan_id ?? "")}</div> : null}
      {create.error ? <div className="state error">{create.error.message}</div> : null}
      <div className="grid two">
        <StatusPanel title="Safety Policy" loading={policy.isLoading} error={policy.error}><JsonBlock value={policy.data} /></StatusPanel>
        <StatusPanel title="Resilience Scores" loading={scores.isLoading} error={scores.error}>
          <DataTable rows={scores.data?.scores ?? []} columns={[{ key: "computed_at", label: "Computed" }, { key: "service", label: "Service" }, { key: "resilience_score", label: "Score" }, { key: "grade", label: "Grade" }, { key: "explanation", label: "Explanation" }]} />
        </StatusPanel>
      </div>
      <StatusPanel title="Chaos Plans" loading={plans.isLoading} error={plans.error}>
        <DataTable rows={plans.data?.plans ?? []} columns={[{ key: "created_at", label: "Created" }, { key: "target_service", label: "Service" }, { key: "experiment_kind", label: "Kind" }, { key: "risk_level", label: "Risk" }, { key: "status", label: "Status" }, { key: "dryrun", label: "Dry-run", render: (row) => <button onClick={() => dryRun.mutate({ plan_id: row.plan_id ?? "", observation_window_seconds: 10, trigger_agent_investigation: false })}>Dry-run execute</button> }]} />
      </StatusPanel>
      <StatusPanel title="Chaos Runs" loading={runs.isLoading} error={runs.error}>
        <DataTable rows={runs.data?.runs ?? []} columns={[{ key: "started_at", label: "Started" }, { key: "target_service", label: "Service" }, { key: "experiment_kind", label: "Kind" }, { key: "dry_run", label: "Dry-run" }, { key: "status", label: "Status" }]} />
      </StatusPanel>
    </div>
  );
}
