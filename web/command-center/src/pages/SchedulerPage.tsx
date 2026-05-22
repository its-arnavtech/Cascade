import { FormEvent, useState } from "react";
import { CalendarClock, Pause, Play, RotateCw, ShieldCheck } from "lucide-react";
import { useControlSchedulerItem, useCreateSchedulerItem, useSchedulerHistory, useSchedulerItems, useSchedulerStatus } from "../api/hooks";
import { Badge } from "../components/Badge";
import { JsonBlock } from "../components/JsonBlock";
import { StatusPanel } from "../components/cards/StatusPanel";
import { DataTable } from "../components/tables/DataTable";

export function SchedulerPage() {
  const status = useSchedulerStatus();
  const items = useSchedulerItems();
  const history = useSchedulerHistory({ limit: 50 });
  const create = useCreateSchedulerItem();
  const pause = useControlSchedulerItem("pause");
  const resume = useControlSchedulerItem("resume");
  const run = useControlSchedulerItem("run");
  const [form, setForm] = useState({
    name: "Scheduled Autopilot dry-run",
    service: "catalogue",
    namespace: "cascade-targets",
    every_minutes: 60,
    preferred_action_type: "investigate_only",
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate({
      item_type: "autopilot_run",
      target_id: `autopilot-${form.service}`,
      name: form.name,
      schedule: { trigger: "interval", every_minutes: Number(form.every_minutes) },
      enabled: true,
      paused: false,
      mode: "dry_run_scheduler",
      payload: {
        service: form.service,
        namespace: form.namespace,
        objective: `Scheduled Autopilot dry-run for ${form.service}`,
        mode: "dry_run",
        preferred_action_type: form.preferred_action_type,
      },
    });
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <h2>Scheduler</h2>
          <p>Always-on dry-run scheduling for chaos campaigns and Autopilot workflows.</p>
        </div>
      </div>

      <section className="panel mode-panel">
        <div>
          <Badge tone="dry">{String(status.data?.mode ?? "dry-run scheduler")}</Badge>
          <p>Scheduled work delegates to existing policy-gated chaos campaign and Autopilot APIs.</p>
        </div>
        <div className="autopilot-mode-card">
          <ShieldCheck size={18} />
          <span>{status.data?.enabled === false ? "Scheduler disabled" : "Policy gates preserved"}</span>
          <code>{Number(status.data?.items ?? 0)} items / {Number(status.data?.due ?? 0)} due</code>
        </div>
      </section>

      <form className="form-grid two-column" onSubmit={submit}>
        <div className="form-field"><label htmlFor="schedule-name">Name</label><input id="schedule-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
        <div className="form-field"><label htmlFor="schedule-minutes">Every minutes</label><input id="schedule-minutes" type="number" min={1} value={form.every_minutes} onChange={(e) => setForm({ ...form, every_minutes: Number(e.target.value) })} /></div>
        <div className="form-field"><label htmlFor="schedule-service">Service</label><input id="schedule-service" value={form.service} onChange={(e) => setForm({ ...form, service: e.target.value })} /></div>
        <div className="form-field"><label htmlFor="schedule-namespace">Namespace</label><input id="schedule-namespace" value={form.namespace} onChange={(e) => setForm({ ...form, namespace: e.target.value })} /></div>
        <div className="form-field full"><label htmlFor="schedule-action">Preferred action</label><select id="schedule-action" value={form.preferred_action_type} onChange={(e) => setForm({ ...form, preferred_action_type: e.target.value })}><option>investigate_only</option><option>restart_deployment</option><option>scale_deployment_noop</option></select></div>
        <button type="submit" className="full" disabled={create.isPending}>{create.isPending ? <span className="spinner" /> : <CalendarClock size={16} />}Create Autopilot dry-run schedule</button>
      </form>
      <div aria-live="polite">{create.error ? <div className="state error">{create.error.message}</div> : null}{create.data ? <div className="state success">Scheduled item {String(create.data.item.item_id ?? "")} recorded.</div> : null}</div>

      <StatusPanel title="Scheduled Items" loading={items.isLoading} error={items.error || pause.error || resume.error || run.error}>
        <DataTable caption="Scheduled items" rows={items.data?.items ?? []} empty="No scheduled items returned." columns={[
          { key: "name", label: "Name" },
          { key: "item_type", label: "Type", width: "140px" },
          { key: "mode", label: "Mode", width: "150px", render: (row) => <Badge tone={String(row.mode).includes("dry") ? "dry" : "neutral"}>{String(row.mode ?? "-")}</Badge> },
          { key: "next_run_at", label: "Next", width: "150px" },
          { key: "last_run_at", label: "Last", width: "150px" },
          { key: "status", label: "Status", width: "130px", render: (row) => <Badge tone={itemTone(row)}>{row.paused ? "paused" : row.enabled === false ? "disabled" : String(row.status ?? "active")}</Badge> },
          { key: "actions", label: "Actions", width: "240px", align: "right", render: (row) => {
            const id = String(row.item_id ?? "");
            return <span className="button-row"><button type="button" className="compact" onClick={() => pause.mutate(id)}><Pause size={14} />Pause</button><button type="button" className="compact" onClick={() => resume.mutate(id)}><Play size={14} />Resume</button><button type="button" className="btn-dry compact" onClick={() => run.mutate(id)}><RotateCw size={14} />Dry-run</button></span>;
          } },
        ]} />
      </StatusPanel>

      <div className="grid two">
        <StatusPanel title="Scheduler Status" loading={status.isLoading} error={status.error}><JsonBlock value={status.data} /></StatusPanel>
        <StatusPanel title="Last Decision"><JsonBlock value={status.data?.last_decision ?? { status: "unknown" }} /></StatusPanel>
      </div>

      <StatusPanel title="Scheduler History" loading={history.isLoading} error={history.error}>
        <DataTable caption="Scheduler history" rows={history.data?.decisions ?? []} empty="No scheduler decisions returned." columns={[
          { key: "evaluated_at", label: "Evaluated", width: "150px" },
          { key: "status", label: "Status", width: "150px", render: (row) => <Badge tone={decisionTone(row.status)}>{String(row.status ?? "-")}</Badge> },
          { key: "item_id", label: "Item", width: "220px" },
          { key: "reason", label: "Reason" },
          { key: "run_id", label: "Run", width: "170px" },
          { key: "skipped_missed_windows", label: "Catch-up skipped", width: "140px" },
        ]} />
      </StatusPanel>
    </div>
  );
}

function itemTone(row: Record<string, unknown>): "good" | "warn" | "bad" | "info" | "neutral" {
  if (row.enabled === false) return "neutral";
  if (row.paused) return "warn";
  const status = String(row.status ?? "").toLowerCase();
  if (status.includes("stopped")) return "bad";
  return "good";
}

function decisionTone(value: unknown): "good" | "warn" | "bad" | "info" | "neutral" {
  const status = String(value ?? "").toLowerCase();
  if (status === "run_started") return "good";
  if (status.includes("blocked") || status.includes("skipped")) return "warn";
  if (status.includes("failed")) return "bad";
  if (status.includes("evaluated")) return "info";
  return "neutral";
}
