import { FormEvent, useMemo, useState } from "react";
import { Filter, Search } from "lucide-react";
import { useAuditEvents, useAuditTimeline } from "../api/hooks";
import type { AuditEvent, JsonRecord } from "../api/types";
import { Badge, type BadgeTone } from "../components/Badge";
import { JsonBlock } from "../components/JsonBlock";
import { StatusPanel } from "../components/cards/StatusPanel";

const badgeStatuses = new Set(["blocked", "dry_run", "dry-run", "verified", "rolled_back", "insufficient_evidence"]);

export function AuditPage() {
  const [draft, setDraft] = useState({ subsystem: "", severity: "", service: "", namespace: "", status: "", start_time: "", end_time: "", limit: "100" });
  const [filters, setFilters] = useState<JsonRecord>({ limit: 100 });
  const [correlationId, setCorrelationId] = useState("");
  const events = useAuditEvents(filters);
  const timeline = useAuditTimeline(correlationId);
  const rows = events.data?.events ?? [];
  const correlationRows = timeline.data?.events ?? [];
  const activeCorrelation = correlationId || String(rows[0]?.correlation_id ?? "");

  function submit(event: FormEvent) {
    event.preventDefault();
    setFilters(compact({ ...draft, limit: Number(draft.limit) || 100 }));
  }

  const sortedRows = useMemo(() => [...rows].sort((a, b) => String(b.timestamp ?? "").localeCompare(String(a.timestamp ?? ""))), [rows]);

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <h2>Audit Timeline</h2>
          <p>Trace Cascade decisions, actions, evidence, and outcomes across subsystems.</p>
        </div>
      </div>

      <section className="panel audit-filter-panel">
        <form className="form-grid audit-filters" onSubmit={submit}>
          <div className="form-field"><label htmlFor="audit-subsystem">Subsystem</label><select id="audit-subsystem" value={draft.subsystem} onChange={(e) => setDraft({ ...draft, subsystem: e.target.value })}><option value="">All</option><option>telemetry</option><option>anomaly</option><option>RCA</option><option>policy</option><option>remediation</option><option>verification</option><option>rollback</option><option>Autopilot</option><option>chaos</option><option>topology</option><option>campaigns</option><option>UI/user action</option><option>system/deployment</option></select></div>
          <div className="form-field"><label htmlFor="audit-severity">Severity</label><select id="audit-severity" value={draft.severity} onChange={(e) => setDraft({ ...draft, severity: e.target.value })}><option value="">All</option><option>debug</option><option>info</option><option>warning</option><option>error</option><option>critical</option></select></div>
          <div className="form-field"><label htmlFor="audit-service">Service</label><input id="audit-service" value={draft.service} onChange={(e) => setDraft({ ...draft, service: e.target.value })} /></div>
          <div className="form-field"><label htmlFor="audit-namespace">Namespace</label><input id="audit-namespace" value={draft.namespace} onChange={(e) => setDraft({ ...draft, namespace: e.target.value })} /></div>
          <div className="form-field"><label htmlFor="audit-status">Status</label><input id="audit-status" value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value })} /></div>
          <div className="form-field"><label htmlFor="audit-start">Start</label><input id="audit-start" type="datetime-local" value={draft.start_time} onChange={(e) => setDraft({ ...draft, start_time: e.target.value })} /></div>
          <div className="form-field"><label htmlFor="audit-end">End</label><input id="audit-end" type="datetime-local" value={draft.end_time} onChange={(e) => setDraft({ ...draft, end_time: e.target.value })} /></div>
          <div className="form-field"><label htmlFor="audit-limit">Limit</label><input id="audit-limit" type="number" min={1} max={500} value={draft.limit} onChange={(e) => setDraft({ ...draft, limit: e.target.value })} /></div>
          <button type="submit"><Filter size={16} /> Apply filters</button>
        </form>
      </section>

      <div className="grid two">
        <StatusPanel title="Chronological Events" loading={events.isLoading} error={events.error}>
          <div className="audit-timeline">
            {sortedRows.length ? sortedRows.map((event) => <AuditEventCard key={event.event_id ?? `${event.timestamp}-${event.event_type}`} event={event} onCorrelation={setCorrelationId} />) : <div className="state">No audit events returned.</div>}
          </div>
        </StatusPanel>

        <StatusPanel title="Correlation View" loading={timeline.isLoading} error={timeline.error}>
          <form className="inline-search" onSubmit={(event) => event.preventDefault()}>
            <input aria-label="Correlation ID" placeholder="correlation_id, run_id, or autopilot_run_id" value={correlationId || activeCorrelation} onChange={(e) => setCorrelationId(e.target.value)} />
            <button type="button" onClick={() => setCorrelationId(activeCorrelation)}><Search size={16} /> Load</button>
          </form>
          <div className="audit-timeline compact">
            {correlationRows.length ? correlationRows.map((event) => <AuditEventCard key={event.event_id ?? `${event.timestamp}-${event.event_type}`} event={event} />) : <div className="state">Select a correlation ID from an event.</div>}
          </div>
        </StatusPanel>
      </div>
    </div>
  );
}

function AuditEventCard({ event, onCorrelation }: { event: AuditEvent; onCorrelation?: (value: string) => void }) {
  const status = String(event.status ?? "");
  const payload = parsePayload(event.raw_payload_json);
  return (
    <article className="audit-event">
      <div className="audit-marker" />
      <div className="audit-event-main">
        <div className="audit-event-header">
          <span>{String(event.timestamp ?? "-")}</span>
          <Badge tone={severityTone(event.severity)}>{String(event.severity ?? "info")}</Badge>
          <Badge tone="teal">{String(event.subsystem ?? "-")}</Badge>
          {statusBadge(status)}
        </div>
        <h3>{String(event.event_type ?? "audit.event")}</h3>
        <p>{String(event.user_safe_message || event.evidence_summary || "No summary provided.")}</p>
        <div className="audit-meta">
          <code>{String(event.namespace || "-")}/{String(event.service || "-")}</code>
          <span>{String(event.actor || "cascade-system")}</span>
          <span>{String(event.action || "-")}</span>
          {event.correlation_id ? <button type="button" className="link-button" onClick={() => onCorrelation?.(String(event.correlation_id))}>{String(event.correlation_id)}</button> : null}
        </div>
        <details>
          <summary>Evidence and raw payload</summary>
          <p>{String(event.evidence_summary || "No evidence summary.")}</p>
          <JsonBlock value={payload} />
        </details>
      </div>
    </article>
  );
}

function statusBadge(status: string) {
  if (!status || !badgeStatuses.has(status)) return null;
  return <Badge tone={status === "blocked" || status === "insufficient_evidence" ? "bad" : "good"}>{status.replace(/_/g, " ")}</Badge>;
}

function severityTone(value: unknown): BadgeTone {
  const severity = String(value ?? "");
  if (severity === "critical" || severity === "error") return "bad";
  if (severity === "warning") return "warn";
  return "good";
}

function parsePayload(value: unknown) {
  if (typeof value !== "string") return value ?? {};
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function compact(value: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== "" && item !== undefined && item !== null));
}
