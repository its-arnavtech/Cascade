import { FormEvent, useState } from "react";
import { dangerousActionsEnabled } from "../api/client";
import { useApprovals, useCreateApproval, useCreateRemediationPlan, useDryRunRemediation, useExecutions, useRemediationPlans, useRemediationPolicy } from "../api/hooks";
import { Badge } from "../components/Badge";
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
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const activeStep = step;
  const [completedPlanId, setCompletedPlanId] = useState("");
  const [completedApprovalId, setCompletedApprovalId] = useState("");
  const [showPolicyRaw, setShowPolicyRaw] = useState(false);
  const [planForm, setPlanForm] = useState({ trigger_type: "manual", service: "recommendationservice", namespace: "cascade-targets", objective: "Recommend safe remediation next steps", preferred_action_type: "investigate_only" });
  const [approvalForm, setApprovalForm] = useState({ decision: "approved", approver: "local-operator", approver_role: "developer", reason: "Approved for dry-run validation only", expires_minutes: 60 });

  function submitPlan(event: FormEvent) {
    event.preventDefault();
    createPlan.mutate(planForm, {
      onSuccess: (data) => {
        const planId = String(data.plan_id ?? "");
        setCompletedPlanId(planId);
        setStep(2);
      },
    });
  }

  function submitApproval(event: FormEvent) {
    event.preventDefault();
    createApproval.mutate({ ...approvalForm, plan_id: completedPlanId, expires_minutes: Number(approvalForm.expires_minutes) }, {
      onSuccess: (data) => {
        setCompletedApprovalId(String(data.approval_id ?? ""));
        setStep(3);
      },
    });
  }

  function submitDryRun(event: FormEvent) {
    event.preventDefault();
    dryRun.mutate({ plan_id: completedPlanId, approval_id: completedApprovalId });
  }

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Remediation</h2><p>Plan, approval, and dry-run validation workflows backed by real services.</p></div></div>
      <div className={`banner ${dangerousActionsEnabled ? "bad" : "warn"}`}>Real remediation execution is disabled by default. This UI supports plan, approval, and dry-run workflows. Dangerous actions enabled: {String(dangerousActionsEnabled)}</div>

      <section className="panel wizard">
        <div className="wizard-steps step-indicator">
          <button type="button" className={`wizard-step-pill ${activeStep === 1 ? "active" : ""} ${completedPlanId ? "done" : ""}`} onClick={() => setStep(1)}>1 Create plan</button>
          <button type="button" className={`wizard-step-pill ${activeStep === 2 ? "active" : ""} ${completedApprovalId ? "done" : ""}`} onClick={() => setStep(2)} disabled={!completedPlanId}>2 Record approval</button>
          <button type="button" className={`wizard-step-pill ${activeStep === 3 ? "active" : ""}`} onClick={() => setStep(3)} disabled={!completedPlanId}>3 Dry-run validation</button>
        </div>

        {step === 1 ? (
          <form className="form-grid" onSubmit={submitPlan}>
            <h3>Create Plan</h3>
            <div className="form-field">
              <label htmlFor="remediation-trigger">Trigger type</label>
              <select id="remediation-trigger" value={planForm.trigger_type} onChange={(e) => setPlanForm({ ...planForm, trigger_type: e.target.value })}><option>manual</option><option>anomaly</option><option>incident</option><option>investigation</option><option>chaos</option></select>
            </div>
            <div className="form-field">
              <label htmlFor="remediation-service">Service</label>
              <input id="remediation-service" value={planForm.service} onChange={(e) => setPlanForm({ ...planForm, service: e.target.value })} placeholder="service" />
            </div>
            <div className="form-field">
              <label htmlFor="remediation-namespace">Namespace</label>
              <input id="remediation-namespace" value={planForm.namespace} onChange={(e) => setPlanForm({ ...planForm, namespace: e.target.value })} placeholder="namespace" />
            </div>
            <div className="form-field">
              <label htmlFor="remediation-objective">Objective</label>
              <input id="remediation-objective" value={planForm.objective} onChange={(e) => setPlanForm({ ...planForm, objective: e.target.value })} placeholder="objective" />
            </div>
            <div className="form-field">
              <label htmlFor="remediation-action">Preferred action type</label>
              <select id="remediation-action" value={planForm.preferred_action_type} onChange={(e) => setPlanForm({ ...planForm, preferred_action_type: e.target.value })}><option>investigate_only</option><option>restart_deployment</option><option>scale_deployment_noop</option></select>
            </div>
            <button className="btn btn-primary" type="submit" disabled={createPlan.isPending}>Create plan</button>
          </form>
        ) : null}

        {step === 2 ? (
          <form className="form-grid" onSubmit={submitApproval}>
            <h3>Approval / Rejection</h3>
            <div className="readonly-field">Plan ID<code>{completedPlanId || "No plan selected"}</code></div>
            <div className="form-field">
              <label htmlFor="remediation-decision">Decision</label>
              <select id="remediation-decision" value={approvalForm.decision} onChange={(e) => setApprovalForm({ ...approvalForm, decision: e.target.value })}><option>approved</option><option>rejected</option></select>
            </div>
            <div className="form-field">
              <label htmlFor="remediation-approver">Approver</label>
              <input id="remediation-approver" value={approvalForm.approver} onChange={(e) => setApprovalForm({ ...approvalForm, approver: e.target.value })} placeholder="approver" />
            </div>
            <div className="form-field">
              <label htmlFor="remediation-role">Role</label>
              <input id="remediation-role" value={approvalForm.approver_role} onChange={(e) => setApprovalForm({ ...approvalForm, approver_role: e.target.value })} placeholder="role" />
            </div>
            <div className="form-field">
              <label htmlFor="remediation-reason">Reason</label>
              <input id="remediation-reason" value={approvalForm.reason} onChange={(e) => setApprovalForm({ ...approvalForm, reason: e.target.value })} placeholder="reason" />
            </div>
            <div className="form-field">
              <label htmlFor="remediation-expires">Expires minutes</label>
              <input id="remediation-expires" type="number" min={1} value={approvalForm.expires_minutes} onChange={(e) => setApprovalForm({ ...approvalForm, expires_minutes: Number(e.target.value) })} />
            </div>
            <button className="btn btn-danger" type="submit" disabled={!completedPlanId || createApproval.isPending}>Record decision</button>
          </form>
        ) : null}

        {step === 3 ? (
          <form className="form-grid" onSubmit={submitDryRun}>
            <h3>Dry-run Validation</h3>
            <div className="readonly-field">Plan ID<code>{completedPlanId || "No plan selected"}</code></div>
            <div className="readonly-field">Approval ID<code>{completedApprovalId || "No approval recorded"}</code></div>
            <button className="btn btn-dry" type="submit" disabled={!completedPlanId || dryRun.isPending}>Run dry-run validation</button>
          </form>
        ) : null}
      </section>

      {createPlan.data ? <div className="state success">Created plan {String(createPlan.data.plan_id ?? "")}</div> : null}
      {createPlan.error ? <div className="state error">{createPlan.error.message}</div> : null}
      {createApproval.data ? <div className="state success">Recorded approval {String(createApproval.data.approval_id ?? "")}</div> : null}
      {createApproval.error ? <div className="state error">{createApproval.error.message}</div> : null}
      {dryRun.data ? <div className="state success">Dry-run validation complete: {String(dryRun.data.validation_status ?? dryRun.data.status ?? "recorded")}</div> : null}
      {dryRun.error ? <div className="state error">{dryRun.error.message}</div> : null}

      <StatusPanel title="Safety Policy" loading={policy.isLoading} error={policy.error}>
        {showPolicyRaw ? <JsonBlock value={policy.data} /> : <PolicySummary value={policy.data} />}
        <button type="button" className="link-button" onClick={() => setShowPolicyRaw((value) => !value)}>{showPolicyRaw ? "Hide raw policy" : "View raw policy"}</button>
      </StatusPanel>
      <StatusPanel title="Remediation Plans" loading={plans.isLoading} error={plans.error}>
        <DataTable rows={plans.data?.plans ?? []} columns={[
          { key: "created_at", label: "Created" },
          { key: "plan_id", label: "Plan" },
          { key: "service", label: "Service" },
          { key: "action_type", label: "Action" },
          { key: "status", label: "Status", render: (row) => <Badge tone={statusTone(row.status)}>{String(row.status ?? "-")}</Badge> },
          { key: "action_summary", label: "Summary" },
          { key: "actions", label: "Actions", align: "right", render: (row) => <div className="table-actions"><button type="button" className="btn compact" onClick={() => { const id = String(row.plan_id ?? ""); setCompletedPlanId(id); setStep(2); }}>Approve</button><button type="button" className="btn btn-dry compact" onClick={() => { const id = String(row.plan_id ?? ""); setCompletedPlanId(id); setStep(3); }}>Validate</button></div> },
        ]} />
      </StatusPanel>
      <div className="grid two">
        <StatusPanel title="Approvals" loading={approvals.isLoading} error={approvals.error}><DataTable rows={approvals.data?.approvals ?? []} columns={[{ key: "decided_at", label: "Decided" }, { key: "plan_id", label: "Plan" }, { key: "decision", label: "Decision", render: (row) => <Badge tone={String(row.decision ?? "").toLowerCase() === "approved" ? "good" : "bad"}>{String(row.decision ?? "-")}</Badge> }, { key: "approver", label: "Approver" }, { key: "reason", label: "Reason" }]} /></StatusPanel>
        <StatusPanel title="Executions / Dry-runs" loading={executions.isLoading} error={executions.error}><DataTable rows={executions.data?.executions ?? []} columns={[{ key: "started_at", label: "Started" }, { key: "plan_id", label: "Plan" }, { key: "dry_run", label: "Dry-run" }, { key: "executed", label: "Executed" }, { key: "validation_status", label: "Validation", render: (row) => <Badge tone={statusTone(row.validation_status)}>{String(row.validation_status ?? "-")}</Badge> }, { key: "output_summary", label: "Summary" }]} /></StatusPanel>
      </div>
    </div>
  );
}

function PolicySummary({ value }: { value: unknown }) {
  const record = value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
  const entries = Object.entries(record).slice(0, 6);
  if (!entries.length) return <div className="state">No policy details loaded yet.</div>;
  return <div className="policy-grid">{entries.map(([key, item]) => <div key={key}><span>{key.replace(/_/g, " ")}</span><strong>{typeof item === "object" ? JSON.stringify(item).slice(0, 100) : String(item)}</strong></div>)}</div>;
}

function statusTone(value: unknown): "good" | "warn" | "bad" | "dry" | "neutral" {
  const status = String(value ?? "").toLowerCase();
  if (status.includes("complete") || status.includes("success") || status.includes("valid")) return "good";
  if (status.includes("fail") || status.includes("error") || status.includes("invalid")) return "bad";
  if (status.includes("pending") || status.includes("dry") || status.includes("draft")) return "dry";
  if (status.includes("warn")) return "warn";
  return "neutral";
}
