import { FormEvent, useState } from "react";
import { apiGet, apiPost } from "../api/client";
import { useApprovals, useCreateApproval, useCreateRemediationPlan, useDryRunRemediation, useExecutions, useLiveDemoStatus, useRemediationPlans, useRemediationPolicy, useRemediationRollbackPlans, useRemediationVerifications } from "../api/hooks";
import { AlertTriangle, Check } from "lucide-react";
import { Badge } from "../components/Badge";
import { SafetyFindingsPanel, TargetWorkloadPanel } from "../components/IntelligencePanels";
import { JsonBlock } from "../components/JsonBlock";
import { StatusPanel } from "../components/cards/StatusPanel";
import { DataTable } from "../components/tables/DataTable";

export function RemediationPage() {
  const policy = useRemediationPolicy();
  const plans = useRemediationPlans({ limit: 20 });
  const approvals = useApprovals({ limit: 20 });
  const executions = useExecutions({ limit: 20 });
  const verifications = useRemediationVerifications({ limit: 20 });
  const rollbackPlans = useRemediationRollbackPlans({ limit: 20 });
  const liveStatus = useLiveDemoStatus();
  const createPlan = useCreateRemediationPlan();
  const createApproval = useCreateApproval();
  const dryRun = useDryRunRemediation();
  const [planForm, setPlanForm] = useState({ trigger_type: "manual", service: "", namespace: "", objective: "Recommend safe remediation next steps", preferred_action_type: "investigate_only" });
  const [approvalForm, setApprovalForm] = useState({ plan_id: "", decision: "approved", approver: "local-operator", approver_role: "developer", reason: "Approved for dry-run validation only", expires_minutes: 60 });
  const [dryRunForm, setDryRunForm] = useState({ plan_id: "", approval_id: "" });
  const [activeStep, setActiveStep] = useState(1);
  const [showPolicyRaw, setShowPolicyRaw] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [liveResult, setLiveResult] = useState<Record<string, unknown> | undefined>();
  const [liveError, setLiveError] = useState("");
  const [livePending, setLivePending] = useState(false);
  const live = liveStatus.data?.remediation;
  const safeServices = (live?.allowed_services ?? []).filter((service) => !(live?.protected_services ?? []).includes(service));
  const selectedService = planForm.service || safeServices[0] || "";
  const selectedNamespace = planForm.namespace || live?.allowed_target_namespace || "cascade-targets";
  const liveReady = Boolean(liveStatus.data?.command_center?.dangerous_actions_enabled && live?.dangerous_actions_enabled && live?.real_remediation_enabled && live?.execution_enabled && live?.live_demo_mode && live?.allowed_target_namespace === "cascade-targets");

  function submitPlan(event: FormEvent) {
    event.preventDefault();
    createPlan.mutate(compact(planForm), {
      onSuccess: (data) => {
        const planId = String(data.plan_id ?? "");
        setApprovalForm((current) => ({ ...current, plan_id: planId }));
        setDryRunForm((current) => ({ ...current, plan_id: planId }));
        setActiveStep(2);
      },
    });
  }

  function submitApproval(event: FormEvent) {
    event.preventDefault();
    createApproval.mutate({ ...approvalForm, expires_minutes: Number(approvalForm.expires_minutes) }, {
      onSuccess: (data) => {
        setDryRunForm((current) => ({ ...current, plan_id: approvalForm.plan_id, approval_id: approvalId(data) }));
        setActiveStep(3);
      },
    });
  }

  function submitDryRun(event: FormEvent) {
    event.preventDefault();
    dryRun.mutate(dryRunForm);
  }

  async function runLiveDemo(event: FormEvent) {
    event.preventDefault();
    setLivePending(true);
    setLiveError("");
    setLiveResult(undefined);
    try {
      const planResponse = await apiPost<Record<string, unknown>>("/remediation/recommender/plans", {
        trigger_type: "manual",
        service: selectedService,
        namespace: selectedNamespace,
        objective: `Local UI demo restart for ${selectedService} after dry-run validation`,
        preferred_action_type: "restart_deployment",
      });
      const planId = String(planResponse.plan_id ?? "");
      const plan = (planResponse.plan as Record<string, unknown> | undefined) ?? {};
      if (!arrayLength(plan.rollback_steps)) throw new Error("Plan is missing rollback steps.");
      if (!arrayLength(plan.post_checks) && !arrayLength((plan.plan as Record<string, unknown> | undefined)?.post_checks)) throw new Error("Plan is missing post-checks.");
      const dry = await apiPost<Record<string, unknown>>("/remediation/executor/executions/dry-run", { plan_id: planId, dry_run: true });
      const approval = await apiPost<Record<string, unknown>>("/remediation/approval/approvals", { plan_id: planId, decision: "approved", approver: "local-demo-user", approver_role: "developer", reason: "Approved local UI demo remediation after dry-run", expires_minutes: 30 });
      const approval_id = approvalId(approval);
      let approvalStatus: Record<string, unknown> | undefined;
      try {
        approvalStatus = await apiGet<Record<string, unknown>>(`/remediation/approval/plans/${planId}/approval-status`);
      } catch {
        approvalStatus = { status: "unavailable" };
      }
      const execution = await apiPost<Record<string, unknown>>("/remediation/executor/executions", { plan_id: planId, approval_id, dry_run: false });
      setLiveResult({ plan: planResponse, dry_run: dry, approval, approval_status: approvalStatus, execution });
    } catch (error) {
      setLiveError(error instanceof Error ? error.message : String(error));
    } finally {
      setLivePending(false);
    }
  }

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Remediation</h2><p>Plan, approval, dry-run validation, and bounded local live-demo execution when backend policy allows it.</p></div></div>
      <div className={`banner ${liveReady ? "danger" : "warn"}`}><AlertTriangle size={18} />{liveReady ? "LIVE DEMO MODE: bounded restart_deployment is available for allowlisted local target services." : "Real remediation is disabled by default. Plan, approval, and dry-run validation are available."}</div>
      <section className="panel mode-panel">
        <div>
          <Badge tone={liveReady ? "bad" : "dry"}>{liveReady ? "Live demo enabled" : "Dry-run mode"}</Badge>
          <p>{liveReady ? "Backend policy allows only restart_deployment against safe services in cascade-targets." : "To test real local remediation, enable Live Demo Mode on a local kind-cascade cluster."}</p>
        </div>
        {!liveReady ? <code className="command-hint">powershell -ExecutionPolicy Bypass -File .\scripts\enable-ui-live-demo.ps1 -ConfirmLocalKind</code> : null}
        {!liveReady && live?.disabled_reasons?.length ? <ul className="reason-list">{live.disabled_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul> : null}
      </section>
      <section className="wizard panel">
        <div className="step-indicator">
          {[1, 2, 3].map((step) => <button type="button" key={step} className={`${activeStep === step ? "active" : ""} ${activeStep > step ? "done" : ""}`} onClick={() => setActiveStep(step)}>{activeStep > step ? <Check size={13} /> : step}<span>{step === 1 ? "Create plan" : step === 2 ? "Record approval" : "Dry-run validation"}</span></button>)}
        </div>
        {activeStep !== 1 && createPlan.data ? <SummaryRow label="Plan" value={String(createPlan.data.plan_id ?? "")} badge={<Badge tone="teal">{String(createPlan.data.status ?? "created")}</Badge>} /> : null}
        {activeStep === 1 ? (
          <form className="form-grid two-column" onSubmit={submitPlan}>
            <div className="form-field"><label htmlFor="plan-trigger">Trigger type</label><select id="plan-trigger" value={planForm.trigger_type} onChange={(e) => setPlanForm({ ...planForm, trigger_type: e.target.value })}><option>manual</option><option>anomaly</option><option>incident</option><option>investigation</option><option>chaos</option></select></div>
            <div className="form-field"><label htmlFor="plan-action">Preferred action</label><select id="plan-action" value={planForm.preferred_action_type} onChange={(e) => setPlanForm({ ...planForm, preferred_action_type: e.target.value })}><option>investigate_only</option><option>restart_deployment</option><option>scale_deployment_noop</option></select></div>
            <div className="form-field"><label htmlFor="plan-service">Service</label><input id="plan-service" value={planForm.service} onChange={(e) => setPlanForm({ ...planForm, service: e.target.value })} /></div>
            <div className="form-field"><label htmlFor="plan-namespace">Namespace</label><input id="plan-namespace" value={planForm.namespace} onChange={(e) => setPlanForm({ ...planForm, namespace: e.target.value })} /></div>
            <div className="form-field full"><label htmlFor="plan-objective">Objective</label><input id="plan-objective" value={planForm.objective} onChange={(e) => setPlanForm({ ...planForm, objective: e.target.value })} /></div>
            <button type="submit" className="full" disabled={createPlan.isPending}>Create plan</button>
          </form>
        ) : null}
        {activeStep !== 2 && createApproval.data ? <SummaryRow label="Approval" value={String(createApproval.data.approval_id ?? "")} badge={<Badge tone={approvalForm.decision === "approved" ? "good" : "bad"}>{approvalForm.decision}</Badge>} /> : null}
        {activeStep === 2 ? (
          <form className="form-grid two-column" onSubmit={submitApproval}>
            <ReadOnlyValue label="Plan ID" value={approvalForm.plan_id || "Create or select a plan first"} />
            <div className="form-field"><label htmlFor="approval-decision">Decision</label><select id="approval-decision" value={approvalForm.decision} onChange={(e) => setApprovalForm({ ...approvalForm, decision: e.target.value })}><option>approved</option><option>rejected</option></select></div>
            <div className="form-field"><label htmlFor="approval-approver">Approver</label><input id="approval-approver" value={approvalForm.approver} onChange={(e) => setApprovalForm({ ...approvalForm, approver: e.target.value })} /></div>
            <div className="form-field"><label htmlFor="approval-role">Role</label><input id="approval-role" value={approvalForm.approver_role} onChange={(e) => setApprovalForm({ ...approvalForm, approver_role: e.target.value })} /></div>
            <div className="form-field"><label htmlFor="approval-expires">Expires minutes</label><input id="approval-expires" type="number" min={1} max={1440} value={approvalForm.expires_minutes} onChange={(e) => setApprovalForm({ ...approvalForm, expires_minutes: Number(e.target.value) })} /></div>
            <div className="form-field full"><label htmlFor="approval-reason">Reason</label><input id="approval-reason" value={approvalForm.reason} onChange={(e) => setApprovalForm({ ...approvalForm, reason: e.target.value })} /></div>
            <button type="submit" className="btn-danger full" disabled={!approvalForm.plan_id || createApproval.isPending}>Record decision</button>
          </form>
        ) : null}
        {activeStep === 3 ? (
          <form className="form-grid two-column" onSubmit={submitDryRun}>
            <ReadOnlyValue label="Plan ID" value={dryRunForm.plan_id || "Create or select a plan first"} />
            <ReadOnlyValue label="Approval ID" value={dryRunForm.approval_id || "Approval optional for dry-run"} />
            <button type="submit" className="btn-dry full" disabled={!dryRunForm.plan_id || dryRun.isPending}>Dry-run validation</button>
          </form>
        ) : null}
      </section>
      <div aria-live="polite">{createPlan.error ? <div className="state error">{createPlan.error.message}</div> : null}{createApproval.error ? <div className="state error">{createApproval.error.message}</div> : null}{dryRun.error ? <div className="state error">{dryRun.error.message}</div> : null}{dryRun.data ? <div className="state success">Dry-run validation recorded.</div> : null}</div>
      {liveReady ? (
        <form className="form-grid two-column panel" onSubmit={runLiveDemo}>
          <h3 className="full">Local Live Demo Remediation</h3>
          <div className="form-field"><label htmlFor="live-remediation-service">Safe service</label><select id="live-remediation-service" value={selectedService} onChange={(e) => setPlanForm({ ...planForm, service: e.target.value })}>{safeServices.map((service) => <option key={service}>{service}</option>)}</select></div>
          <ReadOnlyValue label="Namespace" value={selectedNamespace} />
          <ReadOnlyValue label="Action" value="restart_deployment" />
          <label className="checkbox-field full"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />I understand this will mutate my local kind target namespace.</label>
          <button type="submit" className="btn-danger full" disabled={!selectedService || !confirmed || livePending}>Run bounded live remediation</button>
        </form>
      ) : null}
      <div aria-live="polite">{liveError ? <div className="state error">{liveError}</div> : null}{liveResult ? <div className="state success">Live remediation flow completed. Post-check and execution details are included in the result.</div> : null}</div>
      <div className="grid two">
        <TargetWorkloadPanel />
        <StatusPanel title="Safety Findings" loading={policy.isLoading || plans.isLoading} error={policy.error ?? plans.error}><SafetyFindingsPanel policy={policy.data} record={plans.data?.plans?.[0]} dryRun={dryRun.data?.execution ?? dryRun.data} /></StatusPanel>
      </div>
      <StatusPanel title="Safety Policy" loading={policy.isLoading} error={policy.error}>{showPolicyRaw ? <JsonBlock value={policy.data} /> : <PolicySummary value={policy.data} />}<button type="button" className="link-button" onClick={() => setShowPolicyRaw((value) => !value)}>{showPolicyRaw ? "Hide raw policy" : "View raw policy"}</button></StatusPanel>
      <StatusPanel title="Live Demo Status" loading={liveStatus.isLoading} error={liveStatus.error}><JsonBlock value={liveStatus.data} /></StatusPanel>
      <StatusPanel title="Remediation Plans" loading={plans.isLoading} error={plans.error}>
        <DataTable caption="Remediation plans" rows={plans.data?.plans ?? []} empty="No remediation plans returned." columns={[
          { key: "created_at", label: "Created", width: "130px" },
          { key: "plan_id", label: "Plan", width: "160px" },
          { key: "service", label: "Service", width: "140px", render: (row) => <code className="inline-code">{String(row.service ?? "-")}</code> },
          { key: "action_type", label: "Action", width: "150px" },
          { key: "risk", label: "Risk", width: "100px", render: (row) => <Badge tone={riskTone(policyDecision(row).risk_level ?? row.severity)}>{String(policyDecision(row).risk_level ?? row.severity ?? "unknown")}</Badge> },
          { key: "policy", label: "Policy", width: "150px", render: (row) => <Badge tone={policyTone(policyDecision(row).status)}>{String(policyDecision(row).status ?? "not evaluated").replace(/_/g, " ")}</Badge> },
          { key: "approval", label: "Approval", width: "120px", render: (row) => policyDecision(row).requires_approval ? "Required" : "Not required" },
          { key: "rollback_steps", label: "Rollback", width: "110px", render: (row) => arrayLength(row.rollback_steps) ? "Present" : "Missing" },
          { key: "reason", label: "Reason", render: (row) => formatList(policyDecision(row).reasons ?? row.safety_findings) },
          { key: "actions", label: "Actions", width: "190px", align: "right", render: (row) => <div className="table-actions"><button type="button" className="compact" onClick={() => { const id = String(row.plan_id ?? ""); setApprovalForm((current) => ({ ...current, plan_id: id })); setActiveStep(2); }}>Approve -&gt;</button><button type="button" className="btn-dry compact" onClick={() => { const id = String(row.plan_id ?? ""); setDryRunForm((current) => ({ ...current, plan_id: id })); setActiveStep(3); }}>Validate -&gt;</button></div> },
        ]} />
      </StatusPanel>
      <div className="grid two">
        <StatusPanel title="Approvals" loading={approvals.isLoading} error={approvals.error}><DataTable caption="Approvals" rows={approvals.data?.approvals ?? []} empty="No data returned." columns={[{ key: "decided_at", label: "Decided" }, { key: "plan_id", label: "Plan" }, { key: "decision", label: "Decision", render: (row) => <Badge tone={row.decision === "approved" ? "good" : "bad"}>{String(row.decision ?? "-")}</Badge> }, { key: "approver", label: "Approver" }, { key: "reason", label: "Reason" }]} /></StatusPanel>
        <StatusPanel title="Executions / Dry-runs" loading={executions.isLoading} error={executions.error}><DataTable caption="Executions and dry-runs" rows={executions.data?.executions ?? []} empty="No data returned." columns={[{ key: "started_at", label: "Started" }, { key: "plan_id", label: "Plan" }, { key: "dry_run", label: "Dry-run" }, { key: "executed", label: "Executed" }, { key: "rollback_available", label: "Rollback" }, { key: "validation_status", label: "Validation", render: (row) => <Badge tone={statusTone(row.validation_status)}>{String(row.validation_status ?? "-")}</Badge> }, { key: "output_summary", label: "Dry-run result" }]} /></StatusPanel>
      </div>
      <div className="grid two">
        <StatusPanel title="Post-Remediation Verification" loading={verifications.isLoading} error={verifications.error}><DataTable caption="Verification results" rows={verifications.data?.verifications ?? []} empty="No verification results returned." columns={[{ key: "completed_at", label: "Completed" }, { key: "execution_id", label: "Execution" }, { key: "service", label: "Service" }, { key: "status", label: "Result", render: (row) => <Badge tone={verificationTone(row.status)}>{String(row.status ?? "-").replace(/_/g, " ")}</Badge> }, { key: "evidence_quality", label: "Evidence" }, { key: "rollback_status", label: "Rollback" }, { key: "comparisons", label: "Before / after", render: (row) => comparisonSummary(row.comparisons) }, { key: "summary", label: "Summary" }]} /></StatusPanel>
        <StatusPanel title="Rollback Plans" loading={rollbackPlans.isLoading} error={rollbackPlans.error}><DataTable caption="Rollback plans" rows={rollbackPlans.data?.rollback_plans ?? []} empty="No rollback plans returned." columns={[{ key: "created_at", label: "Created" }, { key: "execution_id", label: "Execution" }, { key: "rollback_type", label: "Type" }, { key: "available", label: "Available" }, { key: "auto_executable", label: "Auto" }, { key: "status", label: "Status", render: (row) => <Badge tone={statusTone(row.status)}>{String(row.status ?? "-")}</Badge> }, { key: "reason", label: "Reason" }]} /></StatusPanel>
      </div>
      {liveResult ? <StatusPanel title="Latest Live Demo Result"><JsonBlock value={liveResult} /></StatusPanel> : null}
    </div>
  );
}

function SummaryRow({ label, value, badge }: { label: string; value: string; badge: React.ReactNode }) {
  return <div className="summary-row"><span>{label}</span><code>{value || "-"}</code>{badge}</div>;
}

function ReadOnlyValue({ label, value }: { label: string; value: string }) {
  return <div className="readonly-field"><span>{label}</span><code>{value}</code></div>;
}

function PolicySummary({ value }: { value: unknown }) {
  const record = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const entries = Object.entries(record).slice(0, 6);
  if (!entries.length) return <div className="state">No data returned.</div>;
  return <div className="policy-grid">{entries.map(([key, item]) => <div key={key}><span>{key.replace(/_/g, " ")}</span><strong>{typeof item === "object" ? JSON.stringify(item).slice(0, 80) : String(item)}</strong></div>)}</div>;
}

function formatList(value: unknown) {
  return Array.isArray(value) && value.length ? value.join("; ") : "No data returned.";
}

function comparisonSummary(value: unknown) {
  if (!Array.isArray(value) || !value.length) return "Insufficient evidence.";
  return value.slice(0, 3).map((item) => {
    const row = item && typeof item === "object" ? item as Record<string, unknown> : {};
    return `${String(row.metric ?? "metric")} ${String(row.direction ?? "unchanged")}`;
  }).join("; ");
}

function policyDecision(row: Record<string, unknown>) {
  const direct = row.policy_decision;
  const nested = (row.plan && typeof row.plan === "object" && !Array.isArray(row.plan) ? row.plan as Record<string, unknown> : {}).policy_decision;
  return (direct && typeof direct === "object" && !Array.isArray(direct) ? direct : nested && typeof nested === "object" && !Array.isArray(nested) ? nested : {}) as Record<string, unknown>;
}

function compact(value: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== ""));
}

function approvalId(value: Record<string, unknown>) {
  return String((value.approval as Record<string, unknown> | undefined)?.approval_id ?? value.approval_id ?? "");
}

function arrayLength(value: unknown) {
  return Array.isArray(value) ? value.length : 0;
}

function statusTone(value: unknown): "good" | "warn" | "bad" | "info" | "neutral" {
  const status = String(value ?? "").toLowerCase();
  if (status.includes("pass") || status.includes("valid") || status.includes("success")) return "good";
  if (status.includes("fail") || status.includes("invalid") || status.includes("error")) return "bad";
  if (status.includes("pending") || status.includes("dry")) return "info";
  if (status.includes("warn")) return "warn";
  return "neutral";
}

function verificationTone(value: unknown): "good" | "warn" | "bad" | "info" | "neutral" {
  const status = String(value ?? "").toLowerCase();
  if (status === "fixed" || status === "improved" || status === "rolled_back") return "good";
  if (status === "unchanged" || status === "insufficient_evidence") return "warn";
  if (status === "degraded" || status === "failed") return "bad";
  return "neutral";
}

function policyTone(value: unknown): "good" | "warn" | "bad" | "info" | "neutral" | "dry" {
  const status = String(value ?? "").toLowerCase();
  if (status === "blocked") return "bad";
  if (status === "requires_approval") return "warn";
  if (status === "dry_run_only") return "dry";
  if (status === "allowed_automatic") return "good";
  if (status === "allowed") return "info";
  return "neutral";
}

function riskTone(value: unknown): "good" | "warn" | "bad" | "info" | "neutral" {
  const risk = String(value ?? "").toLowerCase();
  if (risk === "critical" || risk === "rejected") return "bad";
  if (risk === "high") return "bad";
  if (risk === "medium") return "warn";
  if (risk === "low") return "good";
  return "neutral";
}
