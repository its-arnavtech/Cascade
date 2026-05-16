export function AboutPage() {
  return (
    <div className="page about">
      <div className="page-heading"><div><h2>About / Architecture</h2><p>Phase 9 turns Cascade into an operator-facing command center.</p></div></div>
      <section className="panel">
        <h2>Phase Summary</h2>
        <p>Phases 1-8 provide orchestration, telemetry, storage, anomaly detection, knowledge retrieval, deterministic investigation, chaos automation, and remediation recommendation with approval and dry-run validation. Phase 9 adds the browser UI and fixed-route BFF.</p>
      </section>
      <section className="panel">
        <h2>Request Path</h2>
        <pre className="json-block">Browser -&gt; command-center -&gt; command-center-api /api/* -&gt; retrieval / knowledge / agent / chaos / remediation services</pre>
      </section>
      <section className="panel">
        <h2>Safety Boundaries</h2>
        <p>The UI exposes reads, searches, deterministic investigations, plan creation, approvals, and dry-run validation. Real remediation execution and real chaos controls are hidden or blocked by default.</p>
      </section>
      <section className="panel">
        <h2>Local Commands</h2>
        <pre className="json-block">.\scripts\deploy-phase-9.ps1{"\n"}.\scripts\accept-phase-9.ps1{"\n"}kubectl port-forward -n cascade-system svc/command-center 18300:8030</pre>
      </section>
      <section className="panel">
        <h2>Phase 10</h2>
        <p>Production hardening remains for Phase 10: rate limiting, database backups, secret hygiene, final security audit, and production docs polish.</p>
      </section>
    </div>
  );
}
