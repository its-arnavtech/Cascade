import { FormEvent, useState } from "react";
import { dangerousActionsEnabled } from "../api/client";
import { useApprovals, useCreateApproval, useCreateRemediationPlan, useDryRunRemediation, useExecutions, useRemediationPlans, useRemediationPolicy } from "../api/hooks";
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
  const createPlan = useCreateRemediationPlan();
  const createApproval = useCreateApproval();
  const dryRun = useDryRunRemediation();
  const [planForm, setPlanForm] = useState({ trigger_type: "manual", service: "", namespace: "", objective: "Recommend safe remediation next steps", preferred_action_type: "investigate_only" });
  const [approvalForm, setApprovalForm] = useState({ plan_id: "", decision: "approved", approver: "local-operator", approver_role: "developer", reason: "Approved for dry-run validation only", expires_minutes: 60 });
  const [dryRunForm, setDryRunForm] = useState({ plan_id: "", approval_id: "" });
  const [activeStep, setActiveStep] = useState(1);
  const [showPolicyRaw, setShowPolicyRaw] = useState(false);

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
        setDryRunForm((current) => ({ ...current, plan_id: approvalForm.plan_id, approval_id: String(data.approval_id ?? "") }));
        setActiveStep(3);
      },
    });
  }

  function submitDryRun(event: FormEvent) {
    event.preventDefault();
    dryRun.mutate(dryRunForm);
  }

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Remediation</h2><p>Plan, approval, and dry-run validation workflows backed by real services.</p></div></div>
      <div className={`banner ${dangerousActionsEnabled ? "danger" : "warn"}`}><AlertTriangle size={18} />{dangerousActionsEnabled ? "LIVE MODE: Real remediation execution is enabled." : "Real remediation execution is blocked. Plan, approval, and validation stay dry-run by default."}</div>
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
      <div className="grid two">
        <TargetWorkloadPanel />
        <StatusPanel title="Safety Findings" loading={policy.isLoading || plans.isLoading} error={policy.error ?? plans.error}><SafetyFindingsPanel policy={policy.data} record={plans.data?.plans?.[0]} dryRun={dryRun.data?.execution ?? dryRun.data} /></StatusPanel>
      </div>
      <StatusPanel title="Safety Policy" loading={policy.isLoading} error={policy.error}>{showPolicyRaw ? <JsonBlock value={policy.data} /> : <PolicySummary value={policy.data} />}<button type="button" className="link-button" onClick={() => setShowPolicyRaw((value) => !value)}>{showPolicyRaw ? "Hide raw policy" : "View raw policy"}</button></StatusPanel>
      <StatusPanel title="Remediation Plans" loading={plans.isLoading} error={plans.error}>
        <DataTable caption="Remediation plans" rows={plans.data?.plans ?? []} empty="No data returned." columns={[{ key: "created_at", label: "Created", width: "130px" }, { key: "plan_id", label: "Plan", width: "160px" }, { key: "service", label: "Service", width: "140px" }, { key: "action_type", label: "Action", width: "140px" }, { key: "confidence", label: "Confidence", width: "100px" }, { key: "safety_findings", label: "Safety", render: (row) => formatList(row.safety_findings) }, { key: "rollback_steps", label: "Rollback", render: (row) => formatList(row.rollback_steps) }, { key: "actions", label: "Actions", width: "190px", align: "right", render: (row) => <div className="table-actions"><button type="button" className="compact" onClick={() => { const id = String(row.plan_id ?? ""); setApprovalForm((current) => ({ ...current, plan_id: id })); setActiveStep(2); }}>Approve -&gt;</button><button type="button" className="btn-dry compact" onClick={() => { const id = String(row.plan_id ?? ""); setDryRunForm((current) => ({ ...current, plan_id: id })); setActiveStep(3); }}>Validate -&gt;</button></div> }]} />
      </StatusPanel>
      <div className="grid two">
        <StatusPanel title="Approvals" loading={approvals.isLoading} error={approvals.error}><DataTable caption="Approvals" rows={approvals.data?.approvals ?? []} empty="No data returned." columns={[{ key: "decided_at", label: "Decided" }, { key: "plan_id", label: "Plan" }, { key: "decision", label: "Decision", render: (row) => <Badge tone={row.decision === "approved" ? "good" : "bad"}>{String(row.decision ?? "-")}</Badge> }, { key: "approver", label: "Approver" }, { key: "reason", label: "Reason" }]} /></StatusPanel>
        <StatusPanel title="Executions / Dry-runs" loading={executions.isLoading} error={executions.error}><DataTable caption="Executions and dry-runs" rows={executions.data?.executions ?? []} empty="No data returned." columns={[{ key: "started_at", label: "Started" }, { key: "plan_id", label: "Plan" }, { key: "dry_run", label: "Dry-run" }, { key: "executed", label: "Executed" }, { key: "rollback_available", label: "Rollback" }, { key: "validation_status", label: "Validation", render: (row) => <Badge tone={statusTone(row.validation_status)}>{String(row.validation_status ?? "-")}</Badge> }, { key: "output_summary", label: "Dry-run result" }]} /></StatusPanel>
      </div>
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

function compact(value: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== ""));
}

function statusTone(value: unknown): "good" | "warn" | "bad" | "info" | "neutral" {
  const status = String(value ?? "").toLowerCase();
  if (status.includes("pass") || status.includes("valid") || status.includes("success")) return "good";
  if (status.includes("fail") || status.includes("invalid") || status.includes("error")) return "bad";
  if (status.includes("pending") || status.includes("dry")) return "info";
  if (status.includes("warn")) return "warn";
  return "neutral";
}
