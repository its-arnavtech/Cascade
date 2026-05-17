import { Beaker, CheckCircle, GitBranch, Route, ShieldCheck, Stethoscope } from "lucide-react";
import { Badge } from "../components/Badge";

export function AboutPage() {
  return (
    <div className="page about">
      <div className="page-heading"><div><h2>About Cascade</h2><p>Cascade is a Kubernetes-native AI reliability platform for platform engineers, SREs, and incident responders.</p></div></div>
      <section className="panel">
        <div className="section-title">Architecture overview</div>
        <div className="architecture-grid">
          <article><GitBranch size={22} /><h3>Pipeline</h3><p>Telemetry flows into anomaly detection and incident records. The UI keeps those signals close to the operator workflow.</p></article>
          <article><Stethoscope size={22} /><h3>Investigation</h3><p>Deterministic agents use read-only tools and evidence reports. The goal is explainable triage, not opaque automation.</p></article>
          <article><Beaker size={22} /><h3>Resilience</h3><p>Chaos plans model failure scenarios and validate safety policy. Browser actions stay dry-run unless dangerous mode is explicitly enabled outside the UI.</p></article>
          <article><ShieldCheck size={22} /><h3>Remediation</h3><p>Plans move through approval and dry-run validation. Execution remains behind safety boundaries by default.</p></article>
        </div>
      </section>
      <section className="panel">
        <div className="section-title">Request path</div>
        <div className="flow"><span>Operator</span><Route size={16} /><span>Command Center API</span><Route size={16} /><span>Cascade Services</span><Route size={16} /><span>Kafka / Qdrant / K8s</span></div>
      </section>
      <section className="panel">
        <div className="section-title">Safety boundaries</div>
        <ul className="safety-list">
          <li><CheckCircle size={16} />Real chaos disabled by default</li>
          <li><CheckCircle size={16} />Real remediation disabled by default</li>
          <li><CheckCircle size={16} />All operator actions are dry-run until explicitly approved</li>
        </ul>
      </section>
      <section className="panel">
        <div className="section-title">Local commands</div>
        <pre className="code-block">.\scripts\deploy-phase-9.ps1{"\n"}.\scripts\accept-phase-9.ps1{"\n"}kubectl port-forward -n cascade-system svc/command-center 18300:8030</pre>
      </section>
      <section className="panel">
        <div className="section-title">Current status</div>
        <table>
          <caption className="sr-only">Cascade delivery status by phase</caption>
          <thead><tr><th>Phase</th><th>Name</th><th>Status</th></tr></thead>
          <tbody>
            <tr><td>1-8</td><td>Core services and reliability workflows</td><td><Badge tone="good">implemented</Badge></td></tr>
            <tr><td>9</td><td>Operator command center</td><td><Badge tone="good">implemented</Badge></td></tr>
            <tr><td>10</td><td>Production hardening</td><td><Badge tone="info">planned</Badge></td></tr>
          </tbody>
        </table>
      </section>
    </div>
  );
}
