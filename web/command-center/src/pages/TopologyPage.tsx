import { FormEvent, useState } from "react";
import { useAnalyzeBlastRadius, useTopologyGraph, useTopologySnapshot } from "../api/hooks";
import { BlastRadiusPanel, TargetWorkloadPanel, TopologyGraphView } from "../components/IntelligencePanels";
import { JsonBlock } from "../components/JsonBlock";
import { StatusPanel } from "../components/cards/StatusPanel";

export function TopologyPage() {
  const topology = useTopologyGraph();
  const snapshot = useTopologySnapshot();
  const analyze = useAnalyzeBlastRadius();
  const [service, setService] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (service.trim()) analyze.mutate({ root_service: service.trim() });
  }

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Topology</h2><p>Live dependency graph, target workload context, and bounded blast-radius analysis.</p></div></div>
      <div className="grid two">
        <TargetWorkloadPanel />
        <StatusPanel title="Latest Stored Snapshot" loading={snapshot.isLoading} error={snapshot.error}>
          {snapshot.data?.snapshot ? <JsonBlock value={snapshot.data.snapshot} /> : <div className="state">No data returned.</div>}
        </StatusPanel>
      </div>
      <StatusPanel title="Dependency Graph" loading={topology.isLoading} error={topology.error}>
        <TopologyGraphView value={topology.data} />
      </StatusPanel>
      <form className="form-grid two-column" onSubmit={submit}>
        <div className="form-field"><label htmlFor="blast-service">Root service</label><input id="blast-service" value={service} onChange={(event) => setService(event.target.value)} placeholder="service from topology" /></div>
        <button type="submit" className="full" disabled={!service.trim() || analyze.isPending}>Analyze blast radius</button>
      </form>
      {analyze.error ? <div className="state error">{analyze.error.message}</div> : null}
      <BlastRadiusPanel service={service.trim() || undefined} data={analyze.data} />
    </div>
  );
}
