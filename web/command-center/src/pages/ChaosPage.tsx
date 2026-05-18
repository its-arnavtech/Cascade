import { FormEvent, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { dangerousActionsEnabled } from "../api/client";
import { useChaosPlans, useChaosPolicy, useChaosRuns, useCreateChaosPlan, useDryRunChaos, useResilienceScores } from "../api/hooks";
import { Badge } from "../components/Badge";
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
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [form, setForm] = useState({ target_service: "recommendationservice", target_namespace: "cascade-targets", experiment_kind: "pod_kill", duration_seconds: 30, objective: "Validate recommendationservice resilience with dry-run planning" });

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate({ ...form, duration_seconds: Number(form.duration_seconds), dry_run: true });
  }

  function toggle(id: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Chaos</h2><p>Dry-run planning and dry-run execution only from the UI.</p></div></div>
      <div className={`banner ${dangerousActionsEnabled ? "bad" : "warn"}`}><AlertTriangle size={18} />{dangerousActionsEnabled ? "LIVE MODE: real chaos execution is enabled outside the default safe UI." : "Real chaos execution is blocked. All UI actions are dry-run only."}</div>
      <form className="form-grid two-column" onSubmit={submit}>
        <div className="form-field"><label htmlFor="chaos-service">Target service</label><input id="chaos-service" value={form.target_service} onChange={(event) => setForm({ ...form, target_service: event.target.value })} placeholder="target service" /></div>
        <div className="form-field"><label htmlFor="chaos-kind">Experiment kind</label><select id="chaos-kind" value={form.experiment_kind} onChange={(event) => setForm({ ...form, experiment_kind: event.target.value })}><option>pod_kill</option><option>network_delay</option><option>stress_cpu</option></select></div>
        <div className="form-field"><label htmlFor="chaos-namespace">Namespace</label><input id="chaos-namespace" value={form.target_namespace} onChange={(event) => setForm({ ...form, target_namespace: event.target.value })} placeholder="namespace" /></div>
        <div className="form-field"><label htmlFor="chaos-duration">Duration seconds</label><input id="chaos-duration" type="number" min={5} max={300} value={form.duration_seconds} onChange={(event) => setForm({ ...form, duration_seconds: Number(event.target.value) })} /></div>
        <div className="form-field full"><label htmlFor="chaos-objective">Objective</label><input id="chaos-objective" value={form.objective} onChange={(event) => setForm({ ...form, objective: event.target.value })} placeholder="objective" /></div>
        <button className="btn btn-dry full" type="submit" disabled={create.isPending}>Create dry-run plan</button>
      </form>
      {create.data ? <div className="state success">Created chaos plan {String(create.data.plan_id ?? "")}</div> : null}
      {create.error ? <div className="state error">{create.error.message}</div> : null}
      <div className="grid two">
        <StatusPanel title="Safety Policy" loading={policy.isLoading} error={policy.error}><JsonBlock value={policy.data} /></StatusPanel>
        <StatusPanel title="Resilience Scores" loading={scores.isLoading} error={scores.error}>
          <DataTable caption="Resilience scores" rows={scores.data?.scores ?? []} columns={[
            { key: "computed_at", label: "Computed", width: "140px" },
            { key: "service", label: "Service", width: "150px" },
            { key: "resilience_score", label: "Score", width: "110px", render: (row) => <Badge tone={gradeTone(row.grade)}>{formatScore(row.resilience_score, row.grade)}</Badge> },
            { key: "explanation", label: "Explanation", render: (row) => {
              const id = String(row.score_id ?? row.service ?? "");
              const text = String(row.explanation ?? "");
              const open = expanded.has(id);
              return <span>{open ? text : `${text.slice(0, 160)}${text.length > 160 ? "..." : ""}`} {text.length > 160 ? <button type="button" className="link-button" onClick={() => toggle(id)}>{open ? "Show less" : "Show more"}</button> : null}</span>;
            } },
          ]} />
        </StatusPanel>
      </div>
      <StatusPanel title="Chaos Plans" loading={plans.isLoading} error={plans.error}>
        <DataTable caption="Chaos plans" rows={plans.data?.plans ?? []} columns={[
          { key: "created_at", label: "Created", width: "140px" },
          { key: "target_service", label: "Service", width: "150px" },
          { key: "experiment_kind", label: "Kind", width: "130px" },
          { key: "risk_level", label: "Risk", width: "110px", render: (row) => <Badge tone={riskTone(row.risk_level)}>{String(row.risk_level ?? "-")}</Badge> },
          { key: "status", label: "Status", width: "130px", render: (row) => <Badge tone={statusTone(row.status)}>{String(row.status ?? "-")}</Badge> },
          { key: "dryrun", label: "Dry-run", width: "140px", align: "right", render: (row) => <button className="btn btn-dry compact" disabled={dryRun.isPending} onClick={() => dryRun.mutate({ plan_id: row.plan_id ?? "", observation_window_seconds: 10, trigger_agent_investigation: false })}>Dry-run execute</button> },
        ]} />
      </StatusPanel>
      <StatusPanel title="Chaos Runs" loading={runs.isLoading} error={runs.error}>
        <DataTable caption="Chaos runs" rows={runs.data?.runs ?? []} columns={[
          { key: "started_at", label: "Started" },
          { key: "target_service", label: "Service" },
          { key: "experiment_kind", label: "Kind" },
          { key: "dry_run", label: "Dry-run" },
          { key: "status", label: "Status", render: (row) => <Badge tone={statusTone(row.status)}>{String(row.status ?? "-")}</Badge> },
        ]} />
      </StatusPanel>
    </div>
  );
}

function gradeTone(value: unknown): "good" | "warn" | "bad" | "neutral" {
  const grade = String(value ?? "").toUpperCase();
  if (grade === "A" || grade === "B") return "good";
  if (grade === "C") return "warn";
  if (grade === "D" || grade === "F") return "bad";
  return "neutral";
}

function formatScore(score: unknown, grade: unknown) {
  const numeric = Number(score);
  const prefix = Number.isFinite(numeric) ? `${Math.round(numeric <= 1 ? numeric * 100 : numeric)}` : "-";
  return `${prefix} ${String(grade ?? "").toUpperCase() || "-"}`;
}

function riskTone(value: unknown): "good" | "warn" | "bad" | "neutral" {
  const risk = String(value ?? "").toLowerCase();
  if (risk.includes("high") || risk.includes("critical")) return "bad";
  if (risk.includes("medium")) return "warn";
  if (risk.includes("low")) return "good";
  return "neutral";
}

function statusTone(value: unknown): "good" | "warn" | "bad" | "info" | "neutral" {
  const status = String(value ?? "").toLowerCase();
  if (status.includes("complete") || status.includes("success")) return "good";
  if (status.includes("fail") || status.includes("error")) return "bad";
  if (status.includes("run") || status.includes("pending") || status.includes("dry")) return "info";
  if (status.includes("warn")) return "warn";
  return "neutral";
}
