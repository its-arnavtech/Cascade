export type JsonRecord = Record<string, unknown>;

export type CountMap = Record<string, number | null>;

export interface ApiErrorBody {
  detail?: unknown;
  message?: string;
}

export interface TelemetryEvent extends JsonRecord {
  event_id?: string;
  timestamp?: string;
  service?: string;
  namespace?: string;
  event_type?: string;
  metric_name?: string;
  metric_value?: number;
  severity?: string;
}

export interface FeatureWindow extends JsonRecord {
  window_id?: string;
  window_start?: string;
  service?: string;
  namespace?: string;
  event_count?: number;
  error_count?: number;
  latency_p95_ms?: number;
}

export interface Anomaly extends JsonRecord {
  anomaly_id?: string;
  detected_at?: string;
  service?: string;
  namespace?: string;
  severity?: string;
  risk_score?: number;
  detector_type?: string;
  model_name?: string;
  explanation?: string;
}

export interface Incident extends JsonRecord {
  incident_id?: string;
  started_at?: string;
  service?: string;
  affected_services?: unknown;
  severity?: string;
  title?: string;
  summary?: string;
}

export interface KnowledgeResult extends JsonRecord {
  score?: number;
  chunk_id?: string;
  title?: string;
  source_type?: string;
  source_path?: string;
  source_uri?: string;
  service?: string;
  phase?: string;
  severity?: string;
  chunk_text?: string;
  metadata?: unknown;
}

export interface Investigation extends JsonRecord {
  investigation_id?: string;
  created_at?: string;
  status?: string;
  service?: string;
  namespace?: string;
  trigger_type?: string;
  title?: string;
  objective?: string;
  final_summary?: string;
  confidence?: number;
  tools_used?: string[];
  evidence_refs?: unknown;
}

export interface TargetWorkload extends JsonRecord {
  name?: string;
  namespace?: string;
  frontend_service?: string;
  services?: string[];
  dependencies?: Record<string, string[]>;
  dependency_edges?: Array<[string, string]>;
  safe_chaos_services?: string[];
  protected_services?: string[];
}

export interface TopologyGraph extends JsonRecord {
  snapshot_id?: string;
  captured_at?: string;
  dependencies?: Record<string, string[]>;
  topology?: Record<string, string[]>;
  nodes?: Array<JsonRecord & { id?: string; name?: string; service?: string }>;
  edges?: Array<JsonRecord & { source?: string; target?: string; from?: string; to?: string }>;
}

export interface BlastRadius extends JsonRecord {
  root_service?: string;
  service_name?: string;
  impact_path?: string[];
  affected_services?: string[];
  upstream?: string[];
  downstream?: string[];
  score?: number;
  blast_radius_score?: number;
}

export interface CausalIncident extends JsonRecord {
  incident_id?: string;
  experiment_id?: string;
  root_cause_service?: string;
  causal_chain?: string[];
  affected_services?: string[];
  confidence?: string | number;
  evidence?: unknown;
  started_at?: string;
  generated_at?: string;
  summary?: string;
}

export interface CausalReport extends JsonRecord {
  report_id?: string;
  investigation_id?: string;
  incident_id?: string;
  title?: string;
  summary?: string;
  suspected_root_cause?: string;
  causal_summary?: string;
  affected_services?: unknown;
  evidence?: unknown;
  rejected_alternatives?: unknown;
  recommended_next_steps?: unknown;
  suggested_remediation?: unknown;
  limitations?: unknown;
  markdown_report?: string;
  confidence?: number;
}

export interface InvestigationEvidence extends JsonRecord {
  hypothesis?: string;
  evidence?: unknown;
  evidence_refs?: unknown;
  rejected_alternatives?: unknown;
  causal_summary?: string;
  blast_radius_summary?: string;
  recommended_safe_action?: string;
}

export interface PolicyAuditRecord extends JsonRecord {
  audit_id?: string;
  checked_at?: string;
  plan_id?: string;
  action_type?: string;
  namespace?: string;
  service?: string;
  allowed?: boolean | number;
  risk_level?: string;
  findings?: unknown;
  policy?: unknown;
}

export interface ChaosPlan extends JsonRecord {
  plan_id?: string;
  created_at?: string;
  status?: string;
  experiment_kind?: string;
  target_service?: string;
  target_namespace?: string;
  risk_level?: string;
  safety_score?: number;
  objective?: string;
  safety_findings?: unknown;
  safety_policy?: unknown;
  protected_services?: unknown;
  denied_resource_kinds?: unknown;
  blast_radius_score?: number;
  hypothesis?: string;
  expected_impact?: string;
  plan?: JsonRecord;
  manifest?: JsonRecord;
}

export interface ChaosRun extends JsonRecord {
  run_id?: string;
  plan_id?: string;
  started_at?: string;
  status?: string;
  dry_run?: boolean;
  experiment_kind?: string;
  target_service?: string;
  target_namespace?: string;
  manifest?: JsonRecord;
  safety?: JsonRecord;
  cleanup_status?: string;
}

export interface ResilienceScore extends JsonRecord {
  score_id?: string;
  computed_at?: string;
  service?: string;
  namespace?: string;
  experiment_kind?: string;
  resilience_score?: number;
  grade?: string;
  explanation?: string;
}

export interface RemediationPlan extends JsonRecord {
  plan_id?: string;
  created_at?: string;
  status?: string;
  trigger_type?: string;
  service?: string;
  namespace?: string;
  confidence?: number;
  action_type?: string;
  action_summary?: string;
  remediation_steps?: unknown;
  rollback_steps?: unknown;
  post_checks?: unknown;
  evidence_refs?: unknown;
  safety_findings?: unknown;
  dry_run_manifest?: JsonRecord;
  denied_resource_kinds?: unknown;
  protected_services?: unknown;
}

export interface Approval extends JsonRecord {
  approval_id?: string;
  plan_id?: string;
  decided_at?: string;
  decision?: string;
  approver?: string;
  approver_role?: string;
  reason?: string;
}

export interface RemediationExecution extends JsonRecord {
  execution_id?: string;
  plan_id?: string;
  started_at?: string;
  status?: string;
  dry_run?: boolean;
  executed?: boolean;
  validation_status?: string;
  action_type?: string;
  output_summary?: string;
  rollback_available?: boolean;
  execution_status?: string;
  output?: unknown;
  safety?: JsonRecord;
}

export interface HealthCheck {
  name: string;
  ok: boolean;
  latencyMs: number;
  data?: unknown;
  error?: string;
}
