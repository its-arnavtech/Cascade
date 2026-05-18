import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, refreshIntervalMs } from "./client";
import type {
  Anomaly,
  Approval,
  ChaosPlan,
  ChaosRun,
  CountMap,
  BlastRadius,
  CausalReport,
  FeatureWindow,
  HealthCheck,
  Incident,
  Investigation,
  JsonRecord,
  KnowledgeResult,
  PolicyAuditRecord,
  RemediationExecution,
  RemediationPlan,
  ResilienceScore,
  TargetWorkload,
  TelemetryEvent,
  TopologyGraph,
} from "./types";

const poll = { refetchInterval: refreshIntervalMs };

export function useCounts() {
  return useQuery({ queryKey: ["counts"], queryFn: () => apiGet<CountMap>("/retrieval/debug/counts"), ...poll });
}

export function useTelemetry(filters: JsonRecord = {}) {
  return useQuery({ queryKey: ["telemetry", filters], queryFn: () => apiGet<{ events: TelemetryEvent[]; count: number }>("/retrieval/events/recent", filters), ...poll });
}

export function useFeatureWindows(filters: JsonRecord = {}) {
  return useQuery({ queryKey: ["features", filters], queryFn: () => apiGet<{ features: FeatureWindow[]; count: number }>("/retrieval/features/recent", filters), ...poll });
}

export function useAnomalies(filters: JsonRecord = {}) {
  return useQuery({ queryKey: ["anomalies", filters], queryFn: () => apiGet<{ anomalies: Anomaly[]; count: number }>("/retrieval/anomalies/recent", filters), ...poll });
}

export function useIncidents(filters: JsonRecord = {}) {
  return useQuery({ queryKey: ["incidents", filters], queryFn: () => apiGet<{ incidents: Incident[]; count: number }>("/retrieval/incidents/recent", filters), ...poll });
}

export function useIncident(id?: string) {
  return useQuery({ queryKey: ["incident", id], enabled: Boolean(id), queryFn: () => apiGet<JsonRecord>(`/retrieval/incidents/${id}`) });
}

export function useKnowledgeStats() {
  return useQuery({ queryKey: ["knowledge-stats"], queryFn: () => apiGet<JsonRecord>("/knowledge/knowledge/stats"), ...poll });
}

export function useKnowledgeSearch() {
  return useMutation({
    mutationFn: (body: JsonRecord) => apiPost<{ results: KnowledgeResult[]; evidence_chunks?: KnowledgeResult[]; count?: number; deterministic_summary?: string }>("/knowledge/knowledge/search", body),
  });
}

export function useKnowledgeContext() {
  return useMutation({
    mutationFn: (body: JsonRecord) => apiPost<JsonRecord>("/knowledge/knowledge/context", body),
  });
}

export function useTopologyGraph() {
  return useQuery({ queryKey: ["topology-graph"], queryFn: () => apiGet<TopologyGraph>("/topology/topology/graph"), ...poll });
}

export function useTopologySnapshot() {
  return useQuery({ queryKey: ["topology-snapshot"], queryFn: () => apiGet<{ snapshot?: TopologyGraph | null }>("/retrieval/topology/snapshot/latest"), ...poll });
}

export function useTargetWorkload() {
  return useQuery({
    queryKey: ["target-workload"],
    queryFn: () => apiGet<TargetWorkload>("/target/target/workload"),
    ...poll,
  });
}

export function useBlastRadius(rootService?: string) {
  return useQuery({
    queryKey: ["blast-radius", rootService],
    enabled: Boolean(rootService),
    queryFn: () => apiPost<BlastRadius>("/topology/topology/blast-radius", { root_service: rootService }),
    ...poll,
  });
}

export function useAnalyzeBlastRadius() {
  return useMutation({
    mutationFn: (body: { root_service: string } & JsonRecord) => apiPost<BlastRadius>("/topology/topology/blast-radius", body),
  });
}

export function useCausalIncidents() {
  return useQuery({ queryKey: ["causal-reports"], queryFn: () => apiGet<{ reports: CausalReport[]; count: number }>("/causality/causality/reports/recent"), ...poll });
}

export function useCausalIncident(id?: string) {
  return useQuery({ queryKey: ["causal-report", id], enabled: Boolean(id), queryFn: () => apiGet<{ report: CausalReport; candidates?: JsonRecord[] }>(`/causality/causality/reports/${id}`) });
}

export function useAnalyzeCausality() {
  return useMutation({
    mutationFn: (body: { target_service?: string } & JsonRecord) => apiPost<{ report: CausalReport }>("/causality/causality/analyze", body),
  });
}

export function useCausalReport() {
  return useMutation({
    mutationFn: (body: JsonRecord) => apiPost<CausalReport>("/timeline/report", body),
  });
}

export function usePolicyAuditRecords(enabled = false) {
  return useQuery({
    queryKey: ["policy-audit-records"],
    enabled,
    queryFn: () => apiGet<{ records?: PolicyAuditRecord[]; audits?: PolicyAuditRecord[]; count?: number }>("/remediation/executor/safety/audit"),
    ...poll,
  });
}

export function useInvestigations(filters: JsonRecord = {}) {
  return useQuery({ queryKey: ["investigations", filters], queryFn: () => apiGet<{ investigations: Investigation[]; count: number }>("/agent/investigations", filters), ...poll });
}

export function useInvestigation(id?: string) {
  return useQuery({ queryKey: ["investigation", id], enabled: Boolean(id), queryFn: () => apiGet<JsonRecord>(`/agent/investigations/${id}`) });
}

export function useCreateInvestigation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JsonRecord) => apiPost<JsonRecord>("/agent/investigations", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["investigations"] }),
  });
}

export function useChaosPlans(filters: JsonRecord = {}) {
  return useQuery({ queryKey: ["chaos-plans", filters], queryFn: () => apiGet<{ plans: ChaosPlan[]; count: number }>("/chaos/planner/plans", filters), ...poll });
}

export function useChaosRuns(filters: JsonRecord = {}) {
  return useQuery({ queryKey: ["chaos-runs", filters], queryFn: () => apiGet<{ runs: ChaosRun[]; count: number }>("/chaos/executor/runs", filters), ...poll });
}

export function useResilienceScores(filters: JsonRecord = {}) {
  return useQuery({ queryKey: ["resilience-scores", filters], queryFn: () => apiGet<{ scores: ResilienceScore[]; count: number }>("/chaos/executor/scores/recent", filters), ...poll });
}

export function useChaosPolicy() {
  return useQuery({ queryKey: ["chaos-policy"], queryFn: () => apiGet<JsonRecord>("/chaos/executor/safety/policy"), ...poll });
}

export function useCreateChaosPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JsonRecord) => apiPost<JsonRecord>("/chaos/planner/plans", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chaos-plans"] }),
  });
}

export function useDryRunChaos() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JsonRecord) => apiPost<JsonRecord>("/chaos/executor/runs", { ...body, dry_run: true, approved: false }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chaos-runs"] }),
  });
}

export function useRemediationPlans(filters: JsonRecord = {}) {
  return useQuery({ queryKey: ["remediation-plans", filters], queryFn: () => apiGet<{ plans: RemediationPlan[]; count: number }>("/remediation/recommender/plans", filters), ...poll });
}

export function useApprovals(filters: JsonRecord = {}) {
  return useQuery({ queryKey: ["approvals", filters], queryFn: () => apiGet<{ approvals: Approval[]; count: number }>("/remediation/approval/approvals", filters), ...poll });
}

export function useExecutions(filters: JsonRecord = {}) {
  return useQuery({ queryKey: ["executions", filters], queryFn: () => apiGet<{ executions: RemediationExecution[]; count: number }>("/remediation/executor/executions", filters), ...poll });
}

export function useRemediationPolicy() {
  return useQuery({ queryKey: ["remediation-policy"], queryFn: () => apiGet<JsonRecord>("/remediation/executor/safety/policy"), ...poll });
}

export function useCreateRemediationPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JsonRecord) => apiPost<JsonRecord>("/remediation/recommender/plans", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["remediation-plans"] }),
  });
}

export function useCreateApproval() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JsonRecord) => apiPost<JsonRecord>("/remediation/approval/approvals", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["approvals"] }),
  });
}

export function useDryRunRemediation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JsonRecord) => apiPost<JsonRecord>("/remediation/executor/executions/dry-run", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["executions"] }),
  });
}

const healthTargets = [
  ["retrieval-service", "/retrieval/health"],
  ["knowledge-retrieval-service", "/knowledge/health"],
  ["topology-service", "/topology/health"],
  ["causal-reconstruction-service", "/causality/health"],
  ["incident-timeline-service", "/timeline/health"],
  ["agent-tool-gateway", "/tools/health"],
  ["agent-orchestrator-service", "/agent/health"],
  ["chaos-planner-service", "/chaos/planner/health"],
  ["chaos-executor-service", "/chaos/executor/health"],
  ["remediation-recommender-service", "/remediation/recommender/health"],
  ["approval-service", "/remediation/approval/health"],
  ["remediation-executor-service", "/remediation/executor/health"],
  ["feature-extractor-service", "/features/health"],
  ["anomaly-detector-service", "/anomaly/health"],
] as const;

export function useSystemHealth() {
  return useQuery({
    queryKey: ["system-health"],
    queryFn: async (): Promise<HealthCheck[]> => Promise.all(healthTargets.map(checkHealth)),
    ...poll,
  });
}

async function checkHealth([name, path]: readonly [string, string]): Promise<HealthCheck> {
  const started = performance.now();
  try {
    const data = await apiGet<unknown>(path);
    return { name, ok: true, latencyMs: Math.round(performance.now() - started), data };
  } catch (error) {
    return { name, ok: false, latencyMs: Math.round(performance.now() - started), error: error instanceof Error ? error.message : String(error) };
  }
}
