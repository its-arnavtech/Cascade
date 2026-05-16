import { FormEvent, useState } from "react";
import { dangerousActionsEnabled } from "../api/client";
import { useApprovals, useCreateApproval, useCreateRemediationPlan, useDryRunRemediation, useExecutions, useRemediationPlans, useRemediationPolicy } from "../api/hooks";
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
  const [planForm, setPlanForm] = useState({ trigger_type: "manual", service: "recommendationservice", namespace: "cascade-targets", objective: "Recommend safe remediation next steps", preferred_action_type: "investigate_only" });
  const [approvalForm, setApprovalForm] = useState({ plan_id: "", decision: "approved", approver: "local-operator", approver_role: "developer", reason: "Approved for dry-run validation only", expires_minutes: 60 });
  const [dryRunForm, setDryRunForm] = useState({ plan_id: "", approval_id: "" });

  function submitPlan(event: FormEvent) {
    event.preventDefault();
    createPlan.mutate(planForm);
  }

  function submitApproval(event: FormEvent) {
    event.preventDefault();
    createApproval.mutate({ ...approvalForm, expires_minutes: Number(approvalForm.expires_minutes) });
  }

  function submitDryRun(event: FormEvent) {
    event.preventDefault();
    dryRun.mutate(dryRunForm);
  }

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Remediation</h2><p>Plan, approval, and dry-run validation workflows backed by real services.</p></div></div>
      <div className="banner warn">Real remediation execution is disabled by default. This UI supports plan, approval, and dry-run workflows. Dangerous actions enabled: {String(dangerousActionsEnabled)}</div>
      <div className="grid two">
        <form className="form-grid" onSubmit={submitPlan}>
          <h3>Create Plan</h3>
          <select value={planForm.trigger_type} onChange={(e) => setPlanForm({ ...planForm, trigger_type: e.target.value })}><option>manual</option><option>anomaly</option><option>incident</option><option>investigation</option><option>chaos</option></select>
          <input value={planForm.service} onChange={(e) => setPlanForm({ ...planForm, service: e.target.value })} placeholder="service" />
          <input value={planForm.namespace} onChange={(e) => setPlanForm({ ...planForm, namespace: e.target.value })} placeholder="namespace" />
          <input value={planForm.objective} onChange={(e) => setPlanForm({ ...planForm, objective: e.target.value })} placeholder="objective" />
          <select value={planForm.preferred_action_type} onChange={(e) => setPlanForm({ ...planForm, preferred_action_type: e.target.value })}><option>investigate_only</option><option>restart_deployment</option><option>scale_deployment_noop</option></select>
          <button type="submit">Create plan</button>
        </form>
        <StatusPanel title="Safety Policy" loading={policy.isLoading} error={policy.error}><JsonBlock value={policy.data} /></StatusPanel>
      </div>
      {createPlan.data ? <div className="state success">Created plan {String(createPlan.data.plan_id ?? "")}</div> : null}
      {createPlan.error ? <div className="state error">{createPlan.error.message}</div> : null}
      <div className="grid two">
        <form className="form-grid" onSubmit={submitApproval}>
          <h3>Approval / Rejection</h3>
          <input value={approvalForm.plan_id} onChange={(e) => setApprovalForm({ ...approvalForm, plan_id: e.target.value })} placeholder="plan_id" />
          <select value={approvalForm.decision} onChange={(e) => setApprovalForm({ ...approvalForm, decision: e.target.value })}><option>approved</option><option>rejected</option></select>
          <input value={approvalForm.approver} onChange={(e) => setApprovalForm({ ...approvalForm, approver: e.target.value })} placeholder="approver" />
          <input value={approvalForm.approver_role} onChange={(e) => setApprovalForm({ ...approvalForm, approver_role: e.target.value })} placeholder="role" />
          <input value={approvalForm.reason} onChange={(e) => setApprovalForm({ ...approvalForm, reason: e.target.value })} placeholder="reason" />
          <button type="submit">Record decision</button>
        </form>
        <form className="form-grid" onSubmit={submitDryRun}>
          <h3>Dry-run Validation</h3>
          <input value={dryRunForm.plan_id} onChange={(e) => setDryRunForm({ ...dryRunForm, plan_id: e.target.value })} placeholder="plan_id" />
          <input value={dryRunForm.approval_id} onChange={(e) => setDryRunForm({ ...dryRunForm, approval_id: e.target.value })} placeholder="approval_id optional" />
          <button type="submit">Run dry-run validation</button>
        </form>
      </div>
      <StatusPanel title="Remediation Plans" loading={plans.isLoading} error={plans.error}>
        <DataTable rows={plans.data?.plans ?? []} columns={[{ key: "created_at", label: "Created" }, { key: "plan_id", label: "Plan" }, { key: "service", label: "Service" }, { key: "action_type", label: "Action" }, { key: "confidence", label: "Confidence" }, { key: "action_summary", label: "Summary" }]} />
      </StatusPanel>
      <div className="grid two">
        <StatusPanel title="Approvals" loading={approvals.isLoading} error={approvals.error}><DataTable rows={approvals.data?.approvals ?? []} columns={[{ key: "decided_at", label: "Decided" }, { key: "plan_id", label: "Plan" }, { key: "decision", label: "Decision" }, { key: "approver", label: "Approver" }, { key: "reason", label: "Reason" }]} /></StatusPanel>
        <StatusPanel title="Executions / Dry-runs" loading={executions.isLoading} error={executions.error}><DataTable rows={executions.data?.executions ?? []} columns={[{ key: "started_at", label: "Started" }, { key: "plan_id", label: "Plan" }, { key: "dry_run", label: "Dry-run" }, { key: "executed", label: "Executed" }, { key: "validation_status", label: "Validation" }, { key: "output_summary", label: "Summary" }]} /></StatusPanel>
      </div>
    </div>
  );
}
