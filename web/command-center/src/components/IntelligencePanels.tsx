import { useMemo, useState } from "react";
import { AlertCircle, ArrowRight, GitBranch, Network, ShieldCheck, Target } from "lucide-react";
import { useBlastRadius, useTargetWorkload, useTopologyGraph, useTopologySnapshot } from "../api/hooks";
import type { BlastRadius, CausalReport, JsonRecord, RcaReport, TargetWorkload, TopologyGraph } from "../api/types";
import { Badge } from "./Badge";
import { JsonBlock } from "./JsonBlock";
import { StatusPanel } from "./cards/StatusPanel";

export function TargetWorkloadPanel() {
  const workload = useTargetWorkload();
  const snapshot = useTopologySnapshot();
  const liveGraph = useTopologyGraph();
  const graph = normalizeTopology(liveGraph.data ?? workload.data ?? snapshot.data?.snapshot);
  const target = normalizeTarget(workload.data, graph);

  return (
    <StatusPanel title="Active Target Workload" loading={workload.isLoading && snapshot.isLoading && liveGraph.isLoading} error={workload.error && snapshot.error && liveGraph.error ? workload.error : undefined}>
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
            <Fact label="Discovery" value={graph.discovery_status ?? "static catalog"} />
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

export function RcaReportPanel({ value }: { value: unknown }) {
  const report = (asRecord(asRecord(value)?.report) ?? asRecord(value) ?? {}) as RcaReport;
  const affected = arrayOfStrings(report.affected_downstream_services);
  const limitations = arrayOfStrings(report.limitations);
  const chaos = asRecord(report.related_chaos_experiment);

  if (!Object.keys(report).length) return <div className="state">No RCA evidence bundle returned.</div>;

  return (
    <div className="intelligence-panel">
      <div className="intel-summary">
        <span className="intel-icon"><GitBranch size={18} /></span>
        <div>
          <strong>{String(report.likely_root_cause_service ?? "No root cause asserted")}</strong>
          <span>{String(report.explanation ?? "No RCA explanation returned.")}</span>
        </div>
        <Badge tone={report.status === "ranked" ? "teal" : report.status === "insufficient_data" ? "warn" : "info"}>{formatConfidence(report.confidence_score)}</Badge>
      </div>
      <InsightRows
        rows={[
          ["Status", report.status],
          ["Target service", report.target_service],
          ["Related chaos", chaos ? `${chaos.experiment_id ?? "experiment"} ${chaos.status ?? ""}` : "No overlapping chaos experiment"],
          ["Limitations", limitations.length ? limitations.join("; ") : undefined],
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
  const decision = asRecord(source.policy_decision ?? plan.policy_decision ?? policyRecord.policy_decision) ?? {};
  const findings = arrayOfStrings(source.safety_findings ?? plan.safety_findings ?? policyRecord.findings);
  const policyReasons = arrayOfStrings(decision.reasons);
  const protectedServices = arrayOfStrings(policyRecord.protected_services ?? source.protected_services ?? plan.protected_services);
  const deniedResources = arrayOfStrings(policyRecord.denied_resource_kinds ?? source.denied_resource_kinds ?? plan.denied_resource_kinds);
  const rollback = arrayOfStrings(source.rollback_steps ?? plan.rollback_steps);
  const postChecks = arrayOfStrings(source.post_checks ?? plan.post_checks);
  const policyStatus = String(decision.status ?? (execution.executed ? "executed" : "dry_run_only"));

  return (
    <div className="intelligence-panel">
      <div className="intel-summary">
        <span className="intel-icon"><ShieldCheck size={18} /></span>
        <div>
          <strong>Safety analysis</strong>
          <span>{findings.length || protectedServices.length || deniedResources.length ? "Policy fields returned by API" : "No data returned."}</span>
        </div>
        <Badge tone={policyTone(policyStatus)}>{policyLabel(policyStatus)}</Badge>
      </div>
      <InsightRows
        rows={[
          ["Policy decision", decision.status],
          ["Risk level", decision.risk_level],
          ["Approval requirement", decision.requires_approval === true ? "Human approval required" : decision.requires_approval === false ? "No approval required for current evaluation" : undefined],
          ["Rollback", decision.rollback_available === true ? "Rollback steps present" : decision.rollback_available === false ? "No rollback returned" : undefined],
          ["Policy reasons", policyReasons.length ? policyReasons.join("; ") : undefined],
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

function policyTone(value: string): "good" | "warn" | "bad" | "info" | "neutral" | "dry" {
  if (value === "blocked") return "bad";
  if (value === "requires_approval") return "warn";
  if (value === "dry_run_only") return "dry";
  if (value === "allowed_automatic") return "good";
  if (value === "allowed") return "info";
  return "neutral";
}

function policyLabel(value: string): string {
  return value.replace(/_/g, " ") || "No decision";
}

export function TopologyGraphView({ value }: { value: unknown }) {
  const graph = normalizeTopology(value);
  const [selected, setSelected] = useState(graph.services[0] ?? "");
  const serviceSet = useMemo(() => new Set(graph.services), [graph.services]);
  const active = serviceSet.has(selected) ? selected : graph.services[0] ?? "";
  const downstream = active ? graph.dependencies[active] ?? [] : [];
  const upstream = active ? graph.edges.filter((edge) => edge.target === active && edge.relation === "depends_on").map((edge) => edge.source).sort() : [];
  const relatedEdges = active ? graph.edges.filter((edge) => edge.source === active || edge.target === active).slice(0, 8) : [];
  const selectedNode = graph.nodeDetails[active];

  if (!graph.services.length) return <div className="state">No topology graph found. Register a target config with dependency_edges or deploy Sock Shop.</div>;
  return (
    <div className="dependency-map">
      <div className="dependency-summary">
        <Badge tone="info">{graph.services.length} nodes</Badge>
        <Badge tone={graph.edges.length ? "teal" : "neutral"}>{graph.edges.length} edges</Badge>
        <Badge tone={graph.discovery_status === "discovered" ? "teal" : "warn"}>{graph.discovery_status ?? "static catalog"}</Badge>
        <Badge tone={graph.traffic_summary.has_request_direction_evidence ? "teal" : "warn"}>{graph.traffic_summary.has_request_direction_evidence ? "traffic evidence" : "no traffic edges"}</Badge>
        {graph.red_available ? <Badge tone="teal">RED metrics</Badge> : <Badge tone="warn">RED missing/partial</Badge>}
        {graph.snapshot_id ? <code>{graph.snapshot_id}</code> : null}
      </div>
      {graph.limitations.length || graph.warnings.length ? <div className="state state-compact"><strong>Evidence notes</strong><span>{[...graph.warnings, ...graph.limitations].slice(0, 2).join(" ")}</span></div> : null}
      <div className="dependency-grid" role="list" aria-label="Topology dependency map">
        {graph.services.map((service) => {
          const children = graph.dependencies[service] ?? [];
          const isSelected = service === active;
          const node = graph.nodeDetails[service];
          return (
            <button type="button" className={`dependency-node ${isSelected ? "selected" : ""}`} key={service} onClick={() => setSelected(service)} role="listitem">
              <span className="dependency-node-name">{service}</span>
              <span className="dependency-node-meta">{node?.kind ?? "service"} · {children.length ? `${children.length} downstream` : "Leaf service"}</span>
              <span className={`source-pill source-${sourceClass(node?.source_type)}`}>{sourceLabel(node?.source_type)}</span>
            </button>
          );
        })}
      </div>
      <div className="dependency-detail">
        <div>
          <span>Selected service</span>
          <strong>{active}</strong>
          {selectedNode?.evidence ? <em>{selectedNode.evidence}</em> : null}
        </div>
        <DependencyChips label="Upstream" values={upstream} />
        <ArrowRight size={18} aria-hidden="true" />
        <DependencyChips label="Downstream" values={downstream} />
      </div>
      {relatedEdges.length ? (
        <div className="topology-evidence-list">
          {relatedEdges.map((edge) => (
            <div key={edge.id} className="topology-evidence-row">
              <code>{edge.source}</code><ArrowRight size={14} aria-hidden="true" /><code>{edge.target}</code>
              <span className={`source-pill source-${sourceClass(edge.source_type)}`}>{sourceLabel(edge.source_type)}</span>
              <span>{formatConfidence(edge.confidence)}</span>
              <p>{edge.evidence || "No edge evidence returned."}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

type NormalizedTopologyEdge = { id: string; source: string; target: string; relation: string; source_type?: string; confidence?: number; evidence?: string };
type NormalizedTopologyNode = { id: string; kind?: string; namespace?: string; health_status?: string; source_type?: string; confidence?: number; evidence?: string };

export function normalizeTopology(value: unknown): {
  services: string[];
  edges: NormalizedTopologyEdge[];
  dependencies: Record<string, string[]>;
  nodeDetails: Record<string, NormalizedTopologyNode>;
  snapshot_id?: string;
  captured_at?: string;
  discovery_status?: string;
  limitations: string[];
  warnings: string[];
  traffic_summary: { has_request_direction_evidence: boolean; traffic_inferred_edges: number; trace_inferred_edges: number };
  red_available: boolean;
} {
  const record = asRecord(value) ?? {};
  const decoded = asRecord(record.topology_json ? parseJson(record.topology_json) : undefined);
  const sourceRecord = decoded ?? record;
  const rawDependencies = asStringMap(sourceRecord.dependencies) ?? asStringMap(sourceRecord.topology) ?? {};
  const edges: NormalizedTopologyEdge[] = [];
  for (const [source, targets] of Object.entries(rawDependencies)) {
    for (const target of targets) edges.push({ id: `${source}->${target}:depends_on:dependencies`, source, target, relation: "depends_on", source_type: "static_catalog", confidence: 0.8, evidence: "Dependency returned by topology dependencies map." });
  }
  for (const edge of asArray(sourceRecord.edges)) {
    const item = asRecord(edge) ?? {};
    const source = stringValue(item.source ?? item.from);
    const target = stringValue(item.target ?? item.to);
    if (source && target) {
      const relation = stringValue(item.relation) ?? "depends_on";
      const sourceType = stringValue(item.source_type) ?? "unknown/fallback";
      edges.push({
        id: stringValue(item.id) ?? `${source}->${target}:${relation}:${sourceType}`,
        source,
        target,
        relation,
        source_type: sourceType,
        confidence: numberValue(item.confidence),
        evidence: stringValue(item.evidence),
      });
    }
  }
  const services = new Set<string>();
  const nodeDetails: Record<string, NormalizedTopologyNode> = {};
  for (const service of Object.keys(rawDependencies)) services.add(service);
  for (const edge of edges) {
    const { source, target } = edge;
    services.add(source);
    services.add(target);
  }
  for (const node of asArray(sourceRecord.nodes)) {
    const item = asRecord(node) ?? {};
    const id = stringValue(item.id ?? item.name ?? item.service);
    if (id) {
      services.add(id);
      nodeDetails[id] = {
        id,
        kind: stringValue(item.kind),
        namespace: stringValue(item.namespace),
        health_status: stringValue(item.health_status ?? item.status),
        source_type: stringValue(item.source_type),
        confidence: numberValue(item.confidence),
        evidence: stringValue(item.evidence),
      };
    }
  }
  const dependencies = { ...rawDependencies };
  for (const { source, target, relation } of edges) {
    if (relation !== "depends_on") continue;
    dependencies[source] = [...(dependencies[source] ?? []), target];
    dependencies[target] = dependencies[target] ?? [];
  }
  for (const service of services) dependencies[service] = [...new Set(dependencies[service] ?? [])].sort();
  const serviceList = [...services].sort();
  for (const service of serviceList) nodeDetails[service] = nodeDetails[service] ?? { id: service, kind: "service", source_type: "static_catalog" };
  return {
    services: serviceList,
    edges,
    dependencies,
    nodeDetails,
    snapshot_id: stringValue(sourceRecord.snapshot_id ?? record.snapshot_id),
    captured_at: stringValue(sourceRecord.captured_at ?? record.captured_at),
    discovery_status: stringValue(sourceRecord.discovery_status ?? record.discovery_status),
    limitations: arrayOfStrings(sourceRecord.limitations),
    warnings: arrayOfStrings(sourceRecord.warnings),
    traffic_summary: normalizeTrafficSummary(sourceRecord.traffic_summary),
    red_available: hasRedMetricEvidence(sourceRecord),
  };
}

function normalizeTarget(value: unknown, graph: ReturnType<typeof normalizeTopology>): TargetWorkload & { snapshot_id?: string } {
  const record = asRecord(value) ?? {};
  return {
    ...record,
    services: arrayOfStrings(record.services).length ? arrayOfStrings(record.services) : graph.services,
    dependency_edges: graph.edges.filter((edge) => edge.relation === "depends_on").map((edge) => [edge.source, edge.target] as [string, string]),
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

function parseJson(value: unknown): unknown {
  if (typeof value !== "string" || !value.trim()) return undefined;
  try {
    return JSON.parse(value);
  } catch {
    return undefined;
  }
}

function numberValue(value: unknown): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function sourceLabel(value?: string) {
  if (!value) return "unknown";
  return value.replace("kubernetes_", "k8s ").replace("_", " ");
}

function sourceClass(value?: string) {
  if (!value) return "unknown";
  if (value.includes("static")) return "static";
  if (value.includes("selector")) return "selector";
  if (value.includes("owner")) return "owner";
  if (value.includes("trace")) return "trace";
  if (value.includes("traffic")) return "telemetry";
  if (value.includes("telemetry")) return "telemetry";
  return "unknown";
}

function normalizeTrafficSummary(value: unknown) {
  const record = asRecord(value) ?? {};
  return {
    has_request_direction_evidence: Boolean(record.has_request_direction_evidence),
    traffic_inferred_edges: Number(record.traffic_inferred_edges ?? 0),
    trace_inferred_edges: Number(record.trace_inferred_edges ?? 0),
  };
}

function hasRedMetricEvidence(value: JsonRecord) {
  const sourceSummary = asRecord(value.source_summary) ?? {};
  const metrics = asRecord(value.metric_availability ?? value.red_metric_availability) ?? {};
  if (Object.values(metrics).some(Boolean)) return true;
  return Boolean(sourceSummary.red_metrics_available || sourceSummary.partial_red_metrics);
}

export function PanelNotice({ children }: { children: string }) {
  return <div className="state"><AlertCircle size={16} />{children}</div>;
}
