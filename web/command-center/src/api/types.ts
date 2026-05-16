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
  plan?: JsonRecord;
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
  evidence_refs?: unknown;
  safety_findings?: unknown;
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
}

export interface HealthCheck {
  name: string;
  ok: boolean;
  latencyMs: number;
  data?: unknown;
  error?: string;
}
