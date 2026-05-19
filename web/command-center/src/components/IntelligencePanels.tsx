import { useMemo, useState } from "react";
import { AlertCircle, ArrowRight, GitBranch, Network, ShieldCheck, Target } from "lucide-react";
import { useBlastRadius, useTargetWorkload, useTopologySnapshot } from "../api/hooks";
import type { BlastRadius, CausalReport, JsonRecord, TargetWorkload, TopologyGraph } from "../api/types";
import { Badge } from "./Badge";
import { JsonBlock } from "./JsonBlock";
import { StatusPanel } from "./cards/StatusPanel";

export function TargetWorkloadPanel() {
  const workload = useTargetWorkload();
  const snapshot = useTopologySnapshot();
  const graph = normalizeTopology(workload.data ?? snapshot.data?.snapshot);
  const target = normalizeTarget(workload.data, graph);

  return (
    <StatusPanel title="Active Target Workload" loading={workload.isLoading && snapshot.isLoading} error={workload.error && snapshot.error ? workload.error : undefined}>
      {graph.services.length ? (
        <div className="intelligence-panel">
          <div className="intel-summary">
            <span className="intel-icon"><Target size={18} /></span>
            <div>
              <strong>{target.name || "No workload name returned."}</strong>
              <span>{target.namespace || "No namespace returned."}</span>
            </div>
            <Badge tone="info">{graph.services.length} services</Badge>
          </div>
          <div className="intel-facts target-facts">
            <Fact label="Frontend" value={target.frontend_service || "No frontend declared"} identifier />
            <Fact label="Dependencies" value={graph.edges.length ? String(graph.edges.length) : "No dependency edges"} />
            <Fact label="Snapshot" value={target.snapshot_id ?? "No snapshot yet"} identifier />
          </div>
          <ServiceChips services={graph.services} protectedServices={target.protected_services} />
        </div>
      ) : (
        <div className="state state-compact"><strong>No snapshot yet</strong><span>Run accept-telemetry or wait for observation-service to publish target topology.</span></div>
      )}
    </StatusPanel>
  );
}

export function BlastRadiusPanel({ service, data }: { service?: string; data?: BlastRadius | null }) {
  const blast = useBlastRadius(service && !data ? service : undefined);
  const value = data ?? blast.data;
  const affected = arrayOfStrings(value?.affected_services);
  const path = arrayOfStrings(value?.impact_path);
  const downstream = arrayOfStrings(value?.downstream);
  const upstream = arrayOfStrings(value?.upstream);
  const services = affected.length ? affected : [...downstream, ...upstream];

  return (
    <StatusPanel title="Blast Radius" loading={blast.isLoading} error={blast.error}>
      {service || value ? (
        <div className="intelligence-panel">
          <div className="intel-summary">
            <span className="intel-icon"><Network size={18} /></span>
            <div>
              <strong>{String(value?.root_service ?? value?.service_name ?? service ?? "No root service returned.")}</strong>
              <span>{services.length ? `${services.length} related services returned` : "No data returned."}</span>
            </div>
            <Badge tone={services.length > 4 ? "warn" : services.length ? "info" : "neutral"}>{scoreLabel(value)}</Badge>
          </div>
          <FlowList label="Critical path" values={path} />
          <ServiceChips services={services} />
          {!services.length && !path.length ? <JsonBlock value={value ?? { message: "No data returned." }} /> : null}
        </div>
      ) : (
        <div className="state">No data returned.</div>
      )}
    </StatusPanel>
  );
}

export function CausalReportPanel({ value }: { value: unknown }) {
  const report = normalizeReport(value);
  const affected = arrayOfStrings(report.affected_services);
  const rejected = arrayOfStrings(report.rejected_alternatives);
  const nextSteps = arrayOfStrings(report.recommended_next_steps ?? report.suggested_remediation);

  if (!Object.keys(report).length) return <div className="state">No data returned.</div>;

  return (
    <div className="intelligence-panel">
      <div className="intel-summary">
        <span className="intel-icon"><GitBranch size={18} /></span>
        <div>
          <strong>{String(report.title ?? "Causal summary")}</strong>
          <span>{String(report.summary ?? report.causal_summary ?? "No data returned.")}</span>
        </div>
        <Badge tone="teal">{formatConfidence(report.confidence)}</Badge>
      </div>
      <InsightRows
        rows={[
          ["Hypothesis", report.hypothesis ?? report.suspected_root_cause],
          ["Causal summary", report.causal_summary ?? report.summary],
          ["Rejected alternatives", rejected.length ? rejected.join("; ") : undefined],
          ["Recommended safe action", nextSteps.length ? nextSteps[0] : undefined],
        ]}
      />
      <FlowList label="Affected services" values={affected} />
    </div>
  );
}

export function EvidenceReportPanel({ value }: { value: unknown }) {
  const evidence = collectEvidence(value);
  if (!evidence.length) return <div className="state">No data returned.</div>;
  return (
    <div className="evidence-grid">
      {evidence.slice(0, 8).map((item, index) => {
        const record = asRecord(item) ?? {};
        return (
          <article className="evidence-card" key={String(record.id ?? record.chunk_id ?? record.anomaly_id ?? record.incident_id ?? index)}>
            <span>{String(record.source ?? record.type ?? record.title ?? `Evidence ${index + 1}`)}</span>
            <strong>{String(record.id ?? record.chunk_id ?? record.anomaly_id ?? record.incident_id ?? record.service ?? "No identifier returned.")}</strong>
            <p>{summaryOf(record)}</p>
          </article>
        );
      })}
    </div>
  );
}

export function SafetyFindingsPanel({ policy, record, dryRun }: { policy?: unknown; record?: unknown; dryRun?: unknown }) {
  const policyRecord = asRecord(policy) ?? {};
  const source = asRecord(record) ?? {};
  const plan = asRecord(source.plan) ?? source;
  const execution = asRecord(dryRun) ?? {};
  const findings = arrayOfStrings(source.safety_findings ?? plan.safety_findings ?? policyRecord.findings);
  const protectedServices = arrayOfStrings(policyRecord.protected_services ?? source.protected_services ?? plan.protected_services);
  const deniedResources = arrayOfStrings(policyRecord.denied_resource_kinds ?? source.denied_resource_kinds ?? plan.denied_resource_kinds);
  const rollback = arrayOfStrings(source.rollback_steps ?? plan.rollback_steps);
  const postChecks = arrayOfStrings(source.post_checks ?? plan.post_checks);

  return (
    <div className="intelligence-panel">
      <div className="intel-summary">
        <span className="intel-icon"><ShieldCheck size={18} /></span>
        <div>
          <strong>Safety analysis</strong>
          <span>{findings.length || protectedServices.length || deniedResources.length ? "Policy fields returned by API" : "No data returned."}</span>
        </div>
        <Badge tone={execution.executed ? "bad" : "dry"}>{execution.executed ? "Executed" : "Dry-run only"}</Badge>
      </div>
      <InsightRows
        rows={[
          ["Safety findings", findings.length ? findings.join("; ") : undefined],
          ["Protected services", protectedServices.length ? protectedServices.join(", ") : undefined],
          ["Denied resources", deniedResources.length ? deniedResources.join(", ") : undefined],
          ["Dry-run result", execution.output_summary ?? execution.summary ?? execution.validation_status],
          ["Rollback requirements", rollback.length ? rollback.join("; ") : undefined],
          ["Post-check requirements", postChecks.length ? postChecks.join("; ") : undefined],
        ]}
      />
    </div>
  );
}

export function TopologyGraphView({ value }: { value: unknown }) {
  const graph = normalizeTopology(value);
  const [selected, setSelected] = useState(graph.services[0] ?? "");
  const serviceSet = useMemo(() => new Set(graph.services), [graph.services]);
  const active = serviceSet.has(selected) ? selected : graph.services[0] ?? "";
  const downstream = active ? graph.dependencies[active] ?? [] : [];
  const upstream = active ? graph.edges.filter(([, target]) => target === active).map(([source]) => source).sort() : [];

  if (!graph.services.length) return <div className="state">No topology graph found. Register a target config with dependency_edges or deploy Sock Shop.</div>;
  return (
    <div className="dependency-map">
      <div className="dependency-summary">
        <Badge tone="info">{graph.services.length} nodes</Badge>
        <Badge tone={graph.edges.length ? "teal" : "neutral"}>{graph.edges.length} edges</Badge>
        {graph.snapshot_id ? <code>{graph.snapshot_id}</code> : null}
      </div>
      <div className="dependency-grid" role="list" aria-label="Topology dependency map">
        {graph.services.map((service) => {
          const children = graph.dependencies[service] ?? [];
          const isSelected = service === active;
          return (
            <button type="button" className={`dependency-node ${isSelected ? "selected" : ""}`} key={service} onClick={() => setSelected(service)} role="listitem">
              <span className="dependency-node-name">{service}</span>
              <span className="dependency-node-meta">{children.length ? `${children.length} downstream` : "Leaf service"}</span>
            </button>
          );
        })}
      </div>
      <div className="dependency-detail">
        <div>
          <span>Selected service</span>
          <strong>{active}</strong>
        </div>
        <DependencyChips label="Upstream" values={upstream} />
        <ArrowRight size={18} aria-hidden="true" />
        <DependencyChips label="Downstream" values={downstream} />
      </div>
    </div>
  );
}

export function normalizeTopology(value: unknown): { services: string[]; edges: Array<[string, string]>; dependencies: Record<string, string[]>; snapshot_id?: string; captured_at?: string } {
  const record = asRecord(value) ?? {};
  const rawDependencies = asStringMap(record.dependencies) ?? asStringMap(record.topology) ?? {};
  const edges: Array<[string, string]> = [];
  for (const [source, targets] of Object.entries(rawDependencies)) {
    for (const target of targets) edges.push([source, target]);
  }
  for (const edge of asArray(record.edges)) {
    const item = asRecord(edge) ?? {};
    const source = stringValue(item.source ?? item.from);
    const target = stringValue(item.target ?? item.to);
    if (source && target) edges.push([source, target]);
  }
  const services = new Set<string>();
  for (const service of Object.keys(rawDependencies)) services.add(service);
  for (const [source, target] of edges) {
    services.add(source);
    services.add(target);
  }
  for (const node of asArray(record.nodes)) {
    const item = asRecord(node) ?? {};
    const id = stringValue(item.id ?? item.name ?? item.service);
    if (id) services.add(id);
  }
  const dependencies = { ...rawDependencies };
  for (const [source, target] of edges) {
    dependencies[source] = [...(dependencies[source] ?? []), target];
    dependencies[target] = dependencies[target] ?? [];
  }
  for (const service of services) dependencies[service] = [...new Set(dependencies[service] ?? [])].sort();
  return { services: [...services].sort(), edges, dependencies, snapshot_id: stringValue(record.snapshot_id), captured_at: stringValue(record.captured_at) };
}

function normalizeTarget(value: unknown, graph: ReturnType<typeof normalizeTopology>): TargetWorkload & { snapshot_id?: string } {
  const record = asRecord(value) ?? {};
  return {
    ...record,
    services: arrayOfStrings(record.services).length ? arrayOfStrings(record.services) : graph.services,
    dependency_edges: graph.edges,
    dependencies: graph.dependencies,
    snapshot_id: graph.snapshot_id,
    protected_services: arrayOfStrings(record.protected_services),
  };
}

function normalizeReport(value: unknown): CausalReport & { hypothesis?: unknown } {
  const record = asRecord(value) ?? {};
  return (asRecord(record.report) ?? asRecord(record.report_json) ?? record) as CausalReport & { hypothesis?: unknown };
}

function collectEvidence(value: unknown): unknown[] {
  const record = asRecord(value) ?? {};
  const report = normalizeReport(value);
  const candidates = [record.evidence, record.evidence_refs, record.knowledge_refs, record.anomaly_refs, record.telemetry_evidence, record.topology_evidence, report.evidence, report.evidence_refs, report.knowledge_refs, record.tool_calls];
  return candidates.flatMap((item) => asArray(item));
}

function InsightRows({ rows }: { rows: Array<[string, unknown]> }) {
  return (
    <div className="insight-rows">
      {rows.map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{formatInline(value)}</strong>
        </div>
      ))}
    </div>
  );
}

function FlowList({ label, values }: { label: string; values: string[] }) {
  return (
    <div className="flow-block">
      <span>{label}</span>
      {values.length ? <div className="flow">{values.map((item) => <span key={item}>{item}</span>)}</div> : <div className="state">No data returned.</div>}
    </div>
  );
}

function ServiceChips({ services, protectedServices = [] }: { services: string[]; protectedServices?: string[] }) {
  if (!services.length) return <div className="state state-compact"><strong>No services returned</strong><span>Register a target config with service definitions.</span></div>;
  const protectedSet = new Set(protectedServices);
  return (
    <div className="service-chip-grid">
      {services.map((service) => (
        <span key={service} className={protectedSet.has(service) ? "protected identifier" : "identifier"}>{service}</span>
      ))}
    </div>
  );
}

function Fact({ label, value, identifier = false }: { label: string; value?: unknown; identifier?: boolean }) {
  return <div><span>{label}</span><strong className={identifier ? "identifier" : undefined}>{formatInline(value)}</strong></div>;
}

function DependencyChips({ label, values }: { label: string; values: string[] }) {
  return (
    <div className="dependency-chip-group">
      <span>{label}</span>
      <div>{values.length ? values.map((value) => <code key={value}>{value}</code>) : <em>None returned</em>}</div>
    </div>
  );
}

function formatInline(value: unknown): string {
  if (value === null || value === undefined || value === "") return "No data returned.";
  if (Array.isArray(value)) return value.length ? value.map((item) => String(item)).join(", ") : "No data returned.";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function scoreLabel(value?: BlastRadius) {
  const score = Number(value?.blast_radius_score ?? value?.score);
  if (!Number.isFinite(score)) return "No score";
  return `${Math.round(score <= 1 ? score * 100 : score)}%`;
}

function formatConfidence(value: unknown) {
  const confidence = Number(value);
  if (!Number.isFinite(confidence)) return "No confidence";
  return `${Math.round(confidence <= 1 ? confidence * 100 : confidence)}%`;
}

function summaryOf(record: JsonRecord) {
  for (const key of ["summary", "explanation", "title", "chunk_text", "response_summary", "error_message"]) {
    if (record[key]) return String(record[key]).slice(0, 260);
  }
  return JSON.stringify(record).slice(0, 260) || "No data returned.";
}

function asStringMap(value: unknown): Record<string, string[]> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const result: Record<string, string[]> = {};
  for (const [key, item] of Object.entries(value)) result[key] = arrayOfStrings(item);
  return result;
}

function arrayOfStrings(value: unknown): string[] {
  return asArray(value).map((item) => String(item)).filter(Boolean);
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asRecord(value: unknown): JsonRecord | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : undefined;
}

function stringValue(value: unknown): string | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  return String(value);
}

export function PanelNotice({ children }: { children: string }) {
  return <div className="state"><AlertCircle size={16} />{children}</div>;
}
