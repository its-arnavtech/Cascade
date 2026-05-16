import { useMemo, useState } from "react";
import { useFeatureWindows, useTelemetry } from "../api/hooks";
import { MiniBars } from "../components/charts/MiniBars";
import { StatusPanel } from "../components/cards/StatusPanel";
import { DataTable } from "../components/tables/DataTable";

export function TelemetryPage() {
  const [service, setService] = useState("");
  const [namespace, setNamespace] = useState("");
  const [eventType, setEventType] = useState("");
  const [limit, setLimit] = useState(25);
  const filters = { service, namespace, event_type: eventType, limit };
  const events = useTelemetry(filters);
  const features = useFeatureWindows({ service, limit });
  const bars = useMemo(() => {
    const counts = new Map<string, number>();
    for (const event of events.data?.events ?? []) counts.set(String(event.service ?? "unknown"), (counts.get(String(event.service ?? "unknown")) ?? 0) + 1);
    return [...counts.entries()].map(([label, value]) => ({ label, value }));
  }, [events.data]);

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Telemetry / Events</h2><p>Recent enriched telemetry and feature windows from ClickHouse.</p></div></div>
      <div className="filters">
        <input placeholder="service" value={service} onChange={(e) => setService(e.target.value)} />
        <input placeholder="namespace" value={namespace} onChange={(e) => setNamespace(e.target.value)} />
        <input placeholder="event type" value={eventType} onChange={(e) => setEventType(e.target.value)} />
        <input type="number" min={1} max={100} value={limit} onChange={(e) => setLimit(Number(e.target.value))} />
      </div>
      <div className="grid two">
        <StatusPanel title="Event Count By Service" loading={events.isLoading} error={events.error}><MiniBars values={bars} /></StatusPanel>
        <StatusPanel title="Feature Window Event Trend" loading={features.isLoading} error={features.error}>
          <MiniBars values={(features.data?.features ?? []).slice(0, 12).map((row, index) => ({ label: String(row.service ?? `window ${index + 1}`), value: Number(row.event_count ?? 0) }))} />
        </StatusPanel>
      </div>
      <StatusPanel title="Recent Telemetry Events" loading={events.isLoading} error={events.error}>
        <DataTable rows={events.data?.events ?? []} columns={[{ key: "timestamp", label: "Time" }, { key: "service", label: "Service" }, { key: "namespace", label: "Namespace" }, { key: "event_type", label: "Type" }, { key: "metric_name", label: "Metric" }, { key: "metric_value", label: "Value" }]} />
      </StatusPanel>
      <StatusPanel title="Feature Windows" loading={features.isLoading} error={features.error}>
        <DataTable rows={features.data?.features ?? []} columns={[{ key: "window_start", label: "Window" }, { key: "service", label: "Service" }, { key: "event_count", label: "Events" }, { key: "error_count", label: "Errors" }, { key: "latency_p95_ms", label: "p95 ms" }]} />
      </StatusPanel>
    </div>
  );
}
